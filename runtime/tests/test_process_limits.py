import os,sys
from run_support import capture_process

def test_process_timeout_kills_job_and_keeps_log(tmp_path):
    code=capture_process([sys.executable,'-c','import time;print("started",flush=True);time.sleep(30)'],tmp_path,os.environ.copy(),tmp_path,.3)
    assert code==124 and 'started' in (tmp_path/'execution.log').read_text()

def test_active_job_artifact_limit_stops_growth(tmp_path,monkeypatch):
    monkeypatch.setenv('RUN_ARTIFACT_MAX_MB','1')
    code=capture_process([sys.executable,'-c','from pathlib import Path;import time;Path("large.bin").write_bytes(b"x"*2097152);time.sleep(30)'],tmp_path,os.environ.copy(),tmp_path,20)
    assert code==125
    assert 'artifact size limit exceeded' in (tmp_path/'process.events.jsonl').read_text()
