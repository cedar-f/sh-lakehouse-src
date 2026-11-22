"""Index Kestra executions, preserving the richer local task trace when available."""
import json,time,threading
from datetime import datetime
from config import ROOT,RUNTIME
import run_store
from workflow_runtime import workflow_file
LOCK=threading.Lock()
last_sync=0

def stamp(value):
    return datetime.fromisoformat(value.replace('Z','+00:00')).timestamp() if value else None

def sync(request):
    global last_sync
    with LOCK:
        if time.monotonic()-last_sync<15:return
        page=1
        while True:
            response=request('GET','executions/search',params={'filters[namespace][EQUALS]':'lakehouse.v3','page':page,'size':100,'sort':'state.startDate:desc'})
            for execution in response.get('results',[]):
                if execution.get('namespace')!='lakehouse.v3':continue
                state=execution.get('state',{});local=run_store.read_json(workflow_file(execution['id']))
                definition=local.get('definition') or run_store.read_json(ROOT/'workflows'/(execution['flowId']+'.json'))
                item={'id':execution['id'],'name':execution['flowId'],'flow_id':execution['flowId'],'kind':'workflow',
                      'status':state.get('current','UNKNOWN'),'started':stamp(state.get('startDate')) or time.time(),
                      'ended':stamp(state.get('endDate')),'types':sorted({n['kind'] for n in definition.get('nodes',[])}) or ['workflow'],
                      'trigger':execution.get('trigger',{}),'revision':execution.get('flowRevision')}
                if item['ended']:item['duration']=round(item['ended']-item['started'],3)
                run_store.upsert('workflow',item)
            if page*100>=response.get('total',0):break
            page+=1
        last_sync=time.monotonic()

def detail(execution_id,request):
    local=run_store.read_json(workflow_file(execution_id))
    try:execution=request('GET','executions/'+execution_id)
    except Exception:
        with run_store.connect() as connection:row=connection.execute("SELECT meta FROM history WHERE category='workflow' AND id=?",(execution_id,)).fetchone()
        if not row and not local:raise
        meta=json.loads(row['meta']) if row else local
        execution={'id':execution_id,'namespace':'lakehouse.v3','flowId':meta['name'],'state':{'current':meta['status']},'inputs':local.get('inputs',{})}
        local={**meta,**local,'artifacts_expired':True}
    if execution.get('namespace')!='lakehouse.v3':raise ValueError('Execution is outside this workspace namespace')
    with run_store.connect() as connection:
        rows=connection.execute("SELECT meta FROM history WHERE category='run' AND json_extract(meta,'$.workflow_execution_id')=? ORDER BY started",(execution_id,)).fetchall()
    runs=[json.loads(r['meta']) for r in rows]
    state=execution.get('state',{})
    item={**local,'id':execution_id,'name':execution['flowId'],'status':state.get('current','UNKNOWN'),
          'started':stamp(state.get('startDate')) or local.get('started'),'ended':stamp(state.get('endDate')) or local.get('ended'),'runs':runs,
          'kestra_tasks':[{'id':t['id'],'task_id':t.get('taskId'),'status':t.get('state',{}).get('current'),
                          'started':stamp(t.get('state',{}).get('startDate')),'ended':stamp(t.get('state',{}).get('endDate')),
                          'attempts':len(t.get('attempts',[]))} for t in execution.get('taskRunList',[])],
          'inputs':local.get('inputs',execution.get('inputs',{}))}
    try:item['logs']=request('GET','logs/'+execution_id,params={'minLevel':'INFO'})
    except Exception as error:item['log_error']=str(error)
    if item.get('ended') and item.get('started'):item['duration']=round(item['ended']-item['started'],3)
    return run_store.redact(item)
