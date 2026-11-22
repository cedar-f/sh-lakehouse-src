import asyncio
import copy
import json
import sys
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient

import runner
from cluster_restarts import ClusterRestarts, wait_for_spark
from sql_supervisor import SQLSupervisor, read_json, write_json


CONFIG = {'threads': 'auto', 'driver_memory': '4g', 'shuffle_partitions': 8,
          'default_catalog': 'lakehouse', 'default_schema': 'default',
          'extra': {'spark.sql.sources.default': 'delta'}}


@pytest.fixture
def runner_files(tmp_path, monkeypatch):
    monkeypatch.setenv('RUNNER_TOKEN', 'unit-test-token')
    monkeypatch.setattr(runner, 'SETTINGS', tmp_path / 'spark.json')
    monkeypatch.setattr(runner, 'RUNS', tmp_path / 'runs')
    monkeypatch.setattr(runner, 'SQL_CONTROL', tmp_path / 'control')
    monkeypatch.setattr(runner, 'SQL_RESTART_ID', None)
    runner.RUNS.mkdir()
    return TestClient(runner.app)


def test_invalid_config_is_not_saved_or_restarted(runner_files, monkeypatch):
    pool = Mock()
    monkeypatch.setattr(runner, 'RESTART_POOL', pool)
    write_json(runner.SETTINGS, CONFIG)
    invalid = copy.deepcopy(CONFIG)
    invalid['extra']['spark.sql.sources.default'] = {'invalid': 'nested object'}
    response = runner_files.post('/config', json={**invalid, 'restart_sql': True},
                                 headers={'X-Runner-Token': 'unit-test-token'})
    assert response.status_code == 400
    assert read_json(runner.SETTINGS) == CONFIG
    pool.submit.assert_not_called()


def test_restart_requires_auth_and_concurrent_save_is_rejected(runner_files, monkeypatch):
    pool = Mock()
    monkeypatch.setattr(runner, 'RESTART_POOL', pool)
    assert runner_files.post('/config', json={**CONFIG, 'restart_sql': True}).status_code == 401
    headers = {'X-Runner-Token': 'unit-test-token'}
    response = runner_files.post('/config', json={**CONFIG, 'restart_sql': True}, headers=headers)
    assert response.status_code == 200
    run_id = response.json()['restart_job']
    pool.submit.assert_called_once_with(runner.restart_sql, run_id)
    assert read_json(runner.SETTINGS) == CONFIG
    assert runner_files.post('/config', json=CONFIG, headers=headers).status_code == 409


def test_sql_restart_ignores_ready_status_from_an_old_request(runner_files, monkeypatch):
    run_id = 'a' * 32
    directory = runner.RUNS / run_id
    write_json(directory / 'run.json', {'id': run_id, 'status': 'QUEUED'})
    original_read = runner.read_json
    statuses = iter([{'id': 'old', 'state': 'READY'}, {'id': run_id, 'state': 'STARTING'},
                     {'id': run_id, 'state': 'READY'}])
    reads = []
    def read(path):
        if path == runner.SQL_CONTROL / 'status.json':
            reads.append(path)
            return next(statuses)
        return original_read(path)
    monkeypatch.setattr(runner, 'read_json', read)
    monkeypatch.setattr(runner.time, 'sleep', lambda _: None)
    query = Mock()
    monkeypatch.setattr(runner, 'sql_query', query)
    runner.restart_sql(run_id)
    assert len(reads) == 3
    assert read_json(directory / 'run.json')['status'] == 'SUCCESS'
    assert read_json(runner.SQL_CONTROL / 'request.json')['id'] == run_id
    query.assert_called_once_with('SELECT 1')


def test_sql_restart_failure_is_reported(runner_files, monkeypatch):
    run_id = 'b' * 32
    directory = runner.RUNS / run_id
    write_json(directory / 'run.json', {'id': run_id, 'status': 'QUEUED'})
    write_json(runner.SQL_CONTROL / 'status.json', {'id': run_id, 'state': 'FAILED', 'error': 'JVM exited'})
    query = Mock()
    monkeypatch.setattr(runner, 'sql_query', query)
    runner.restart_sql(run_id)
    result = read_json(directory / 'run.json')
    assert result['status'] == 'FAILED' and result['error'] == 'JVM exited'
    query.assert_not_called()


def test_supervisor_replaces_only_its_child_process(tmp_path):
    supervisor = SQLSupervisor(tmp_path, [sys.executable, '-c', 'import time; time.sleep(90)'], probe=lambda: True)
    try:
        supervisor.launch('first')
        first = supervisor.process
        supervisor.step()
        assert read_json(tmp_path / 'status.json')['state'] == 'READY'
        write_json(tmp_path / 'request.json', {'id': 'second'})
        supervisor.step()
        status = read_json(tmp_path / 'status.json')
        assert first.poll() is not None
        assert status['state'] == 'READY' and status['id'] == 'second'
        assert status['pid'] != first.pid
    finally:
        supervisor.stop()


def test_supervisor_timeout_never_reports_ready(tmp_path):
    supervisor = SQLSupervisor(tmp_path, [sys.executable, '-c', 'import time; time.sleep(90)'],
                               probe=lambda: False, timeout=0)
    try:
        supervisor.launch('timeout')
        child = supervisor.process
        supervisor.step()
        assert read_json(tmp_path / 'status.json')['state'] == 'FAILED'
        assert child.poll() is not None
    finally:
        supervisor.stop()


def manager():
    kernels = Mock()
    kernels.list_kernels.return_value = [{'id': 'chosen'}, {'id': 'other'}]
    kernels.restart_kernel = AsyncMock()
    return kernels


def test_both_restarts_only_selected_kernels_after_sql_is_ready():
    async def run():
        kernels = manager()
        async def call(method, path, payload=None):
            if path == 'config':
                assert payload['restart_sql'] is True
                return {'restart_job': 'sql-job'}
            return {'status': 'SUCCESS'}
        check = AsyncMock()
        control = ClusterRestarts(kernels, call, ready_check=check)
        await control.start({'scope': 'both', 'kernel_ids': ['chosen', 'chosen'], 'config': CONFIG})
        await control.task
        assert control.snapshot()['state'] == 'READY'
        assert control.snapshot()['sql']['state'] == 'READY'
        kernels.restart_kernel.assert_awaited_once_with('chosen')
        check.assert_awaited_once()
    asyncio.run(run())


@pytest.mark.parametrize('scope,ids', [('invalid', []), ('notebooks', []), ('both', ['unknown'])])
def test_invalid_scope_or_kernel_is_rejected_before_saving(scope, ids):
    async def run():
        call = AsyncMock()
        control = ClusterRestarts(manager(), call)
        with pytest.raises(ValueError):
            await control.start({'scope': scope, 'kernel_ids': ids, 'config': CONFIG})
        call.assert_not_called()
    asyncio.run(run())


def test_sql_failure_does_not_restart_notebooks_or_report_ready():
    async def run():
        kernels = manager()
        call = AsyncMock(side_effect=[{'restart_job': 'sql-job'}, {'status': 'FAILED', 'error': 'Bad Spark config'}])
        control = ClusterRestarts(kernels, call)
        await control.start({'scope': 'both', 'kernel_ids': ['chosen'], 'config': CONFIG})
        await control.task
        state = control.snapshot()
        assert state['state'] == 'FAILED' and state['saved'] is True
        assert state['kernels'][0]['state'] == 'SKIPPED'
        kernels.restart_kernel.assert_not_called()
    asyncio.run(run())


def test_failed_notebook_readiness_and_concurrent_restart():
    async def run():
        kernels = manager()
        gate = asyncio.Event()
        async def check(_):
            await gate.wait()
            raise RuntimeError('Spark failed to start')
        call = AsyncMock(return_value={'saved': True})
        control = ClusterRestarts(kernels, call, ready_check=check)
        data = {'scope': 'notebooks', 'kernel_ids': ['chosen'], 'config': CONFIG}
        await control.start(data)
        with pytest.raises(ValueError, match='already in progress'):
            await control.start(data)
        gate.set()
        await control.task
        assert control.snapshot()['state'] == 'FAILED'
        assert control.snapshot()['kernels'][0]['state'] == 'FAILED'
        assert call.call_args.args[2]['restart_sql'] is False
    asyncio.run(run())


def test_python_ready_without_spark_is_not_considered_ready():
    async def run():
        client = Mock()
        client.wait_for_ready = AsyncMock()
        client.execute.return_value = 'request'
        client.get_shell_msg = AsyncMock(return_value={'parent_header': {'msg_id': 'request'},
            'content': {'user_expressions': {'spark_ready': {'status': 'ok', 'data': {'text/plain': 'False'}}}}})
        kernel = Mock()
        kernel.client.return_value = client
        with pytest.raises(RuntimeError, match='Spark did not initialize'):
            await wait_for_spark(kernel)
        client.stop_channels.assert_called_once()
    asyncio.run(run())
