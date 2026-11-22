import os
import config,retention

def test_service_temp_cleanup_preserves_active_pid_and_other_services(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'RUNTIME',tmp_path);monkeypatch.setattr(config,'SERVICE','notebook')
    paths=[tmp_path/'notebook/spark-tmp/123',tmp_path/'notebook/spark-tmp/456',tmp_path/'sql/spark-tmp/456']
    for path in paths:path.mkdir(parents=True);os.utime(path,(1,1))
    def lookup(pid,signal):
        if pid==456:raise ProcessLookupError()
    monkeypatch.setattr(config.os,'kill',lookup)
    config.clean_local_spark_temp(now=200000)
    assert paths[0].exists() and not paths[1].exists() and paths[2].exists()

def test_runner_never_prunes_other_container_pid_namespaces(tmp_path,monkeypatch):
    monkeypatch.setattr(retention,'RUNTIME',tmp_path/'runtime');monkeypatch.setattr(retention,'RUNS',tmp_path/'runs');retention.RUNS.mkdir()
    path=retention.RUNTIME/'notebook/spark-tmp/999';path.mkdir(parents=True);os.utime(path,(1,1))
    def invalid_lookup(*args):raise AssertionError('Must not inspect another container PID')
    monkeypatch.setattr(retention.os,'kill',invalid_lookup)
    retention.cleanup(False,now=200000)
    assert path.exists()
