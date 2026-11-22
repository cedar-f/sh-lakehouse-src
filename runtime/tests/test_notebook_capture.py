import json,os,subprocess,sys
from pathlib import Path
import nbformat

def test_real_notebook_retains_cells_outputs_and_relative_working_directory(tmp_path):
    original=tmp_path/'project';original.mkdir();(original/'relative.txt').write_text('relative data')
    directory=tmp_path/'run';directory.mkdir()
    source=directory/'source.ipynb';out=directory/'result.ipynb'
    source.write_text(json.dumps({'nbformat':4,'nbformat_minor':5,'metadata':{},'cells':[
        {'cell_type':'code','metadata':{},'source':'from pathlib import Path\nprint(Path("relative.txt").read_text())\nset_output("count", parameters["count"])','execution_count':5,'outputs':[{'output_type':'stream','name':'stdout','text':'stale output'}]}]}))
    env={**os.environ,'IPYTHONDIR':str(tmp_path/'ipython'),'LAKEHOUSE_NOTEBOOK_CWD':str(original),'LAKEHOUSE_RUN_DIR':str(directory),'LAKEHOUSE_PARAMETERS':'{"count": 2}'}
    result=subprocess.run([sys.executable,str(Path(__file__).parents[1]/'execute_notebook.py'),str(source),str(out)],env=env,capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
    notebook=nbformat.read(out,as_version=4);nbformat.validate(notebook)
    assert notebook.cells[1].metadata.lakehouse.status=='SUCCESS'
    assert 'relative data' in notebook.cells[1].outputs[0].text
    assert 'stale output' not in out.read_text()
    assert json.loads((directory/'outputs.json').read_text())['count']==2
    assert 'relative data' in (directory/'notebook.events.jsonl').read_text()

def test_failed_notebook_preserves_error_cell_and_previous_outputs(tmp_path):
    source=tmp_path/'source.ipynb';output=tmp_path/'failed.ipynb'
    source.write_text(json.dumps({'nbformat':4,'nbformat_minor':5,'metadata':{},'cells':[
        {'cell_type':'code','metadata':{},'source':'print("first completed")','execution_count':None,'outputs':[]},
        {'cell_type':'code','metadata':{},'source':'raise ValueError("expected failure")','execution_count':None,'outputs':[]}]}))
    env={**os.environ,'IPYTHONDIR':str(tmp_path/'ipython'),'LAKEHOUSE_RUN_DIR':str(tmp_path)}
    result=subprocess.run([sys.executable,str(Path(__file__).parents[1]/'execute_notebook.py'),str(source),str(output)],env=env,capture_output=True,text=True,timeout=30)
    assert result.returncode!=0
    notebook=nbformat.read(output,as_version=4)
    assert notebook.cells[1].metadata.lakehouse.status=='SUCCESS'
    assert notebook.cells[2].metadata.lakehouse.status=='FAILED'
    assert notebook.cells[2].outputs[0].ename=='ValueError'
    assert 'expected failure' in (tmp_path/'notebook.events.jsonl').read_text()
