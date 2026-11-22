import json,os,shutil,threading,time
from pathlib import Path
from run_store import atomic_json,process_line,redact

def snapshot_source(payload,directory,source=None):
    data={'kind':payload.get('kind'),'path':payload.get('path'),'files':[]}
    if payload.get('kind')=='sql':data['files']=[{'path':'query.sql','code':payload.get('sql','')}]
    elif source and source.suffix=='.ipynb':
        shutil.copy2(source,directory/'source.ipynb')
        notebook=json.loads(source.read_text());data['files']=[{'path':source.name,'code':'\n\n'.join(''.join(c.get('source',[])) for c in notebook.get('cells',[]) if c.get('cell_type')=='code')}]
    elif source:
        total=0
        for path in sorted(source.rglob('*')):
            relative=path.relative_to(source)
            if any(p.startswith('.') or p in ('target','logs','dbt_packages') for p in relative.parts):continue
            if not path.is_file() or path.suffix not in ('.sql','.yml','.yaml','.md') or path.name=='profiles.yml':continue
            size=path.stat().st_size
            if size>500000 or total+size>3000000:continue
            total+=size;data['files'].append({'path':relative.as_posix(),'code':path.read_text(errors='replace')})
    atomic_json(directory/'source.json',redact(data))

def capture_process(command,cwd,env,directory,timeout):
    import signal,subprocess
    maximum=int(os.getenv('RUN_LOG_MAX_MB','25'))*1024*1024
    process=subprocess.Popen(command,cwd=cwd,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
    def reader():
        written=0;limited=False
        with (directory/'execution.log').open('w',encoding='utf-8') as stream:
            while True:
                raw=process.stdout.readline(1024*1024)
                if not raw:break
                line=redact(raw.decode(errors='replace'))
                if written+len(line.encode())<=maximum:
                    stream.write(line);stream.flush();written+=len(line.encode());process_line(directory,line)
                elif not limited:
                    limited=True;process_line(directory,'Log size limit reached; remaining process output is discarded')
    thread=threading.Thread(target=reader,daemon=True);thread.start()
    deadline=time.monotonic()+timeout;code=None
    maximum_artifacts=max(1,int(os.getenv('RUN_ARTIFACT_MAX_MB','1024')))*1024*1024
    try:
        while code is None:
            try:code=process.wait(timeout=max(.01,min(5,deadline-time.monotonic())))
            except subprocess.TimeoutExpired:
                amount=0
                for path in directory.rglob('*'):
                    try:
                        if path.is_file() and not path.is_symlink():amount+=path.stat().st_size
                    except FileNotFoundError:pass
                if time.monotonic()>=deadline:code=124
                elif amount>maximum_artifacts:
                    code=125;process_line(directory,'ERROR: Run artifact size limit exceeded; increase RUN_ARTIFACT_MAX_MB if needed')
    finally:
        if process.poll() is None:
            try:os.killpg(process.pid,signal.SIGTERM);process.wait(timeout=5)
            except (subprocess.TimeoutExpired,ProcessLookupError):
                try:os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                process.wait()
        thread.join(timeout=10);process.stdout.close()
    return code
