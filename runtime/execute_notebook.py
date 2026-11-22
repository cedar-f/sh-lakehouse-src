import json,os,sys,time,signal
from pathlib import Path
import nbformat
from nbclient import NotebookClient
from run_store import append_event,atomic_json,redact
source,output=map(Path,sys.argv[1:3])
notebook=nbformat.read(source,as_version=4)
for existing in notebook.cells:
    existing.metadata.pop('lakehouse',None)
    if existing.cell_type=='code':existing.outputs=[];existing.execution_count=None
parameters=json.loads(os.getenv('LAKEHOUSE_PARAMETERS','{}'))
directory=output.parent
cell=nbformat.v4.new_code_cell('from runtime_outputs import set_output\nparameters = '+repr(parameters));cell.metadata['lakehouse_parameters']=True;notebook.cells.insert(0,cell)
last_saved=[0]
def snapshot(force=False):
    if force or time.monotonic()-last_saved[0]>.25:
        atomic_json(directory/'notebook-progress.json',redact(notebook));last_saved[0]=time.monotonic()
def starting(cell,cell_index,**kwargs):
    cell.metadata['lakehouse']={'status':'RUNNING','started':time.time()};snapshot(True)
    if not cell.metadata.get('lakehouse_parameters'):append_event(directory,'Cell '+str(cell_index)+' started',source='notebook',cell=cell_index)
def completed(cell,cell_index,**kwargs):
    meta=cell.metadata.setdefault('lakehouse',{});meta['ended']=time.time();meta['duration']=meta['ended']-meta.get('started',meta['ended'])
    meta['status']='FAILED' if any(o.get('output_type')=='error' for o in cell.get('outputs',[])) else 'SUCCESS';snapshot(True)
    if not cell.metadata.get('lakehouse_parameters'):append_event(directory,'Cell '+str(cell_index)+' '+meta['status'],source='notebook',cell=cell_index)
class RecordingClient(NotebookClient):
    def process_message(self,msg,cell,cell_index):
        try:
            result=super().process_message(msg,cell,cell_index);content=msg.get('content',{});kind=msg.get('msg_type')
            if not cell.metadata.get('lakehouse_parameters'):
                if kind=='stream':append_event(directory,content.get('text',''),'WARN' if content.get('name')=='stderr' else 'INFO',source='notebook',cell=cell_index,stream=content.get('name'))
                elif kind=='error':append_event(directory,'\n'.join(content.get('traceback',[])),'ERROR',source='notebook',cell=cell_index)
            return result
        finally:snapshot()
client=RecordingClient(notebook,timeout=3600,kernel_name='python3',resources={'metadata':{'path':os.getenv('LAKEHOUSE_NOTEBOOK_CWD',str(source.parent))}},on_cell_start=starting,on_cell_executed=completed)
def interrupted(*_):raise KeyboardInterrupt('Notebook execution interrupted')
signal.signal(signal.SIGTERM,interrupted)
try: client.execute()
finally:
    for cell in notebook.cells:
        meta=cell.metadata.get('lakehouse',{})
        if meta.get('status')=='RUNNING':meta.update(status='INTERRUPTED',ended=time.time())
    snapshot(True);atomic_json(output,redact(notebook))
