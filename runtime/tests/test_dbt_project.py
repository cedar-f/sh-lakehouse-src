import json
from unittest.mock import Mock
from urllib.error import HTTPError

import pytest
import yaml

import runner
from dbt_project import project_destination, ensure_schema_macro, validate_manifest, SCHEMA_MACRO


DEFAULTS = {'default_catalog': 'old_catalog', 'default_schema': 'default'}


def project(path, **overrides):
    data = {'name': 'demo', 'profile': 'lakehouse', 'config-version': 2,
            'vars': {'lakehouse_catalog': 'analytics'},
            'models': {'demo': {'staging': {'+schema': 'a'}, 'marts': {'+schema': 'b'}}}}
    data.update(overrides)
    (path / 'dbt_project.yml').write_text(yaml.safe_dump(data))
    return data


def test_catalog_and_connection_schema_come_from_project_not_compute(tmp_path):
    project(tmp_path)
    destination = project_destination(tmp_path, {}, DEFAULTS)
    assert destination == {'mode': 'project', 'catalog': 'analytics', 'project_name': 'demo',
                           'session_schema': 'a', 'schemas': ['a', 'b']}


@pytest.mark.parametrize('payload', [{'schema': 'other'}, {'catalog': 'other'},
                                    {'parameters': {'lakehouse_catalog': 'other'}}])
def test_execution_cannot_silently_redirect_a_project(tmp_path, payload):
    project(tmp_path)
    with pytest.raises(ValueError):
        project_destination(tmp_path, payload, DEFAULTS)


@pytest.mark.parametrize('catalog', ['', None, 'a.b', "{{ env_var('CATALOG') }}"])
def test_catalog_must_be_a_literal_identifier(tmp_path, catalog):
    project(tmp_path, vars={'lakehouse_catalog': catalog})
    with pytest.raises(ValueError):
        project_destination(tmp_path, {}, DEFAULTS)


def test_project_requires_declared_schema_and_rejects_adapter_database(tmp_path):
    project(tmp_path, models={'demo': {}})
    with pytest.raises(ValueError, match='Declare at least one'):
        project_destination(tmp_path, {}, DEFAULTS)
    project(tmp_path, models={'demo': {'+schema': 'a', '+database': 'analytics'}})
    with pytest.raises(ValueError, match='one catalog'):
        project_destination(tmp_path, {}, DEFAULTS)


def test_legacy_project_preserves_existing_overrides(tmp_path):
    project(tmp_path, vars={})
    assert project_destination(tmp_path, {'catalog': 'old', 'schema': 'custom'}, DEFAULTS) == {
        'mode': 'legacy', 'catalog': 'old', 'session_schema': 'custom'}


def test_macro_is_added_once_without_overwriting_user_code(tmp_path):
    project(tmp_path)
    ensure_schema_macro(tmp_path)
    path = tmp_path / 'macros/lakehouse_schema.sql'
    assert path.read_text() == SCHEMA_MACRO
    ensure_schema_macro(tmp_path)
    custom = '{% macro generate_schema_name(custom_schema_name,node) %}custom{% endmacro %}'
    path.write_text(custom)
    ensure_schema_macro(tmp_path)
    assert path.read_text() == custom


def test_macro_paths_cannot_escape_the_project(tmp_path):
    project(tmp_path, **{'macro-paths': ['../elsewhere']})
    with pytest.raises(ValueError, match='stay inside'):
        ensure_schema_macro(tmp_path)


def manifest(schema='a', declared='a', database=None):
    return {'nodes': {'model.demo.orders': {'name': 'orders', 'resource_type': 'model',
             'schema': schema, 'database': database, 'config': {'schema': declared}}}}


def test_manifest_requires_explicit_exact_schema_before_sql_execution():
    validate_manifest(manifest(), {})
    for data in (manifest(declared=None), manifest(schema='default_a'), manifest(database='other')):
        with pytest.raises(ValueError):
            validate_manifest(data, {})
    with pytest.raises(ValueError, match='Sources'):
        validate_manifest({'sources': {'source.demo.raw': {'schema': 'raw', 'database': 'other'}}}, {})


def test_project_namespace_does_not_create_default(monkeypatch):
    calls = []
    def uc(method, resource, data=None):
        calls.append((method, resource, data))
        if method == 'GET' and resource.startswith('schemas/'):
            raise HTTPError('http://fixture', 404, 'missing', {}, None)
        return {}
    monkeypatch.setattr(runner, 'uc', uc)
    runner.ensure_dbt_namespace({'mode': 'project', 'catalog': 'analytics', 'session_schema': 'a'})
    assert calls == [('GET', 'catalogs/analytics', None), ('GET', 'schemas/analytics.a', None),
                     ('POST', 'schemas', {'name': 'a', 'catalog_name': 'analytics'})]


def test_missing_catalog_has_actionable_error(monkeypatch):
    monkeypatch.setattr(runner, 'uc', Mock(side_effect=HTTPError('http://fixture', 404, 'missing', {}, None)))
    with pytest.raises(ValueError, match='Create it in Catalog'):
        runner.ensure_dbt_namespace({'mode': 'project', 'catalog': 'missing', 'session_schema': 'a'})


def test_runner_writes_project_profile_and_resolved_destination(tmp_path, monkeypatch):
    project(tmp_path)
    runs = tmp_path / 'runs'
    runs.mkdir()
    monkeypatch.setattr(runner, 'RUNS', runs)
    monkeypatch.setattr(runner, 'safe_path', lambda _: tmp_path)
    monkeypatch.setattr(runner, 'settings', lambda: {**DEFAULTS, 'driver_memory': '1g'})
    monkeypatch.setattr(runner, 'wait_for_sql_ready', Mock())
    monkeypatch.setattr(runner, 'ensure_dbt_namespace', Mock())
    monkeypatch.setattr(runner, 'spark_conf', lambda: {})
    monkeypatch.setattr(runner, 'record', lambda path, data: None)
    captured = []
    def capture(command, cwd, env, directory, timeout):
        captured.append((command, env))
        return 0
    monkeypatch.setattr(runner, 'capture_process', capture)
    result = runner.execute({'kind': 'dbt', 'path': '.', 'command': 'build'}, 'a' * 32)
    assert result['status'] == 'SUCCESS'
    assert result['catalog'] == 'analytics' and result['dbt_destination']['schemas'] == ['a', 'b']
    directory = runs / ('a' * 32)
    profile = yaml.safe_load((directory / 'profiles.yml').read_text())['lakehouse']['outputs']['dev']
    assert profile['schema'] == 'a'
    assert profile['server_side_parameters']['set:hivevar:spark.sql.defaultCatalog'] == 'analytics'
    assert captured[0][0][1].endswith('dbt_job.py')
    spec = json.loads((directory / 'dbt-job.json').read_text())
    assert spec['destination']['catalog'] == 'analytics'


def test_open_docs_does_not_reuse_snapshot_from_another_catalog(tmp_path, monkeypatch):
    import run_store
    project(tmp_path)
    monkeypatch.setattr(runner, 'safe_path', lambda _: tmp_path)
    monkeypatch.setattr(runner, 'settings', lambda: DEFAULTS)
    monkeypatch.setattr(run_store, 'DB', tmp_path/'history.sqlite')
    monkeypatch.setattr(runner, 'RUNS', tmp_path/'runs')
    for index, catalog in enumerate(('analytics', 'other')):
        run_id = str(index) * 32
        directory = runner.RUNS/run_id/'target'
        directory.mkdir(parents=True)
        (directory/'index.html').write_text('fixture docs')
        run_store.upsert('run', {'id': run_id, 'path': '.', 'kind': 'dbt', 'status': 'SUCCESS',
                               'started': index+1, 'catalog': catalog,
                               'dbt_destination': {'mode': 'project'}})
    assert runner.docs_latest('.')['run_id'] == '0'*32
    project(tmp_path, vars={'lakehouse_catalog': 'new_catalog'})
    assert runner.docs_latest('.')['run_id'] is None
