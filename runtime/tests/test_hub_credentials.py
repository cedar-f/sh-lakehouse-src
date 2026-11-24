import runpy
from pathlib import Path

from traitlets.config import Config


def test_hub_forwards_r2_s3a_aliases_to_singleuser(monkeypatch):
    values={'R2_ACCESS_KEY_ID':'fixture-key', 'R2_SECRET_ACCESS_KEY':'fixture-secret',
            'AWS_ACCESS_KEY_ID':'fixture-key', 'AWS_SECRET_ACCESS_KEY':'fixture-secret',
            'RUNNER_TOKEN':'fixture-runner', 'AWS_UNRELATED_PRIVATE_SETTING':'not-for-child'}
    for key,value in values.items():monkeypatch.setenv(key,value)
    config=Config()
    runpy.run_path(str(Path(__file__).parents[1]/'hub_config.py'),init_globals={'get_config':lambda:config})
    child=config.Spawner.environment
    for key in ('R2_ACCESS_KEY_ID','R2_SECRET_ACCESS_KEY','AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY','RUNNER_TOKEN'):
        assert child[key]==values[key]
    assert 'AWS_UNRELATED_PRIVATE_SETTING' not in child
