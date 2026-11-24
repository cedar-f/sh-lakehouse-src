"""Resolve packages before launching a JVM whose application classpath uses Ivy jars."""
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess


def use_resolved_jars(conf,paths):
    # Do not repeat remote Ivy resolution when the real driver JVM starts.
    jars=list(dict.fromkeys([p for p in conf.get('spark.jars','').split(',') if p]+paths))
    conf['spark.jars']=','.join(jars)
    conf.pop('spark.jars.packages',None)


def prepare(conf):
    packages=conf.get('spark.jars.packages')
    if not packages:return
    import pyspark
    ivy=Path(conf.get('spark.jars.ivy',str(Path.home()/'.ivy2')))
    ivy.mkdir(parents=True,exist_ok=True)
    identity={k:v for k,v in conf.items() if k.startswith('spark.jars.')}
    identity['pyspark']=pyspark.__version__
    digest=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
    marker=ivy/('lakehouse-resolved-'+digest+'.json')
    with (ivy/'lakehouse-resolve.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        try:
            paths=json.loads(marker.read_text(encoding='utf-8'))
            if paths and all(Path(p).is_file() for p in paths):
                use_resolved_jars(conf,paths);return
        except (OSError,ValueError):pass
        helper=Path('/opt/lakehouse/spark-package-resolver.jar')
        if not helper.is_file():raise RuntimeError('Spark package resolver is missing; rebuild the runtime image')
        submit=Path(pyspark.__file__).parent/'bin'/'spark-submit'
        command=[str(submit),'--driver-memory','512m','--class','lakehouse.ResolveSparkPackages']
        for key,value in conf.items():
            if key.startswith('spark.jars.') and key!='spark.jars':command+=['--conf',key+'='+str(value)]
        command.append(str(helper))
        subprocess.run(command,check=True)
        paths=[str(p) for p in (ivy/'jars').glob('*.jar')]
        if not paths:raise RuntimeError('Spark dependency resolution produced no Ivy jars')
        temporary=marker.with_suffix('.tmp');temporary.write_text(json.dumps(paths),encoding='utf-8');temporary.replace(marker)
        use_resolved_jars(conf,paths)
