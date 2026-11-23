"""Shared Spark configuration: notebooks and SQL endpoint use identical catalogs."""
import json
import os
import re
import urllib.request
from pathlib import Path

ROOT = Path(os.environ.get('WORKSPACE_ROOT', '/workspace'))
RUNTIME = Path(os.environ.get('RUNTIME_ROOT', str(ROOT / '.lakehouse' / 'runtime')))
RUNS = Path(os.environ.get('RUNS_ROOT', str(ROOT / 'runs')))
SERVICE = os.getenv('LAKEHOUSE_SERVICE', 'notebook')
SETTINGS = ROOT / '.lakehouse' / 'spark.json'
IDENT = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')
PACKAGES = ','.join([
    'org.apache.hadoop:hadoop-aws:3.4.1',
    'io.delta:delta-spark_4.0_2.13:4.3.1',
    'io.unitycatalog:unitycatalog-spark_4.0_2.13:0.7.0',
])

def timezone_name():
    from zoneinfo import ZoneInfo
    name = os.getenv('TZ', 'Asia/Ho_Chi_Minh')
    ZoneInfo(name)
    return name

def identifier(value):
    if not isinstance(value, str) or not IDENT.fullmatch(value):
        raise ValueError('Use letters, digits and underscores; start with a letter or underscore')
    return value

def uc(method, resource, data=None, params=None):
    from urllib.parse import urlencode
    url = os.getenv('UC_URL', 'http://registry:8080') + '/api/2.1/unity-catalog/' + resource
    if params: url += '?' + urlencode(params)
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method,
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer not-used'})
    with urllib.request.urlopen(req, timeout=30) as response:
        return {} if method=='DELETE' else json.load(response)

def all_catalogs():
    items, token = [], None
    while True:
        result = uc('GET', 'catalogs', params={'page_token':token} if token else None)
        items += result.get('catalogs', [])
        token = result.get('next_page_token')
        if not token: return items

def settings():
    result = {'threads':os.getenv('SPARK_THREADS','auto'),
        'driver_memory':os.getenv('SPARK_DRIVER_MEMORY','4g'),
        'shuffle_partitions':int(os.getenv('SPARK_SHUFFLE_PARTITIONS','8')),
        'default_catalog':os.getenv('DEFAULT_CATALOG','lakehouse'),
        'default_schema':os.getenv('DEFAULT_SCHEMA','default'), 'extra':{}}
    if SETTINGS.exists(): result.update(json.loads(SETTINGS.read_text()))
    return result

def spark_conf():
    clean_local_spark_temp()
    s = settings()
    identifier(s['default_catalog']); identifier(s['default_schema'])
    threads = str(s['threads'])
    if threads != 'auto' and (not threads.isdigit() or not 1 <= int(threads) <= 512):
        raise ValueError('threads must be auto or 1..512')
    endpoint = os.getenv('S3_ENDPOINT') or f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"
    conf = {
        'spark.master':'local[*]' if threads == 'auto' else f'local[{threads}]',
        'spark.driver.memory':s['driver_memory'],
        'spark.sql.shuffle.partitions':str(s['shuffle_partitions']),
        'spark.jars.packages':PACKAGES,
        'spark.jars.ivy':str(Path.home()/'.ivy2'),
        # Thrift worker threads also need Delta/UC on the JVM application classpath.
        'spark.driver.extraClassPath':str(Path.home()/'.ivy2'/'jars'/'*'),
        'spark.sql.extensions':'io.delta.sql.DeltaSparkSessionExtension',
        'spark.sql.catalog.spark_catalog':'org.apache.spark.sql.delta.catalog.DeltaCatalog',
        'spark.sql.defaultCatalog':s['default_catalog'],
        'spark.hadoop.fs.s3.impl':'org.apache.hadoop.fs.s3a.S3AFileSystem',
        'spark.hadoop.fs.s3a.impl':'org.apache.hadoop.fs.s3a.S3AFileSystem',
        'spark.hadoop.fs.s3a.endpoint':endpoint,
        'spark.hadoop.fs.s3a.endpoint.region':'auto',
        'spark.hadoop.fs.s3a.path.style.access':'true',
        'spark.hadoop.fs.s3a.connection.ssl.enabled':str(endpoint.startswith('https')).lower(),
        'spark.sql.session.timeZone':timezone_name(),
        'spark.sql.warehouse.dir':(RUNTIME / SERVICE / 'warehouse').resolve().as_uri(),
        'spark.local.dir':str(RUNTIME / SERVICE / 'spark-tmp' / os.getenv('LAKEHOUSE_SPARK_RUN',str(os.getpid()))),
        'spark.hadoop.javax.jdo.option.ConnectionURL':'jdbc:derby:'+str(RUNTIME / SERVICE / 'metastore_db')+';create=true',
        'spark.driver.extraJavaOptions':'-Duser.timezone='+timezone_name()+' -Dderby.stream.error.file='+str(RUNTIME/SERVICE/'derby.log'),
        'spark.executor.extraJavaOptions':'-Duser.timezone='+timezone_name(),
        'spark.redaction.regex':'(?i)secret|password|token|access[.]?key',
    }
    for cat in all_catalogs():
        name = identifier(cat['name'])
        conf.update({f'spark.sql.catalog.{name}':'io.unitycatalog.spark.UCSingleCatalog',
            f'spark.sql.catalog.{name}.uri':os.getenv('UC_URL','http://registry:8080'),
            f'spark.sql.catalog.{name}.auth.type':'static',
            f'spark.sql.catalog.{name}.auth.token':'not-used'})
    allowed = ('spark.sql.', 'spark.hadoop.', 'spark.jars.')
    for key,value in s.get('extra',{}).items():
        if not key.startswith(allowed): raise ValueError('Unsupported Spark setting: '+key)
        conf[key] = str(value)
    return conf

def clean_local_spark_temp(now=None):
    """Prune old orphan directories only in this container's PID namespace."""
    import time,shutil
    now=now or time.time();root=RUNTIME/SERVICE/'spark-tmp'
    if not root.exists():return
    for path in root.iterdir():
        try:
            if not path.name.isdigit() or len(path.name)>10 or path.is_symlink() or not path.is_dir():continue
            if path.stat().st_mtime>now-86400:continue
        except FileNotFoundError:continue
        try:os.kill(int(path.name),0)
        except (ProcessLookupError,OverflowError):
            try:
                if path.resolve().parent==root.resolve():shutil.rmtree(path)
            except FileNotFoundError:pass
        except PermissionError:pass

def safe_path(relative, suffix=None):
    path = (ROOT / relative).resolve()
    if Path(relative).is_absolute() or not path.is_relative_to(ROOT.resolve()):
        raise ValueError('Path must stay inside workspace')
    if suffix and path.suffix != suffix: raise ValueError('Expected '+suffix)
    return path
