"""Bounded operational artifacts. Never prune warehouses, metastores or live runs."""
import json,os,shutil,threading,time
from config import RUNS,RUNTIME
import run_store
LOCK=threading.Lock()

def size(path):
    return sum(p.stat().st_size for p in path.rglob('*') if p.is_file() and not p.is_symlink())

def cleanup(apply=False,now=None):
    now=now or time.time()
    days=max(1,int(os.getenv('RUN_RETENTION_DAYS','30')))
    maximum=max(.01,float(os.getenv('RUN_STORAGE_MAX_GB','10')))*1024**3
    rows=[]
    for directory in RUNS.iterdir():
        if directory.is_symlink() or not directory.is_dir():continue
        meta=run_store.read_json(directory/'run.json')
        if meta.get('status') not in run_store.TERMINAL:continue
        rows.append((float(meta.get('ended') or meta.get('started') or now),directory,meta,size(directory)))
    rows.sort(key=lambda row:row[0]);total=sum(row[3] for row in rows)
    selected=[]
    for ended,directory,meta,amount in rows:
        if ended>=now-days*86400 and total<=maximum:continue
        selected.append({'id':meta['id'],'bytes':amount,'reason':'age' if ended<now-days*86400 else 'quota'});total-=amount
        if apply:
            # Recheck terminal state immediately before removal.
            latest=run_store.read_json(directory/'run.json')
            if latest.get('status') not in run_store.TERMINAL:continue
            if directory.resolve().parent!=RUNS.resolve():raise ValueError('Unsafe cleanup path')
            meta.update(artifacts_expired=True);run_store.upsert('run',meta)
            shutil.rmtree(directory)
    temporary=[]
    # Other containers have separate PID namespaces. Never infer that their
    # Spark processes are dead from a PID lookup inside the runner container.
    for service in ('runner',):
        root=RUNTIME/service/'spark-tmp'
        if not root.exists():continue
        for path in root.iterdir():
            if path.is_symlink() or not path.is_dir() or path.stat().st_mtime>now-86400:continue
            meta=run_store.read_json(RUNS/path.name/'run.json')
            if meta and meta.get('status') not in run_store.TERMINAL:continue
            if path.name.isdigit() and len(path.name)<=10:
                try:os.kill(int(path.name),0);continue
                except (ProcessLookupError,PermissionError):pass
            temporary.append(str(path))
            if apply and path.resolve().parent==root.resolve():shutil.rmtree(path)
    if apply:
        history_days=max(days,int(os.getenv('HISTORY_RETENTION_DAYS','365')))
        with run_store.connect() as connection:
            connection.execute('DELETE FROM history WHERE ended<? AND status IN ('+','.join('?' for _ in run_store.TERMINAL)+')',[now-history_days*86400,*run_store.TERMINAL])
        for path in (RUNTIME/'workflows').glob('*/execution.json'):
            data=run_store.read_json(path)
            if data.get('status') in run_store.TERMINAL and data.get('ended',now)<now-history_days*86400:shutil.rmtree(path.parent)
    return {'apply':apply,'runs':selected,'bytes':sum(r['bytes'] for r in selected),'remaining_terminal_bytes':total,
            'temporary':temporary,'retention_days':days,'storage_max_gb':maximum/1024**3,
            'history_retention_days':int(os.getenv('HISTORY_RETENTION_DAYS','365'))}

def start():
    def maintain():
        while True:
            try:
                with LOCK:cleanup(True)
            except Exception as error:print('Runtime cleanup:',error,flush=True)
            time.sleep(3600)
    threading.Thread(target=maintain,daemon=True).start()

def install_kestra_retention():
    """Use Kestra's purge API task so its database and internal files agree."""
    import httpx,yaml
    from config import timezone_name
    days=max(1,int(os.getenv('KESTRA_RETENTION_DAYS','30')))
    flow={'id':'runtime_retention','namespace':'lakehouse.maintenance','description':'Managed operational retention; excludes active executions and lakehouse tables.',
          'tasks':[{'id':'purge','type':'io.kestra.plugin.core.execution.PurgeExecutions',
                    'endDate':"{{ now() | dateAdd(-"+str(days)+", 'DAYS') }}",'namespace':'lakehouse.v3',
                    'states':['SUCCESS','FAILED','WARNING','KILLED','CANCELLED']}],
          'triggers':[{'id':'daily','type':'io.kestra.plugin.core.trigger.Schedule','cron':'20 3 * * *','timezone':timezone_name()}]}
    body=yaml.safe_dump(flow,sort_keys=False)
    with httpx.Client(timeout=30,auth=(os.environ['KESTRA_USER'],os.environ['KESTRA_PASSWORD'])) as client:
        base=os.getenv('KESTRA_URL','http://kestra:8080')+'/api/v1/main/flows'
        old=client.get(base+'/lakehouse.maintenance/runtime_retention',params={'source':True})
        if old.status_code not in (200,404):old.raise_for_status()
        if old.status_code==200 and yaml.safe_load(old.json().get('source','{}'))==flow:return
        valid=client.post(base+'/validate',content=body,headers={'Content-Type':'application/x-yaml'});valid.raise_for_status()
        if any(item.get('constraints') or item.get('violations') for item in valid.json()):raise ValueError('Kestra retention flow validation failed')
        response=client.post(base,content=body,headers={'Content-Type':'application/x-yaml'}) if old.status_code==404 else client.put(base+'/lakehouse.maintenance/runtime_retention',content=body,headers={'Content-Type':'application/x-yaml'})
        response.raise_for_status()

def start_kestra_retention():
    def install():
        for attempt in range(60):
            try:install_kestra_retention();return
            except Exception as error:
                if attempt==59:print('Could not configure Kestra retention:',error,flush=True)
                time.sleep(15)
    threading.Thread(target=install,daemon=True).start()
