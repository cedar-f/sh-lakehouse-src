"""Private runner. No Docker socket; accepts only allowlisted task types and paths."""
import concurrent.futures
import json
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated
import httpx
import yaml
from fastapi import FastAPI, Depends, Header, HTTPException
from config import ROOT, RUNTIME, RUNS, SETTINGS, safe_path, settings, identifier, uc, spark_conf, timezone_name
import run_store
from run_support import snapshot_source,capture_process
from workflows import compile_flow
from dbt_project import prepare_dbt_project, project_destination, ensure_schema_macro
from sql_supervisor import CONTROL as SQL_CONTROL, read_json, write_json

app=FastAPI()
LOCK=threading.Lock()
POOL=concurrent.futures.ThreadPoolExecutor(max_workers=2)
RESTART_POOL=concurrent.futures.ThreadPoolExecutor(max_workers=1)
CONFIG_LOCK=threading.Lock()
SQL_RESTART_ID=None
FLOWS=ROOT/'workflows'
for p in [RUNS,FLOWS,ROOT/'.lakehouse']: p.mkdir(parents=True,exist_ok=True)

def auth(x_runner_token:Annotated[str,Header()]=''):
    import hmac
    if not hmac.compare_digest(x_runner_token,os.environ['RUNNER_TOKEN']): raise HTTPException(401,'Invalid runner token')

def record(directory,data):
    run_store.write_run(directory,data)

def sql_query(sql,catalog=None,schema=None):
    from pyhive import hive
    from TCLIService.ttypes import TOperationState
    conf={k:v for k,v in spark_conf().items() if k.startswith('spark.sql.catalog.')}
    conf['spark.sql.defaultCatalog']=identifier(catalog or settings()['default_catalog'])
    # Spark Thrift copies Hive session variables into Spark SQLConf. Plain keys
    # update only HiveConf and do not register catalogs in a new Spark session.
    conf={'set:hivevar:'+key:value for key,value in conf.items()}
    connection=hive.Connection(host=os.getenv('SQL_HOST','sql'),port=10000,auth='NOSASL',
        username='lakehouse',database=identifier(schema or settings()['default_schema']),configuration=conf)
    try:
        from sql_functions import SQLFunctions
        from function_sql_adapters import replace
        def execute(statement):
            cursor=connection.cursor()
            try:
                cursor.execute(statement)
                if not cursor.description:return {'columns':[],'rows':[]}
                rows=cursor.fetchmany(1001)
                return {'columns':[c[0] for c in cursor.description],'rows':[list(r) for r in rows[:1000]],'truncated':len(rows)>1000}
            finally:cursor.close()
        return SQLFunctions(execute,lambda cols,rows:{'columns':cols,'rows':rows},replace=replace).run(sql)
    finally: connection.close()

def wait_for_sql_ready(timeout=120):
    deadline=time.monotonic()+timeout
    while True:
        state=read_json(SQL_CONTROL/'status.json')
        if state.get('state') in ('FAILED','STOPPED'):
            raise RuntimeError('Spark SQL is unavailable: '+state.get('error',state['state'])+
                               '. Open Compute and use Save & Restart Spark for SQL/dbt.')
        try:
            sql_query('SELECT 1')
            return
        except Exception as error:
            remaining=deadline-time.monotonic()
            if remaining<=0:
                raise RuntimeError('Timed out waiting for Spark SQL. Check Compute and the SQL service logs: '+str(error)) from error
            time.sleep(min(2,remaining))


def command_error(kind,code,log):
    import re
    with log.open('rb') as stream:
        stream.seek(max(0,log.stat().st_size-20000))
        text=stream.read().decode(errors='replace')
    text=re.sub(r'\x1b\[[0-9;]*m','',text)
    for key,value in os.environ.items():
        if len(value)>5 and any(part in key for part in ('TOKEN','SECRET','PASSWORD','ACCESS_KEY')):
            text=text.replace(value,'[REDACTED]')
    marker=re.search(r'\[ERROR\]:|Runtime Error in |Compilation Error in |Traceback \(most recent call last\):',text)
    excerpt=(text[marker.start():] if marker else text[-1800:]).strip()[:1800]
    return f'{kind} failed (exit {code}). '+excerpt


def execute(payload,run_id):
    directory=RUNS/run_id; directory.mkdir(exist_ok=True)
    started=time.time(); data={**run_store.redact({k:v for k,v in payload.items() if k in ('kind','path','command','select','catalog','schema','parameters','name','workflow_execution_id','flow_id','task_id','task_path','attempt')}),
        'id':run_id,'status':'QUEUED','started':started,'timezone':timezone_name()}
    data['name']=data.get('name') or ((payload.get('path','dbt')+' · '+payload.get('command','build')) if payload.get('kind')=='dbt' else payload.get('path') or payload.get('kind'))
    record(directory,data)
    with LOCK:
        data.update(status='RUNNING',queued_at=started,started=time.time());started=data['started'];record(directory,data)
        kind=payload.get('kind','unknown')
        try:
            kind=payload['kind']; timeout=int(payload.get('timeout',7200))
            if not 1<=timeout<=86400: raise ValueError('Timeout must be 1..86400 seconds')
            deadline=time.monotonic()+timeout
            env=os.environ.copy(); env['LAKEHOUSE_PARAMETERS']=json.dumps(payload.get('parameters',{}))
            env['LAKEHOUSE_RUN_DIR']=str(directory);env['LAKEHOUSE_SPARK_RUN']=run_id
            env['PYSPARK_SUBMIT_ARGS']=f"--driver-memory {settings()['driver_memory']} pyspark-shell"
            if kind=='notebook':
                source=safe_path(payload['path'],'.ipynb')
                if not source.is_file(): raise ValueError('Notebook not found')
                snapshot_source(payload,directory,source)
                cmd=[sys.executable,'/opt/lakehouse/execute_notebook.py',str(directory/'source.ipynb'),str(directory/source.name)]
                cwd=source.parent
                env['LAKEHOUSE_NOTEBOOK_CWD']=str(cwd)
            elif kind=='dbt':
                cwd=safe_path(payload.get('path','dbt'))
                destination=project_destination(cwd,payload,settings())
                command=payload.get('command','build')
                if command not in ('build','run','test','seed','snapshot','docs','deps','debug'): raise ValueError('Invalid dbt command')
                prepare_dbt_project(cwd)
                if destination['mode']=='project': ensure_schema_macro(cwd)
                snapshot_source(payload,directory,cwd)
                cat=destination['catalog']
                data.update(catalog=cat,dbt_destination=destination)
                record(directory,data)
                if command!='deps':
                    data['stage']='Waiting for Spark SQL'; record(directory,data)
                    wait_for_sql_ready(min(120,timeout))
                    ensure_dbt_namespace(destination)
                parameters={k:v for k,v in spark_conf().items() if k.startswith('spark.sql.catalog.')}
                parameters['spark.sql.defaultCatalog']=cat
                profile={'lakehouse':{'target':'dev','outputs':{'dev':{'type':'spark','method':'thrift',
                    'host':os.getenv('SQL_HOST','sql'),'port':10000,'auth':'NOSASL','user':'lakehouse',
                    'schema':destination['session_schema'],'threads':1,
                    'server_side_parameters':{'set:hivevar:'+key:value for key,value in parameters.items()}}}}}
                (directory/'profiles.yml').write_text(yaml.safe_dump(profile))
                env['DBT_TARGET_PATH']=str(directory/'target')
                env['DBT_LOG_PATH']=str(directory/'dbt-logs')
                cmd=['dbt',command,'--log-format','json','--no-use-colors','--profiles-dir',str(directory),'--project-dir',str(cwd)]
                if command=='docs': cmd.insert(2,'generate')
                if payload.get('select') and command in ('build','run','test','snapshot'): cmd+=['--select',payload['select']]
                if payload.get('parameters'): cmd+=['--vars',json.dumps(payload['parameters'])]
                if destination['mode']=='project':
                    spec={'command':command,'destination':destination,'run_dir':str(directory),
                          'project_dir':str(cwd),'parameters':payload.get('parameters',{}),'select':payload.get('select','')}
                    (directory/'dbt-job.json').write_text(json.dumps(spec))
                    cmd=[sys.executable,str(Path(__file__).with_name('dbt_job.py')),str(directory/'dbt-job.json')]
            elif kind=='sql':
                snapshot_source(payload,directory)
                data['stage']='Waiting for Spark SQL'; record(directory,data)
                wait_for_sql_ready(min(120,timeout))
                cwd=ROOT
                (directory/'query.sql').write_text(payload['sql'])
                cmd=[sys.executable,'/opt/lakehouse/sql_job.py',str(directory/'query.sql'),str(directory/'result.json')]
            else: raise ValueError('Task must be notebook, dbt or sql')
            data['stage']='Running '+kind; record(directory,data)
            remaining=deadline-time.monotonic()
            if remaining<=0: raise TimeoutError('Task timeout reached while waiting for Spark SQL or preparing the task')
            data['invocation']=run_store.redact(cmd);record(directory,data)
            code=capture_process(cmd,cwd,env,directory,remaining)
            data.update(status='SUCCESS' if code==0 else 'TIMED_OUT' if code==124 else 'FAILED',exit_code=code)
            if code!=0: data['error']=command_error(kind,code,directory/'execution.log')
        except Exception as exc: data.update(status='FAILED',error=str(exc))
        if kind=='sql' and (directory/'result.json').exists():run_store.atomic_json(directory/'outputs.json',read_json(directory/'result.json'))
        data.update(stage='Completed' if data['status']=='SUCCESS' else 'Execution stopped',ended=time.time(),duration=round(time.time()-started,2),output=f'runs/{run_id}',outputs=run_store.redact(read_json(directory/'outputs.json')))
        record(directory,data)
    return data


def ensure_dbt_namespace(destination):
    from urllib.error import HTTPError
    cat=destination['catalog']
    if destination['mode']=='project':
        try: uc('GET','catalogs/'+cat)
        except HTTPError as error:
            if error.code!=404: raise
            raise ValueError(f'Catalog {cat} does not exist. Create it in Catalog before running this dbt project.') from error
        # The patched dbt child connects to a declared schema, never USE default.
        schemas=[destination['session_schema']]
    else:
        # Preserve the historical adapter/session behavior for unmigrated projects.
        schemas=['default']
    for schema in schemas:
        try: uc('GET','schemas/'+cat+'.'+schema)
        except HTTPError as error:
            if error.code!=404: raise
            try: uc('POST','schemas',{'name':schema,'catalog_name':cat})
            except HTTPError as conflict:
                if conflict.code!=409: raise

@app.get('/health')
def health(): return {'status':'ok'}

@app.get('/maintenance',dependencies=[Depends(auth)])
def maintenance_preview():
    from retention import cleanup
    return cleanup(False)

@app.post('/maintenance',dependencies=[Depends(auth)])
def maintenance_apply(payload:dict):
    from retention import cleanup,LOCK as CLEAN_LOCK
    with CLEAN_LOCK:return cleanup(True)

@app.post('/run',dependencies=[Depends(auth)])
def run(payload:dict):
    if 'payload_b64' in payload:
        import base64
        decoded=json.loads(base64.b64decode(payload['payload_b64']))
        context=payload.get('context',{});decoded.update(workflow_execution_id=context.get('execution_id'),flow_id=context.get('flow_id'),task_id=context.get('task_id'))
        payload=decoded
    result=execute(payload,uuid.uuid4().hex)
    if result['status']!='SUCCESS': raise HTTPException(500,result)
    return result

@app.post('/jobs',dependencies=[Depends(auth)])
def start(payload:dict):
    run_id=uuid.uuid4().hex; directory=RUNS/run_id; directory.mkdir()
    record(directory,{'id':run_id,'status':'QUEUED','kind':payload.get('kind'),'started':time.time()})
    POOL.submit(execute,payload,run_id)
    return {'id':run_id,'status':'QUEUED'}

@app.get('/history/{category}',dependencies=[Depends(auth)])
def history_get(category:str,search:str='',kind:str='',status:str='',from_time:str='',to_time:str='',page:int=1,page_size:int=25):
    try:
        warning=''
        if category=='workflows':
            from workflow_history import sync
            try:sync(kestra)
            except Exception as error:warning='Kestra is unavailable; showing cached history. '+str(error)
        result=run_store.history('workflow' if category=='workflows' else 'run',search,kind,status,from_time,to_time,page,page_size)
        if warning:result['warning']=warning
        return result
    except Exception as error:raise HTTPException(400,str(error))

@app.get('/runs/{run_id}',dependencies=[Depends(auth)])
def run_detail(run_id:str):return run_store.detail(run_id)

@app.get('/workflow-history/{execution_id}',dependencies=[Depends(auth)])
def workflow_detail(execution_id:str):
    from workflow_history import detail
    return detail(execution_id,kestra)

@app.get('/runs/{run_id}/logs',dependencies=[Depends(auth)])
def run_logs(run_id:str,cursor:str='',limit:int=100,level:str='',search:str='',source:str=''):
    return run_store.log_page(run_id,cursor,limit,level,search,source)

@app.get('/runs/{run_id}/models',dependencies=[Depends(auth)])
def run_models(run_id:str):return run_store.dbt_models(run_id)

@app.get('/runs/{run_id}/cells',dependencies=[Depends(auth)])
def run_cells(run_id:str,page:int=1,page_size:int=25):return run_store.notebook_cells(run_id,page,page_size)

@app.get('/docs/latest',dependencies=[Depends(auth)])
def docs_latest(project:str='dbt'):
    try: destination=project_destination(safe_path(project),{},settings())
    except ValueError as error: raise HTTPException(400,str(error))
    with run_store.connect() as connection:
        rows=[json.loads(r['meta']) for r in connection.execute("SELECT meta FROM history WHERE category='run' AND kind='dbt' AND status='SUCCESS' AND json_extract(meta,'$.path')=? ORDER BY started DESC",(project,))]
    for row in rows:
        if destination['mode']=='project' and (row.get('dbt_destination',{}).get('mode')!='project' or row.get('catalog')!=destination['catalog']):continue
        if row.get('path')==project and (RUNS/row['id']/'target/index.html').exists():return {'run_id':row['id']}
    return {'run_id':None}

@app.post('/workflow/execute',dependencies=[Depends(auth)])
def workflow_run(payload:dict):
    import base64
    from workflow_runtime import execute_workflow
    flow=json.loads(base64.b64decode(payload['flow_b64']))
    inputs=json.loads(base64.b64decode(payload.get('inputs_b64','e30=')))
    result=execute_workflow(flow,payload['execution_id'],inputs.get('parameters',inputs),execute)
    if result['status']!='SUCCESS':raise HTTPException(500,{'execution_id':result['id'],'error':result.get('error','A workflow task failed; open Workflow Run History')})
    return {'id':result['id'],'status':result['status'],'task_count':len(result.get('tasks',[])),
            'details':'Open Workflow Run History for notebook outputs and individual iterations.'}

@app.get('/jobs',dependencies=[Depends(auth)])
def jobs():
    result=[]
    for path in sorted(RUNS.glob('*/run.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:100]:
        result.append(json.loads(path.read_text()))
    return result

@app.get('/jobs/{run_id}',dependencies=[Depends(auth)])
def job(run_id:str):
    if not __import__('re').fullmatch('[a-f0-9]{32}',run_id): raise HTTPException(400,'Invalid run ID')
    directory=RUNS/run_id
    if not (directory/'run.json').exists(): raise HTTPException(404,'Run not found')
    result=json.loads((directory/'run.json').read_text())
    log=directory/'execution.log'
    if log.exists():
        with log.open('rb') as f: f.seek(max(0,log.stat().st_size-20000)); result['log']=f.read().decode(errors='replace')
    return result

@app.post('/sql',dependencies=[Depends(auth)])
def sql(payload:dict):
    try:
        with LOCK: return sql_query(payload['sql'],payload.get('catalog'))
    except Exception as e: raise HTTPException(400,str(e))

@app.get('/config',dependencies=[Depends(auth)])
def config_get(): return settings()


@app.post('/tables/delete',dependencies=[Depends(auth)])
def tables_delete(payload:dict):
    from catalog_actions import drop_tables
    try:
        with LOCK:return drop_tables(payload,uc,sql_query)
    except ValueError as error:raise HTTPException(400,str(error))

@app.get('/sql/status',dependencies=[Depends(auth)])
def sql_status(): return read_json(SQL_CONTROL/'status.json') or {'state':'UNKNOWN'}


@app.post('/views',dependencies=[Depends(auth)])
def views_create(payload:dict):
    from view_actions import create_view
    try:
        with LOCK:return create_view(payload,uc,sql_query)
    except Exception as error:raise HTTPException(400,str(error))


@app.post('/views/delete',dependencies=[Depends(auth)])
def views_delete(payload:dict):
    from view_actions import drop_views
    try:
        with LOCK:return drop_views(payload,uc,sql_query)
    except ValueError as error:raise HTTPException(400,str(error))

def validated_config(payload):
    import re
    identifier(payload['default_catalog']); identifier(payload['default_schema'])
    if not isinstance(payload['driver_memory'],str) or not re.fullmatch('[1-9][0-9]*[gm]',payload['driver_memory']):
        raise ValueError('Memory example: 4g')
    threads=str(payload['threads'])
    if threads!='auto' and (not threads.isdigit() or not 1<=int(threads)<=512): raise ValueError('Invalid CPU count')
    shuffle=int(payload['shuffle_partitions'])
    if not 1<=shuffle<=10000: raise ValueError('Invalid shuffle partitions')
    extra=payload.get('extra',{})
    if not isinstance(extra,dict): raise ValueError('Extra Spark config must be a JSON object')
    for key,value in extra.items():
        if not isinstance(key,str) or not key.startswith(('spark.sql.','spark.hadoop.','spark.jars.')):
            raise ValueError('Only spark.sql.*, spark.hadoop.* and spark.jars.* are supported')
        if not isinstance(value,(str,int,float,bool)):
            raise ValueError('Each Spark config value must be a string, number or boolean')
    return {'threads':threads,'driver_memory':payload['driver_memory'],'shuffle_partitions':shuffle,
            'default_catalog':payload['default_catalog'],'default_schema':payload['default_schema'],'extra':extra}


def restart_sql(run_id):
    directory=RUNS/run_id
    data=read_json(directory/'run.json')
    started=time.time()
    try:
        # Existing SQL requests/jobs finish before the process is restarted.
        with LOCK:
            data.update(status='RUNNING',stage='Restarting Spark SQL')
            record(directory,data)
            write_json(SQL_CONTROL/'request.json',{'id':run_id,'created':time.time()})
            deadline=time.monotonic()+660
            while True:
                result=read_json(SQL_CONTROL/'status.json')
                if result.get('id')==run_id:
                    stage=result.get('state','STARTING')
                    if stage=='READY': break
                    if stage in ('FAILED','STOPPED'):
                        raise RuntimeError(result.get('error','Spark SQL stopped during restart'))
                if time.monotonic()>deadline:
                    raise TimeoutError('SQL restart timed out; check the SQL container logs and supervisor')
                time.sleep(1)
            sql_query('SELECT 1')
        data.update(status='SUCCESS',stage='Spark SQL ready')
    except Exception as error:
        data.update(status='FAILED',stage='Spark SQL restart failed',error=str(error))
    data.update(duration=round(time.time()-started,2))
    record(directory,data)


@app.post('/config',dependencies=[Depends(auth)])
def config_set(payload:dict):
    global SQL_RESTART_ID
    try:
        config=validated_config(payload)
        if not isinstance(payload.get('restart_sql',False),bool): raise ValueError('restart_sql must be boolean')
    except (ValueError,TypeError,KeyError) as error: raise HTTPException(400,str(error))
    with CONFIG_LOCK:
        if SQL_RESTART_ID and read_json(RUNS/SQL_RESTART_ID/'run.json').get('status') in ('QUEUED','RUNNING'):
            raise HTTPException(409,'Spark SQL restart is already in progress; wait before saving again')
        SETTINGS.parent.mkdir(parents=True,exist_ok=True)
        temp=SETTINGS.with_suffix('.tmp'); temp.write_text(json.dumps(config)); temp.replace(SETTINGS)
        result={'saved':True,'apply':'Saved for new Spark sessions'}
        if payload.get('restart_sql'):
            run_id=uuid.uuid4().hex; directory=RUNS/run_id; directory.mkdir()
            record(directory,{'id':run_id,'kind':'cluster_restart','status':'QUEUED',
                              'stage':'Waiting for running SQL jobs to finish','started':time.time()})
            SQL_RESTART_ID=run_id
            RESTART_POOL.submit(restart_sql,run_id)
            result['restart_job']=run_id
        return result

def kestra(method,path,**kwargs):
    with httpx.Client(timeout=30,auth=(os.environ['KESTRA_USER'],os.environ['KESTRA_PASSWORD'])) as client:
        response=client.request(method,os.getenv('KESTRA_URL','http://kestra:8080')+'/api/v1/main/'+path,**kwargs)
        if response.is_error: raise HTTPException(502,response.text[:2000])
        return response.json() if response.content else {}

@app.get('/flows',dependencies=[Depends(auth)])
def flows(): return [json.loads(p.read_text()) for p in FLOWS.glob('*.json')]

@app.post('/flows',dependencies=[Depends(auth)])
def save_flow(payload:dict):
    try: compiled=compile_flow(payload)
    except (ValueError,KeyError) as e: raise HTTPException(400,str(e))
    text=yaml.safe_dump(compiled,sort_keys=False)
    # Update existing flows; create only when the lookup reports 404.
    with httpx.Client(timeout=30,auth=(os.environ['KESTRA_USER'],os.environ['KESTRA_PASSWORD'])) as c:
        base=os.getenv('KESTRA_URL','http://kestra:8080')+'/api/v1/main/flows'
        lookup=c.get(base+'/lakehouse.v3/'+compiled['id'])
        if lookup.status_code not in (200,404): raise HTTPException(502,lookup.text[:2000])
        r=c.post(base,content=text,headers={'Content-Type':'application/x-yaml'}) if lookup.status_code==404 else c.put(base+'/lakehouse.v3/'+compiled['id'],content=text,headers={'Content-Type':'application/x-yaml'})
        if r.is_error: raise HTTPException(502,r.text[:3000])
    path=FLOWS/(compiled['id']+'.json'); tmp=path.with_suffix('.tmp'); tmp.write_text(json.dumps(payload)); tmp.replace(path)
    path.with_suffix('.yml').write_text(text)
    return {'saved':True,'yaml':text}

@app.post('/flows/{flow_id}/execute',dependencies=[Depends(auth)])
def execute_flow(flow_id:str,payload:dict={}):
    args={}
    if payload.get('parameters'):args['files']={'parameters':(None,json.dumps(payload['parameters']))}
    return kestra('POST','executions/lakehouse.v3/'+identifier(flow_id),**args)

@app.get('/executions',dependencies=[Depends(auth)])
def executions(): return kestra('GET','executions/search',params={'namespace':'lakehouse.v3','page':1,'size':30})

if __name__=='__main__':
    run_store.import_runs()
    run_store.recover_interrupted()
    from retention import start as start_retention,start_kestra_retention
    start_retention();start_kestra_retention()
    import uvicorn
    uvicorn.run(app,host='0.0.0.0',port=8765)
