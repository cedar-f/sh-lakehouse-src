import json,time
from pathlib import Path
import pytest
import run_store as store
import workflow_runtime as engine
import retention
from workflows import compile_flow

@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):
    runs=tmp_path/'runs';runs.mkdir()
    monkeypatch.setattr(store,'RUNS',runs);monkeypatch.setattr(store,'DB',tmp_path/'history.sqlite')
    monkeypatch.setattr(engine,'DIRECTORY',tmp_path/'workflows')
    monkeypatch.setattr(retention,'RUNS',runs);monkeypatch.setattr(retention,'RUNTIME',tmp_path/'runtime')
    monkeypatch.setenv('TZ','Asia/Ho_Chi_Minh')

def test_history_filters_paging_and_timezone():
    start=store.parse_time('2026-11-21T07:00:00')
    assert start==store.parse_time('2026-11-21T00:00:00Z')
    for i in range(31):store.upsert('run',{'id':f'{i:032x}','name':'orders' if i<20 else 'customer','kind':'dbt' if i%2 else 'sql','status':'SUCCESS' if i<15 else 'FAILED','started':start+i})
    assert store.history(search='orders',kind='dbt',status='SUCCESS')['total']==7
    assert len(store.history(page=2,page_size=10)['items'])==10
    assert store.history(search=f'{30:032x}')['total']==1
    assert store.history(from_time='2026-11-21T07:00:10',to_time='2026-11-21T07:00:20')['total']==11
    with pytest.raises(ValueError):store.history(from_time='2026-11-22',to_time='2026-11-21')

def test_log_cursor_no_loss_or_duplicates():
    run_id='a'*32;directory=store.RUNS/run_id;directory.mkdir();store.write_run(directory,{'id':run_id,'kind':'notebook','status':'SUCCESS','started':time.time()})
    for i in range(60):store.append_event(directory,'line '+str(i),source='process' if i%2 else 'notebook',index=i)
    cursor='';rows=[]
    for _ in range(20):
        result=store.log_page(run_id,cursor,7);rows+=result['items'];cursor=result['cursor']
        if not result['has_more']:break
    assert len(rows)==60 and len({r['id'] for r in rows})==60
    assert sorted(r['index'] for r in rows)==list(range(60))

def test_log_redaction_and_artifact_traversal(monkeypatch):
    monkeypatch.setenv('RUNNER_TOKEN','secret-unit-value')
    run_id='b'*32;directory=store.RUNS/run_id;directory.mkdir();store.write_run(directory,{'id':run_id,'status':'SUCCESS'})
    store.append_event(directory,'error secret-unit-value','ERROR');(directory/'profiles.yml').write_text('password: private')
    assert store.log_page(run_id)['items'][0]['message']=='error [REDACTED]'
    (directory/'dbt-job.json').write_text('{"parameters":{"password":"private"}}')
    assert not any(a['path']=='dbt-job.json' for a in store.artifacts(run_id))
    for path in ('../history.sqlite','profiles.yml','dbt-job.json'):
        with pytest.raises(ValueError):store.artifact_path(run_id,path)

def task(id,kind='sql',**kw):return dict(id=id,kind=kind,sql='SELECT 1',**kw)
def run(nodes,executor=None,**kw):
    return engine.execute_workflow({'id':'test','nodes':nodes,**kw},'test_execution',{},executor or (lambda p,i:{'status':'SUCCESS','outputs':p.get('parameters',{})}))

def test_notebook_outputs_vars_conditions_and_loop():
    seen=[]
    def execute(payload,id):
        seen.append(payload)
        return {'status':'SUCCESS','outputs':{'values':[2,3]}} if payload['task_id']=='source' else {'status':'SUCCESS','outputs':{'n':payload['parameters']['n']}}
    result=run([task('source','notebook',path='test.ipynb'),task('vars','variable',dependsOn=['source'],values={'threshold':2}),task('if','condition',dependsOn=['vars'],condition='len(outputs.source.values) == vars.threshold'),task('loop','loop',parent='if',branch='then',values='{{ outputs.source.values }}'),task('consumer',parent='loop',parameters={'n':'{{ item * 10 }}'})],execute)
    assert result['status']=='SUCCESS'
    assert [p['parameters']['n'] for p in seen[1:]]==[20,30]
    assert result['outputs']['loop']['count']==2
    assert len(result['tasks'])==6

def test_failure_handler_and_always_semantics():
    def execute(payload,id):return {'status':'FAILED','error':'expected'} if payload['task_id']=='bad' else {'status':'SUCCESS','outputs':{}}
    result=run([task('bad'),task('recover',dependsOn=['bad'],runWhen='failure'),task('skip',dependsOn=['bad']),task('finally',dependsOn=['bad'],runWhen='always')],execute)
    assert result['status']=='SUCCESS'
    assert next(t for t in result['tasks'] if t['id']=='skip')['status']=='SKIPPED'
    assert run([task('bad'),task('finally',dependsOn=['bad'],runWhen='always')],execute)['status']=='FAILED'

def test_loop_limit_and_nested_cycle_rejected():
    assert run([task('loop','loop',values=[1,2],maxIterations=1)])['status']=='FAILED'
    with pytest.raises(ValueError,match='cycle'):engine.validate({'nodes':[task('a','loop',parent='b'),task('b','loop',parent='a')]})

@pytest.mark.parametrize('expression',["__import__('os').system('id')","vars.__class__","[1] * 100000000"])
def test_expression_does_not_execute_python(expression):
    with pytest.raises((ValueError,KeyError)):engine.expression(expression,{'vars':{}})

def test_compiled_advanced_flow_has_inputs_and_controller():
    result=compile_flow({'id':'conditional','inputs':{'enabled':True},'nodes':[task('condition','condition',condition='inputs.enabled')]})
    assert result['inputs'][0]['type']=='JSON'
    assert result['tasks'][0]['uri'].endswith('/workflow/execute')

def test_retention_protects_active_runs_and_preserves_history(monkeypatch):
    monkeypatch.setenv('RUN_RETENTION_DAYS','1')
    for i,status in enumerate(['RUNNING','SUCCESS','FAILED']):
        directory=store.RUNS/f'{i:032x}';directory.mkdir();store.write_run(directory,{'id':directory.name,'status':status,'started':100,'ended':101 if status!='RUNNING' else None});(directory/'execution.log').write_text('log')
    preview=retention.cleanup(False,now=200000)
    assert len(preview['runs'])==2 and len(list(store.RUNS.iterdir()))==3
    retention.cleanup(True,now=200000)
    assert len(list(store.RUNS.iterdir()))==1
    assert store.history()['total']==3
    assert store.detail(f'{1:032x}')['artifacts_expired'] is True

@pytest.mark.parametrize('status',['QUEUED','RUNNING'])
def test_restart_marks_abandoned_work_interrupted_without_replaying(tmp_path,monkeypatch,status):
    monkeypatch.setattr(store,'RUNTIME',tmp_path/'runtime')
    directory=store.RUNS/('d'*32);directory.mkdir();store.write_run(directory,{'id':directory.name,'kind':'notebook','status':status,'started':100})
    store.atomic_json(directory/'notebook-progress.json',{'cells':[{'metadata':{'lakehouse':{'status':'RUNNING'}}}]})
    trace=store.RUNTIME/'workflows/execution/execution.json';store.atomic_json(trace,{'id':'execution','name':'flow','status':'RUNNING','started':100,'tasks':[{'id':'task','status':'RUNNING'}]})
    store.recover_interrupted()
    assert store.read_run(directory.name)['status']=='INTERRUPTED'
    assert store.read_json(directory/'notebook-progress.json')['cells'][0]['metadata']['lakehouse']['status']=='INTERRUPTED'
    assert store.read_json(trace)['tasks'][0]['status']=='INTERRUPTED'
    assert store.history('workflow',status='INTERRUPTED')['total']==1
