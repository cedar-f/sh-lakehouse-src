from unittest.mock import Mock
from urllib.error import HTTPError, URLError

import pytest
import pathspec

import runner
import service_readiness
from dbt_project import prepare_dbt_project


def clock(monkeypatch):
    elapsed = [0]
    monkeypatch.setattr(service_readiness.time, 'monotonic', lambda: elapsed[0])
    monkeypatch.setattr(service_readiness.time, 'sleep', lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds))
    return elapsed


def test_sql_startup_waits_for_catalog_after_docker_resume(monkeypatch):
    elapsed = clock(monkeypatch)
    load = Mock(side_effect=[URLError('connection refused'),
        HTTPError('http://catalog', 503, 'starting', {}, None), {'spark.master': 'local[2]'}])
    assert service_readiness.spark_conf_when_catalog_ready(timeout=10, loader=load) == {'spark.master': 'local[2]'}
    assert load.call_count == 3 and elapsed[0] == 4


def test_catalog_wait_is_bounded(monkeypatch):
    elapsed = clock(monkeypatch)
    load = Mock(side_effect=URLError('connection refused'))
    with pytest.raises(TimeoutError, match='Unity Catalog did not become available'):
        service_readiness.spark_conf_when_catalog_ready(timeout=4, loader=load)
    assert elapsed[0] == 4 and load.call_count == 3


@pytest.mark.parametrize('error', [ValueError('Invalid Spark config'),
    HTTPError('http://catalog', 401, 'unauthorized', {}, None)])
def test_permanent_config_or_auth_error_is_not_retried(monkeypatch, error):
    clock(monkeypatch)
    load = Mock(side_effect=error)
    with pytest.raises(type(error)):
        service_readiness.spark_conf_when_catalog_ready(loader=load)
    assert load.call_count == 1


def test_runner_waits_for_sql_instead_of_starting_dbt_too_early(monkeypatch):
    clock(monkeypatch)
    monkeypatch.setattr(runner, 'read_json', lambda _: {'state': 'STARTING'})
    query = Mock(side_effect=[ConnectionError('SQL starting'), {'rows': [[1]]}])
    monkeypatch.setattr(runner, 'sql_query', query)
    runner.wait_for_sql_ready(timeout=10)
    assert query.call_count == 2


def test_failed_sql_has_actionable_error(monkeypatch):
    monkeypatch.setattr(runner, 'read_json', lambda _: {'state': 'FAILED', 'error': 'JVM exited'})
    query = Mock()
    monkeypatch.setattr(runner, 'sql_query', query)
    with pytest.raises(RuntimeError, match='Open Compute and use Save & Restart Spark'):
        runner.wait_for_sql_ready()
    query.assert_not_called()


def test_checkpoint_exclusion_keeps_user_rules_and_recovery_files(tmp_path):
    existing = '# User rules\nmodels/legacy/**'
    (tmp_path / '.dbtignore').write_text(existing)
    checkpoint = tmp_path / 'models/.ipynb_checkpoints/orders-checkpoint.sql'
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_text('select 1')
    prepare_dbt_project(tmp_path)
    first = (tmp_path / '.dbtignore').read_bytes()
    prepare_dbt_project(tmp_path)
    assert (tmp_path / '.dbtignore').read_bytes() == first
    assert first.decode().startswith(existing)
    assert checkpoint.read_text() == 'select 1'
    rules = pathspec.PathSpec.from_lines('gitwildmatch', first.decode().splitlines())
    assert rules.match_file('models/.ipynb_checkpoints/orders-checkpoint.sql')
    assert rules.match_file('seeds/.ipynb_checkpoints/orders-checkpoint.csv')
    assert rules.match_file('models/legacy/old.sql')
    assert not rules.match_file('models/orders.sql')


def test_cli_failure_detail_shows_root_error_without_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv('RUNNER_TOKEN', 'private-test-value')
    log = tmp_path / 'execution.log'
    log.write_text('12:00:00 Normal log\n12:00:01 [ERROR]: Encountered an error:\n'
                   'Database Error\nfailed to connect private-test-value\n' + 'stack line\n' * 800)
    message = runner.command_error('dbt', 2, log)
    assert 'failed to connect' in message
    assert 'private-test-value' not in message and '[REDACTED]' in message
    assert len(message) < 2000
