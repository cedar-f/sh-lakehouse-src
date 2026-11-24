import json
import sys
from types import SimpleNamespace

import pytest

from spark_dependencies import prepare


def test_no_packages_does_not_launch(monkeypatch):
    monkeypatch.setattr('spark_dependencies.subprocess.run',lambda *a,**kw:pytest.fail('unexpected launch'))
    prepare({})


def test_pre_resolve_cached_files_and_retry_missing_jar(tmp_path,monkeypatch):
    monkeypatch.setitem(sys.modules,'pyspark',SimpleNamespace(__version__='fixture',__file__='/tmp/pyspark/__init__.py'))
    original_is_file=type(tmp_path).is_file
    monkeypatch.setattr(type(tmp_path),'is_file',lambda p:True if str(p)=='/opt/lakehouse/spark-package-resolver.jar' else original_is_file(p))
    calls=[]
    jar=tmp_path/'jars'/'fixture.jar'
    def resolve(command,check):
        calls.append(command);jar.parent.mkdir(exist_ok=True);jar.write_bytes(b'fixture')
    monkeypatch.setattr('spark_dependencies.subprocess.run',resolve)
    conf={'spark.jars.packages':'fixture:connector:1','spark.jars.ivy':str(tmp_path)}
    prepared=dict(conf);prepare(prepared);prepare(dict(conf))
    assert 'spark.jars.packages' not in prepared and prepared['spark.jars']==str(jar)
    assert len(calls)==1
    assert '--class' in calls[0] and 'lakehouse.ResolveSparkPackages' in calls[0]
    assert json.loads(next(tmp_path.glob('lakehouse-resolved-*.json')).read_text())==[str(jar)]
    jar.unlink();prepare(dict(conf))
    assert len(calls)==2
    prepare({**conf,'spark.jars.packages':'fixture:connector:2'})
    assert len(calls)==3
