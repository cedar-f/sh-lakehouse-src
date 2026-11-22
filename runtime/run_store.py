"""Durable run metadata, bounded log reads and timezone-aware history queries."""
import base64
import json
import os
import re
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from config import ROOT, RUNTIME, RUNS, timezone_name

DB = RUNTIME / 'history.sqlite'
TERMINAL = {'SUCCESS', 'FAILED', 'WARNING', 'CANCELLED', 'KILLED', 'TIMED_OUT', 'INTERRUPTED', 'SKIPPED', 'ARCHIVED'}
ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')
SECRET_KEY = re.compile(r'password|secret|token|access.?key|authorization', re.I)
_schema_lock = threading.Lock()


def redact(value):
    if isinstance(value, dict):
        return {k: '[REDACTED]' if SECRET_KEY.search(str(k)) else redact(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    if isinstance(value, str):
        for key, secret in os.environ.items():
            if len(secret) > 5 and SECRET_KEY.search(key):
                value = value.replace(secret, '[REDACTED]')
        return ANSI.sub('', value)
    return value


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(data, default=str, ensure_ascii=False), encoding='utf-8')
    temporary.replace(path)


def read_json(path, default=None):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {} if default is None else default


def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB, timeout=15)
    connection.row_factory = sqlite3.Row
    with _schema_lock:
        connection.execute('PRAGMA journal_mode=WAL')
        connection.execute('''CREATE TABLE IF NOT EXISTS history (
            category TEXT NOT NULL, id TEXT NOT NULL, name TEXT NOT NULL,
            kind TEXT NOT NULL, status TEXT NOT NULL, started REAL NOT NULL,
            ended REAL, kinds TEXT NOT NULL DEFAULT '', meta TEXT NOT NULL,
            PRIMARY KEY(category,id))''')
        connection.execute('CREATE INDEX IF NOT EXISTS history_time ON history(category,started DESC)')
        connection.execute('CREATE INDEX IF NOT EXISTS history_status ON history(category,status,kind)')
        connection.commit()
    return connection


def upsert(category, data):
    item = dict(data)
    item['name'] = item.get('name') or item.get('path') or item.get('kind') or item['id']
    item['started'] = float(item.get('started') or item.get('queued_at') or time.time())
    item.setdefault('kind', 'workflow' if category == 'workflow' else 'unknown')
    item.setdefault('status', 'UNKNOWN')
    kinds = ',' + ','.join(sorted(set(item.get('types') or [item['kind']]))) + ','
    with connect() as connection:
        connection.execute('''INSERT INTO history(category,id,name,kind,status,started,ended,kinds,meta)
          VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(category,id) DO UPDATE SET
          name=excluded.name,kind=excluded.kind,status=excluded.status,started=excluded.started,
          ended=excluded.ended,kinds=excluded.kinds,meta=excluded.meta''',
          (category,item['id'],item['name'],item['kind'],item['status'],item['started'],item.get('ended'),
           kinds,json.dumps(item,default=str,ensure_ascii=False)))
    return item


def write_run(directory, data):
    atomic_json(directory / 'run.json', data)
    upsert('run', data)


def run_directory(run_id):
    if not re.fullmatch('[a-f0-9]{32}', run_id):
        raise ValueError('Invalid run ID')
    directory = RUNS / run_id
    if not (directory / 'run.json').is_file():
        raise FileNotFoundError('Run not found')
    return directory


def read_run(run_id):
    directory = run_directory(run_id)
    data = read_json(directory / 'run.json')
    return data


def legacy_metadata(directory):
    data = read_json(directory / 'run.json')
    if not data.get('id'):
        return None
    results = read_json(directory / 'target' / 'run_results.json')
    args = results.get('args', {})
    data.setdefault('ended', data.get('started', 0) + data['duration'] if data.get('duration') is not None else None)
    data.setdefault('timezone', 'UTC')
    if data.get('kind') == 'dbt':
        project = args.get('project_dir', '')
        if project.startswith('/workspace/'):
            data.setdefault('path', project[len('/workspace/'):])
        data.setdefault('command', 'docs' if (directory / 'target' / 'index.html').exists() else args.get('which', 'build'))
        data.setdefault('select', args.get('select') or '')
        data.setdefault('name', (data.get('path') or 'dbt') + ' · ' + data['command'])
    elif data.get('kind') == 'notebook':
        notebooks = [p for p in directory.glob('*.ipynb') if p.name != 'source.ipynb']
        if notebooks:
            data.setdefault('name', notebooks[0].name)
    return data


def import_runs():
    RUNS.mkdir(parents=True, exist_ok=True)
    for directory in RUNS.iterdir():
        if directory.is_dir() and (directory / 'run.json').exists():
            data = legacy_metadata(directory)
            if data:
                upsert('run', data)

def recover_interrupted():
    """A single runner owns this volume. Never silently replay work after reboot."""
    now=time.time()
    for path in RUNS.glob('*/run.json'):
        data=read_json(path)
        if data.get('status') not in ('QUEUED','RUNNING'):continue
        data.update(status='INTERRUPTED',ended=now,interrupted_at=now,stage='Interrupted by runner restart',
                    error='Runner restarted before completion. Review partial outputs before retrying.')
        data['duration']=round(max(0,now-data.get('started',now)),2)
        write_run(path.parent,data)
        progress=path.parent/'notebook-progress.json';notebook=read_json(progress)
        if notebook:
            for cell in notebook.get('cells',[]):
                meta=cell.get('metadata',{}).get('lakehouse',{})
                if meta.get('status')=='RUNNING':meta.update(status='INTERRUPTED',ended=now)
            atomic_json(progress,notebook)
    for path in (RUNTIME/'workflows').glob('*/execution.json'):
        data=read_json(path)
        if data.get('status') not in ('QUEUED','RUNNING'):continue
        data.update(status='INTERRUPTED',ended=now,error='Runner restarted; partial task outputs were preserved.')
        for task in data.get('tasks',[]):
            if task.get('status') in ('RUNNING','QUEUED'):task.update(status='INTERRUPTED',ended=now)
        atomic_json(path,data);upsert('workflow',{k:v for k,v in data.items() if k not in ('tasks','definition')})


def parse_time(value, upper=False):
    if not value:
        return None
    text = str(value).strip().replace('Z', '+00:00')
    date = datetime.fromisoformat(text)
    if date.tzinfo is None:
        local = ZoneInfo(timezone_name())
        date = date.replace(tzinfo=local)
        if date.astimezone(timezone.utc).astimezone(local).replace(tzinfo=None) != date.replace(tzinfo=None):
            raise ValueError('The selected local time does not exist in this timezone')
    return date.timestamp()


def history(category='run', search='', kind='', status='', from_time='', to_time='', page=1, page_size=25):
    page, page_size = int(page), int(page_size)
    if page < 1 or page_size not in (10, 25, 50, 100, 200):
        raise ValueError('Page must be positive; page size must be 10, 25, 50, 100 or 200')
    if len(search) > 200:
        raise ValueError('Search is too long')
    start, end = parse_time(from_time), parse_time(to_time, True)
    if start is not None and end is not None and start > end:
        raise ValueError('From date/time must be before To date/time')
    clauses, values = ['category=?'], [category]
    if search:
        clauses.append('(instr(lower(name),lower(?))>0 OR instr(lower(id),lower(?))>0)')
        values += [search, search]
    if kind:
        clauses.append('instr(kinds,?)>0'); values.append(',' + kind + ',')
    if status:
        clauses.append('status=?'); values.append(status.upper())
    if start is not None:
        clauses.append('started>=?'); values.append(start)
    if end is not None:
        clauses.append('started<=?'); values.append(end)
    where = ' AND '.join(clauses)
    with connect() as connection:
        total = connection.execute('SELECT count(*) FROM history WHERE ' + where, values).fetchone()[0]
        rows = connection.execute('SELECT meta FROM history WHERE '+where+' ORDER BY started DESC,id DESC LIMIT ? OFFSET ?',
                                  [*values, page_size, (page-1)*page_size]).fetchall()
    return {'items': [redact(json.loads(row['meta'])) for row in rows], 'total': total,
            'page': page, 'page_size': page_size, 'pages': max(1, (total+page_size-1)//page_size), 'timezone': timezone_name()}


def event_file(directory, source='process'):
    return directory / (source + '.events.jsonl')


def append_event(directory, message, level='INFO', source='process', **fields):
    record = {'timestamp':time.time(), 'level':level.upper(), 'source':source,
              'message':redact(str(message))[:16000], **fields}
    path = event_file(directory, source)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size>=int(os.getenv('RUN_LOG_MAX_MB','25'))*1024*1024:return
    with path.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(redact(record),default=str,ensure_ascii=False)+'\n')


def process_line(directory, line):
    text = ANSI.sub('', line.rstrip('\r\n'))
    level, fields = 'INFO', {}
    try:
        value = json.loads(text)
        if isinstance(value, dict) and isinstance(value.get('info'), dict):
            info, data = value['info'], value.get('data', {})
            text, level = info.get('msg',text), info.get('level','info').upper()
            node = data.get('node_info') or {}
            if node:
                fields['model'] = node.get('unique_id') or node.get('node_name')
                fields['node'] = node
            fields['source_type'] = 'dbt'
    except ValueError:
        if re.search(r'\b(ERROR|Exception|Traceback)\b', text): level='ERROR'
        elif re.search(r'\bWARN(?:ING)?\b', text): level='WARN'
    append_event(directory,text,level,**fields)


def log_page(run_id, cursor='', limit=100, level='', search='', source=''):
    directory = run_directory(run_id)
    limit = max(1,min(int(limit),500))
    try:
        offsets = json.loads(base64.urlsafe_b64decode(cursor + '='*(-len(cursor)%4))) if cursor else {}
        if not isinstance(offsets,dict) or any(not isinstance(v,int) or v<0 for v in offsets.values()):raise ValueError()
    except Exception:
        raise ValueError('Invalid log cursor')
    paths = {key:event_file(directory,key) for key in ('process','notebook') if event_file(directory,key).exists()}
    legacy = not paths
    if legacy and (directory/'execution.log').exists(): paths={'legacy':directory/'execution.log'}
    candidates, scanned = [], dict(offsets)
    base_time = read_json(directory/'run.json').get('started',time.time())
    for key,path in paths.items():
        if source and key != source: continue
        position = min(offsets.get(key,0),path.stat().st_size)
        read_bytes = 0
        with path.open('rb') as stream:
            stream.seek(position)
            matched = 0
            while matched < limit and read_bytes < 1024*1024:
                start = stream.tell(); raw = stream.readline(1024*1024)
                if not raw: break
                if not raw.endswith(b'\n') and read_json(directory/'run.json').get('status') not in TERMINAL:
                    break
                finish = stream.tell(); read_bytes += len(raw); scanned[key]=finish
                text=raw.decode(errors='replace').rstrip('\r\n')
                try:record=json.loads(text) if not legacy else None
                except ValueError:record=None
                if not isinstance(record,dict) or 'message' not in record:
                    clean=ANSI.sub('',text)
                    record={'timestamp':base_time,'level':'ERROR' if re.search(r'\bERROR\b',clean) else 'INFO','source':key,'message':clean,'legacy':True}
                    match=re.match(r'(\d{2}:\d{2}:\d{2})\s+(.*)',clean)
                    if match:
                        date=datetime.fromtimestamp(base_time,timezone.utc).strftime('%Y-%m-%d')
                        record.update(timestamp=datetime.fromisoformat(date+'T'+match[1]+'+00:00').timestamp(),message=match[2])
                if level and record.get('level')!=level.upper():continue
                if search and search.casefold() not in str(record.get('message','')).casefold():continue
                record['id']=key+':'+str(start)
                candidates.append((record.get('timestamp',base_time),key,start,finish,redact(record)))
                matched+=1
    candidates.sort(key=lambda row:(row[0],row[1],row[2]))
    selected=candidates[:limit]
    for _,key,start,_,_ in candidates[limit:]:
        scanned[key]=min(scanned.get(key,start),start)
    has_more=any(path.stat().st_size>scanned.get(key,0) for key,path in paths.items() if not source or key==source)
    token=base64.urlsafe_b64encode(json.dumps(scanned).encode()).decode().rstrip('=')
    return {'items':[row[4] for row in selected],'cursor':token,'has_more':has_more,'timezone':timezone_name()}


def artifact_path(run_id, relative):
    directory=run_directory(run_id).resolve()
    path=(directory/relative).resolve()
    if not path.is_relative_to(directory) or not path.is_file() or SECRET_KEY.search(path.name) or path.name=='profiles.yml':
        raise ValueError('Artifact is unavailable')
    return path


def artifacts(run_id):
    directory=run_directory(run_id)
    result=[]
    for path in directory.rglob('*'):
        if not path.is_file() or path.is_symlink() or path.name=='profiles.yml' or SECRET_KEY.search(path.name):continue
        if path.name.endswith('.tmp') or '.git' in path.parts:continue
        result.append({'path':path.relative_to(directory).as_posix(),'size':path.stat().st_size})
        if len(result)>=2000:break
    return result


def dbt_models(run_id):
    directory=run_directory(run_id)
    manifest=read_json(directory/'target/manifest.json')
    results=read_json(directory/'target/run_results.json')
    complete={r['unique_id']:r for r in results.get('results',[])}
    live={}
    path=event_file(directory)
    if path.exists():
        with path.open(encoding='utf-8',errors='replace') as stream:
            for line in stream:
                try:event=json.loads(line)
                except ValueError:continue
                node=event.get('node',{})
                if node.get('unique_id'):live[node['unique_id']]=node
    rows=[]
    for identifier,node in manifest.get('nodes',{}).items():
        if node.get('resource_type') not in ('model','seed','test','snapshot'):continue
        run=complete.get(identifier,{})
        rows.append({'id':identifier,'name':node.get('name'),'type':node.get('resource_type'),
                     'status':str(run.get('status') or live.get(identifier,{}).get('node_status') or 'PENDING').upper(),
                     'duration':run.get('execution_time'),'message':run.get('message',''),
                     'path':node.get('original_file_path'),'sql':node.get('compiled_code') or node.get('raw_code','')})
    if not rows:
        rows=[{'id':key,'name':node.get('node_name',key),'type':node.get('resource_type','model'),
               'status':str(node.get('node_status','RUNNING')).upper()} for key,node in live.items()]
    return redact(rows)


def notebook_cells(run_id, page=1, page_size=25):
    directory=run_directory(run_id)
    notebook=read_json(directory/'notebook-progress.json')
    if not notebook:
        paths=[p for p in directory.glob('*.ipynb') if p.name!='source.ipynb']
        notebook=read_json(paths[0]) if paths else {}
    rows=[]
    for index,cell in enumerate(notebook.get('cells',[])):
        if cell.get('cell_type')!='code' or cell.get('metadata',{}).get('lakehouse_parameters'):continue
        metadata=cell.get('metadata',{}).get('lakehouse',{})
        outputs=cell.get('outputs',[])
        status=metadata.get('status') or ('FAILED' if any(o.get('output_type')=='error' for o in outputs)
                                         else 'SUCCESS' if cell.get('execution_count') is not None else 'PENDING')
        rows.append({'index':index,'number':len(rows)+1,'status':status,'source':''.join(cell.get('source',[])),
                     'started':metadata.get('started'),'ended':metadata.get('ended'),'duration':metadata.get('duration'),
                     'outputs':outputs})
    if int(page)<1 or not 1<=int(page_size)<=100:raise ValueError('Invalid cell page')
    start=(max(1,int(page))-1)*min(100,int(page_size))
    return {'items':redact(rows[start:start+min(100,int(page_size))]),'total':len(rows),'page':int(page)}


def detail(run_id):
    if not (RUNS/run_id/'run.json').exists():
        if not re.fullmatch('[a-f0-9]{32}',run_id):raise ValueError('Invalid run ID')
        with connect() as connection:row=connection.execute("SELECT meta FROM history WHERE category='run' AND id=?",(run_id,)).fetchone()
        if row:return redact({**json.loads(row['meta']),'artifacts_expired':True,'artifacts':[]})
    directory=run_directory(run_id)
    data=legacy_metadata(directory) or read_run(run_id)
    data['artifacts']=artifacts(run_id)
    data['outputs']=read_json(directory/'outputs.json',data.get('outputs',{}))
    data['source']=read_json(directory/'source.json')
    return redact(data)
