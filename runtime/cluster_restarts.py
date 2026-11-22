"""Coordinate saved Spark settings, SQL readiness and selected Jupyter kernels."""
import asyncio
import copy
import inspect
import time
import uuid


async def wait_for_spark(kernel):
    client = kernel.client()
    client.start_channels()
    try:
        await client.wait_for_ready(timeout=180)
        request = client.execute('', silent=True, store_history=False, user_expressions={
            'spark_ready': "'spark' in globals() and not spark.sparkContext._jsc.sc().isStopped()",
        })
        async def reply():
            while True:
                message = await client.get_shell_msg()
                if message.get('parent_header', {}).get('msg_id') == request:
                    result = message['content'].get('user_expressions', {}).get('spark_ready', {})
                    if result.get('status') != 'ok' or result.get('data', {}).get('text/plain') != 'True':
                        raise RuntimeError('Kernel restarted but Spark did not initialize; check notebook startup output')
                    return
        await asyncio.wait_for(reply(), timeout=60)
    finally:
        client.stop_channels()


class ClusterRestarts:
    def __init__(self, kernel_manager, runner, ready_check=wait_for_spark, poll_interval=1):
        self.kernel_manager = kernel_manager
        self.runner = runner
        self.ready_check = ready_check
        self.poll_interval = poll_interval
        self.current = None
        self.task = None
        self.lock = asyncio.Lock()

    def snapshot(self, job_id=None):
        if job_id and (not self.current or job_id != self.current['id']):
            raise ValueError('Restart operation not found')
        return copy.deepcopy(self.current)

    async def start(self, data):
        async with self.lock:
            if self.task and not self.task.done():
                raise ValueError('A restart is already in progress; wait for it to finish')
            scope = data.get('scope')
            if scope not in ('sql', 'notebooks', 'both'):
                raise ValueError('Choose SQL/dbt, selected notebooks, or both')
            selected = data.get('kernel_ids', [])
            if not isinstance(selected, list) or any(not isinstance(k, str) for k in selected):
                raise ValueError('Invalid notebook kernel selection')
            selected = list(dict.fromkeys(selected)) if scope != 'sql' else []
            if scope == 'notebooks' and not selected:
                raise ValueError('Select at least one notebook kernel')
            known = {k['id'] for k in self.kernel_manager.list_kernels()}
            if any(k not in known for k in selected):
                raise ValueError('A selected kernel is no longer running; refresh the notebook list')
            config = data.get('config')
            if not isinstance(config, dict):
                raise ValueError('Spark configuration must be a JSON object')
            saved = await self.runner('POST', 'config', {**config, 'restart_sql': scope in ('sql', 'both')})
            if scope in ('sql', 'both') and not saved.get('restart_job'):
                raise RuntimeError('The runner does not support automatic restart yet; update the runtime image')
            self.current = {'id': uuid.uuid4().hex, 'state': 'RESTARTING', 'scope': scope,
                            'stage': 'Configuration saved', 'saved': True,
                            'sql': {'state': 'QUEUED' if scope in ('sql', 'both') else 'SKIPPED'},
                            'kernels': [{'id': k, 'state': 'QUEUED'} for k in selected]}
            self.task = asyncio.create_task(self.apply(saved.get('restart_job')))
            return self.snapshot()

    async def apply(self, sql_job):
        job = self.current
        try:
            if sql_job:
                deadline = time.monotonic() + 960
                while True:
                    result = await self.runner('GET', 'jobs/' + sql_job)
                    state = result['status']
                    job['sql']['state'] = state
                    job['stage'] = result.get('stage', 'Restarting Spark SQL')
                    if state == 'SUCCESS':
                        job['sql']['state'] = 'READY'
                        break
                    if state == 'FAILED':
                        raise RuntimeError(result.get('error', 'SQL restart failed; see Runs'))
                    if time.monotonic() > deadline:
                        raise TimeoutError('SQL restart is still pending; check Runs and SQL container logs')
                    await asyncio.sleep(self.poll_interval)
            job['stage'] = 'Restarting selected notebook kernels'
            # Serial startup avoids starting several Spark JVMs at the same time.
            errors = []
            for item in job['kernels']:
                item['state'] = 'RESTARTING'
                try:
                    result = await self.kernel_manager.restart_kernel(item['id'])
                    # MappingKernelManager returns a second Future for kernel_info_reply.
                    if inspect.isawaitable(result):
                        await result
                    await self.ready_check(self.kernel_manager.get_kernel(item['id']))
                    item['state'] = 'READY'
                except Exception as error:
                    item.update(state='FAILED', error=str(error))
                    errors.append(str(error))
            if errors:
                raise RuntimeError('; '.join(errors))
            job.update(state='READY', stage='Selected services are ready')
        except Exception as error:
            if job['sql']['state'] not in ('READY', 'SKIPPED'):
                job['sql']['state'] = 'FAILED'
            for item in job['kernels']:
                if item['state'] == 'QUEUED':
                    item['state'] = 'SKIPPED'
            job.update(state='FAILED', stage='Configuration saved; restart did not complete', error=str(error))
