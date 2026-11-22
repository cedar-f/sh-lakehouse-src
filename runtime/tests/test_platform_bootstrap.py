import json
from pathlib import Path
import runpy
from urllib.error import HTTPError

from botocore.exceptions import ClientError
import pytest

import config
import platform_bootstrap as provision


class Store:
    def __init__(self, objects=None):
        self.objects = dict(objects or {})
        self.puts = []

    def list_objects_v2(self, **args):
        return {'Contents': [{'Key': key} for key in self.objects if key.startswith(args['Prefix'])][:args['MaxKeys']]}

    def put_object(self, **args):
        assert args['IfNoneMatch'] == '*'
        self.puts.append(args['Key'])
        if args['Key'] in self.objects:
            raise ClientError({'ResponseMetadata': {'HTTPStatusCode': 412}}, 'PutObject')
        self.objects[args['Key']] = args['Body']


def test_empty_bucket_layout_then_repeat_preserves_all_objects(monkeypatch):
    monkeypatch.setenv('BACKUP_PREFIX', 'platform-backups/v3')
    store = Store()
    assert set(provision.ensure_layout(store, 'bucket').values()) == {'created'}
    assert store.objects == {'warehouse/': b'', 'incoming/': b'', 'platform-backups/v3/': b''}
    store.objects['warehouse/table/_delta_log/000.json'] = b'keep delta log'
    before = dict(store.objects)
    store.puts.clear()
    assert set(provision.ensure_layout(store, 'bucket').values()) == {'reused'}
    assert store.objects == before and not store.puts


def test_existing_prefix_without_marker_is_reused(monkeypatch):
    monkeypatch.setenv('BACKUP_PREFIX', 'backups/custom')
    store = Store({'warehouse/a/data': b'keep', 'incoming/data.csv': b'keep', 'backups/custom/archive': b'keep'})
    assert set(provision.ensure_layout(store, 'bucket').values()) == {'reused'}
    assert not store.puts and 'warehouse/' not in store.objects


@pytest.mark.parametrize('prefix', ['', '../backups', '/backups', 'incoming', 'warehouse/x', 'x//y', 'x\\y'])
def test_invalid_backup_prefix_fails_before_any_storage_mutation(monkeypatch, prefix):
    monkeypatch.setenv('BACKUP_PREFIX', prefix)
    store = Store()
    with pytest.raises(ValueError, match='BACKUP_PREFIX'):
        provision.ensure_layout(store, 'bucket')
    assert not store.objects


def test_racing_marker_creation_is_not_overwritten(monkeypatch):
    monkeypatch.setenv('BACKUP_PREFIX', 'backups')
    store = Store({'warehouse/': b'custom marker'})
    original = store.list_objects_v2
    store.list_objects_v2 = lambda **args: {} if args['Prefix'] == 'warehouse/' else original(**args)
    assert provision.ensure_layout(store, 'bucket')['warehouse/'] == 'reused'
    assert store.objects['warehouse/'] == b'custom marker'


def test_bootstrap_twice_and_user_sample_changes_are_preserved(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'ROOT', tmp_path)
    monkeypatch.setenv('R2_BUCKET', 'bucket')
    monkeypatch.setenv('BACKUP_PREFIX', 'platform-backups/v3')
    monkeypatch.setenv('DEFAULT_CATALOG', 'starter')
    monkeypatch.setenv('DEFAULT_SCHEMA', 'default')
    monkeypatch.setenv('SEED_SAMPLE_DBT', 'true')
    store = Store()
    monkeypatch.setattr(provision, 'storage', lambda: store)
    resources = {}
    def uc(method, resource, data):
        assert method == 'POST'
        key = (resource, data.get('catalog_name'), data['name'])
        if key in resources:
            raise HTTPError('http://catalog', 409, 'exists', {}, None)
        resources[key] = dict(data)
    monkeypatch.setattr(config, 'uc', uc)
    path = Path(provision.__file__).with_name('bootstrap.py')
    runpy.run_path(str(path))
    model = tmp_path/'dbt_sample/models/customer_totals.sql'
    model.write_text('-- custom user model\nselect 123\n')
    definition = tmp_path/'workflows/dbt_sample_pipeline.json'
    flow = json.loads(definition.read_text())
    assert [n['command'] for n in flow['nodes']] == ['seed', 'build', 'docs']
    assert flow['scheduleEnabled'] is False and flow['cron'] == ''
    assert all(n['catalog'] == 'starter' and n['schema'] == 'dbt_sample' for n in flow['nodes'])
    flow['description'] = 'user customization'
    definition.write_text(json.dumps(flow))
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    runpy.run_path(str(path))
    assert {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()} == before
    assert ('schemas', 'starter', 'dbt_sample') in resources


def test_existing_project_and_yaml_only_flow_are_not_overwritten(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'ROOT', tmp_path)
    (tmp_path/'dbt_sample').mkdir()
    (tmp_path/'dbt_sample/dbt_project.yml').write_text('user project')
    (tmp_path/'workflows').mkdir()
    path = tmp_path/'workflows/dbt_sample_pipeline.yml'
    path.write_text('user workflow')
    assert provision.seed_sample(tmp_path, 'demo', 'Etc/UTC') == {'project': 'reused', 'flow': 'reused'}
    assert path.read_text() == 'user workflow'
    assert not (tmp_path/'workflows/dbt_sample_pipeline.json').exists()
    assert (tmp_path/'dbt_sample/dbt_project.yml').read_text() == 'user project'


def test_sample_can_be_disabled(monkeypatch):
    monkeypatch.setenv('SEED_SAMPLE_DBT', 'false')
    assert provision.sample_enabled() is False
    monkeypatch.setenv('SEED_SAMPLE_DBT', 'maybe')
    with pytest.raises(ValueError):
        provision.sample_enabled()
