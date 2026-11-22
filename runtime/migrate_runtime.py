"""One-time verified migration, run with runtime services stopped and volume mounted."""
import hashlib,json,os,shutil,uuid,time
from config import ROOT,RUNTIME,RUNS

def digest(path):
    result={}
    for p in path.rglob('*'):
        if p.is_symlink():raise RuntimeError('Migration does not follow symbolic links: '+str(p))
        if p.is_file():
            h=hashlib.sha256()
            with p.open('rb') as stream:
                for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
            result[p.relative_to(path).as_posix()]=h.hexdigest()
    return result

def move(source,target):
    if not source.exists() or source.resolve()==target.resolve():return
    if not source.resolve().is_relative_to(ROOT.resolve()):raise RuntimeError('Migration source is outside workspace')
    if not target.resolve().is_relative_to(RUNTIME.parent.resolve()):raise RuntimeError('Migration destination is outside data volume')
    if source.is_dir():
        before=digest(source);shutil.copytree(source,target,dirs_exist_ok=True)
        after=digest(target)
        if any(after.get(p)!=h for p,h in before.items()):raise RuntimeError('Migration verification failed: '+str(source))
        shutil.rmtree(source)
    else:
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
        if source.read_bytes()!=target.read_bytes():raise RuntimeError('Migration verification failed')
        source.unlink()
    print('Migrated and verified:',source.name,flush=True)

if __name__=='__main__':
    RUNS.mkdir(parents=True,exist_ok=True);RUNTIME.mkdir(parents=True,exist_ok=True)
    old=ROOT/'runs'
    if old.exists() and old.resolve()!=RUNS.resolve():
        for source in old.iterdir():move(source,RUNS/source.name)
        old.rmdir()
    # Local Hive tables can contain absolute file locations. Archive only after
    # the administrator has checked SHOW TABLES IN spark_catalog.default.
    marker=ROOT/'.lakehouse/migrate-empty-hive'
    if marker.exists():
        for name in ('metastore_db','spark-warehouse','derby.log'):move(ROOT/name,RUNTIME/'legacy-local-hive'/name)
        marker.unlink()
    elif (ROOT/'metastore_db').exists():print('Kept existing local Hive files; see docs/RUNS_WORKFLOWS.md before archiving.')
    move(ROOT/'.lakehouse/uploads',RUNTIME/'uploads')
    # Preserve artifacts from earlier manual dbt invocations as a retained run.
    if any((ROOT/'dbt'/name).exists() for name in ('target','logs')):
        run_id=uuid.uuid4().hex;directory=RUNS/run_id;directory.mkdir()
        for name,target in [('target','target'),('logs','dbt-logs')]:move(ROOT/'dbt'/name,directory/target)
        (directory/'run.json').write_text(json.dumps({'id':run_id,'name':'Archived dbt workspace artifacts','kind':'artifact_archive','status':'ARCHIVED','started':time.time(),'ended':time.time(),'path':'dbt','stage':'Migrated from workspace; not a new execution'}))
    for path in [RUNTIME.parent,*RUNTIME.parent.rglob('*')]:
        if not path.is_symlink():os.chown(path,1000,1000)
