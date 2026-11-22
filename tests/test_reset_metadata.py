"""Check the reset target selection without deleting any Docker volumes."""
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('reset_metadata', Path(__file__).parents[1]/'scripts/reset_metadata.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def docker(monkeypatch, bad_label=False, external=False, missing=False):
    calls = []
    volumes = {key: {'name': 'fixture_'+key} for key in (*module.KEYS, 'git_ssh', 'spark_ivy')}
    if external:
        volumes['postgres_data']['external'] = True
    def command(args):
        calls.append(args)
        if args[:3] == ['docker', 'compose', 'config']:
            return json.dumps({'name': 'fixture', 'volumes': volumes})
        if args == ['docker', 'volume', 'ls', '-q']:
            return '' if missing else '\n'.join(v['name'] for v in volumes.values())
        if args[:3] == ['docker', 'volume', 'inspect']:
            return json.dumps([{'Labels': {'com.docker.compose.project': 'other' if bad_label else 'fixture',
                'com.docker.compose.volume': args[3].removeprefix('fixture_')}}])
        return ''
    monkeypatch.setattr(module, 'command', command)
    return calls


def test_only_owned_metadata_volumes_are_removed_after_compose_down(monkeypatch):
    calls = docker(monkeypatch)
    module.reset()
    assert calls[-2] == ['docker', 'compose', 'down']
    assert calls[-1] == ['docker', 'volume', 'rm', *['fixture_'+key for key in module.KEYS]]
    assert not any('--force' in call or '-v' in call for call in calls)


@pytest.mark.parametrize('kwargs', [{'bad_label': True}, {'external': True}])
def test_reset_refuses_unowned_or_external_volumes_before_stopping(monkeypatch, kwargs):
    calls = docker(monkeypatch, **kwargs)
    with pytest.raises(ValueError, match='Refusing'):
        module.reset()
    assert ['docker', 'compose', 'down'] not in calls
    assert not any(call[:3] == ['docker', 'volume', 'rm'] for call in calls)


def test_new_host_without_volumes_can_start_fresh(monkeypatch):
    calls = docker(monkeypatch, missing=True)
    module.reset()
    assert calls[-1] == ['docker', 'compose', 'down']
