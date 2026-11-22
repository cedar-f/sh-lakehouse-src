"""Destructive restart checks: run ONLY against a separate test stack/workspace.

Required env: LAKEHOUSE_RESTART_TEST_URL, LAKEHOUSE_TEST_NOTEBOOK_CONTAINER,
LAKEHOUSE_TEST_SQL_CONTAINER, LAKEHOUSE_TEST_WORKSPACE_ROOT.
Uses the project's .env for the login token. Does not create any R2 tables.
"""
import ast
import json
import os
import re
import subprocess
import sys
import time
import traceback
import uuid
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ENV = dict(line.split('=', 1) for line in (ROOT / '.env').read_text(encoding='utf-8-sig').splitlines()
           if '=' in line and not line.startswith('#'))
URL = os.environ['LAKEHOUSE_RESTART_TEST_URL'].rstrip('/')
NOTEBOOK = os.environ['LAKEHOUSE_TEST_NOTEBOOK_CONTAINER']
SQL = os.environ['LAKEHOUSE_TEST_SQL_CONTAINER']
WORKSPACE = Path(os.environ['LAKEHOUSE_TEST_WORKSPACE_ROOT'])
KERNEL_QUERY = r'''
import ast,json,sys
from pathlib import Path
from jupyter_client import BlockingKernelClient
client=BlockingKernelClient(connection_file=str(Path('/home/analyst/.local/share/jupyter/runtime')/('kernel-'+sys.argv[1]+'.json')))
client.load_connection_file();client.start_channels()
try:
 client.wait_for_ready(timeout=180)
 request=client.execute(sys.argv[3],silent=True,store_history=False,user_expressions={'result':sys.argv[2]})
 while True:
  reply=client.get_shell_msg(timeout=180)
  if reply.get('parent_header',{}).get('msg_id')!=request:continue
  result=reply['content']['user_expressions']['result']
  if result['status']!='ok':raise RuntimeError(result.get('evalue','Kernel expression failed'))
  print(json.dumps(ast.literal_eval(result['data']['text/plain'])))
  break
finally:client.stop_channels()
'''


def main():
    deadline = time.monotonic() + 180
    import urllib.request
    while True:
        try:
            urllib.request.urlopen(URL + '/login', timeout=3).close()
            break
        except Exception:
            if time.monotonic() > deadline:
                raise TimeoutError('Test notebook server did not start')
            time.sleep(1)
    fixture = 'restart_check_' + uuid.uuid4().hex[:10] + '.ipynb'
    session = None
    created = False
    errors = []
    with sync_playwright() as playwright:
        options = {'headless': True}
        if os.getenv('LAKEHOUSE_TEST_BROWSER'):
            options['executable_path'] = os.environ['LAKEHOUSE_TEST_BROWSER']
        browser = playwright.chromium.launch(**options)
        page = browser.new_page(viewport={'width': 1600, 'height': 1200})
        page.on('pageerror', lambda error: errors.append(str(error)))
        def api(method, path, data=None):
            response = page.request.fetch(URL + path, method=method, data=data,
                headers={'Authorization': 'token ' + ENV['JUPYTER_TOKEN']}, timeout=180000)
            if not response.ok:
                raise RuntimeError(str(response.status) + ': ' + response.text()[:1500])
            return response.json() if response.body() else None
        def sql_state():
            return json.loads((WORKSPACE / '.lakehouse/sql-control/status.json').read_text())
        def kernel_value(expression, code=''):
            result = subprocess.run(['docker', 'exec', NOTEBOOK, 'python3', '-c', KERNEL_QUERY,
                session['kernel']['id'], expression, code], capture_output=True, text=True, timeout=200)
            if result.returncode:
                raise RuntimeError(result.stderr[-2500:])
            return json.loads(result.stdout.strip().splitlines()[-1])
        try:
            page.goto(URL + '/lab/workspaces/restart-check-' + uuid.uuid4().hex[:10], wait_until='domcontentloaded')
            page.get_by_label('Password or token:').fill(ENV['JUPYTER_TOKEN'])
            page.get_by_role('button', name='Log in', exact=True).click()
            page.get_by_role('heading', name='Catalog', exact=True).wait_for(timeout=60000)
            names = ['Catalog', 'Files', 'Compute', 'SQL', 'dbt', 'Runs', 'Workflows', 'GitHub', 'Notebook']
            for name in names:
                page.locator('.lh-sidebar').get_by_role('button', name=name, exact=True).click()
                tab = page.get_by_role('tab', name=name, exact=True)
                expect(tab).to_have_attribute('aria-selected', 'true')
            tabs = page.get_by_role('tab', name=re.compile('^(?:' + '|'.join(names) + ')$'))
            assert tabs.count() == 9
            assert tabs.evaluate_all('(tabs)=>new Set(tabs.map(t=>t.closest(".lm-TabBar"))).size') == 1
            print('PASS: all 9 tabs have plain names, share one tab bar and select immediately', flush=True)

            api('PUT', '/api/contents/' + fixture, {'type': 'notebook', 'format': 'json', 'content': {
                'nbformat': 4, 'nbformat_minor': 5, 'metadata': {}, 'cells': []}})
            created = True
            session = api('POST', '/api/sessions', {'path': fixture, 'type': 'notebook', 'name': fixture,
                                                   'kernel': {'name': 'python3'}})
            before = kernel_value("(__import__('os').getpid(),spark.conf.get('spark.sql.sources.default'),'restart_sentinel' in globals())",
                                  "restart_sentinel='preserve until selected restart'")
            assert before[1:] == ['parquet', True], before
            sql_pid = sql_state()['pid']
            server_started = subprocess.check_output(['docker', 'inspect', NOTEBOOK, '--format', '{{.State.StartedAt}}'], text=True).strip()
            sql_started = subprocess.check_output(['docker', 'inspect', SQL, '--format', '{{.State.StartedAt}}'], text=True).strip()
            page.locator('.lh-sidebar').get_by_role('button', name='Compute', exact=True).click()
            compute = page.locator('#lakehouse-Compute')
            compute.get_by_role('button', name='Refresh notebook list', exact=True).click()
            expect(compute.get_by_role('checkbox')).to_have_count(1)
            compute.get_by_role('checkbox').check()
            scope = compute.get_by_label('Restart scope', exact=True)
            extra = compute.get_by_label('Extra Spark config / Maven packages (JSON)', exact=True)
            save = compute.get_by_role('button', name='Save & Restart Spark', exact=True)
            status = compute.get_by_role('status')
            def apply(scope_name, extra_config, expected='READY'):
                scope.select_option(scope_name)
                extra.fill(json.dumps(extra_config))
                save.click()
                expect(save).to_be_disabled()
                page.wait_for_function("([selector,state])=>document.querySelector(selector)?.textContent.startsWith(state+' · ')",
                    arg=['#lakehouse-Compute [role="status"]', expected], timeout=240000)
                expect(save).to_be_enabled()

            apply('sql', {'spark.sql.sources.default': 'delta'})
            assert sql_state()['state'] == 'READY' and sql_state()['pid'] != sql_pid
            after_sql = kernel_value("(__import__('os').getpid(),spark.conf.get('spark.sql.sources.default'),'restart_sentinel' in globals())")
            assert after_sql == before
            result = api('POST', '/lakehouse/api/sql', {'sql': 'SET spark.sql.sources.default'})
            assert result['rows'][0][1] == 'delta', result
            print('PASS: SQL-only save replaces SQL JVM, applies Delta and preserves the unselected notebook and its RAM', flush=True)

            sql_pid = sql_state()['pid']
            apply('both', {'spark.sql.sources.default': 'delta'})
            after_both = kernel_value("(__import__('os').getpid(),spark.conf.get('spark.sql.sources.default'),'restart_sentinel' in globals())")
            assert after_both[0] != before[0] and after_both[1:] == ['delta', False], after_both
            assert sql_state()['pid'] != sql_pid
            assert tabs.count() == 9
            print('PASS: both scope restarts SQL and the selected kernel; notebook gets Delta; tabs stay open', flush=True)

            sql_pid = sql_state()['pid']
            apply('notebooks', {'spark.sql.sources.default': 'delta'})
            after_notebook = kernel_value("(__import__('os').getpid(),spark.conf.get('spark.sql.sources.default'))")
            assert after_notebook[0] != after_both[0] and after_notebook[1] == 'delta'
            assert sql_state()['pid'] == sql_pid
            print('PASS: notebook-only scope leaves SQL JVM running', flush=True)

            apply('sql', {'spark.sql.sources.default': 'delta', 'spark.sql.shuffle.partitions': 'not-a-number'}, expected='FAILED')
            assert 'Configuration saved' in status.inner_text()
            assert sql_state()['state'] == 'FAILED'
            apply('sql', {'spark.sql.sources.default': 'delta'})
            assert sql_state()['state'] == 'READY'
            assert kernel_value("__import__('os').getpid()") == after_notebook[0]
            print('PASS: invalid Spark startup reports FAILED; fixing the config and saving recovers SQL without restarting notebooks', flush=True)

            job = api('POST', '/lakehouse/api/jobs', {'kind': 'dbt', 'path': 'dbt', 'command': 'debug'})
            deadline = time.monotonic() + 120
            while True:
                run = api('GET', '/lakehouse/api/jobs/' + job['id'])
                if run['status'] in ('SUCCESS', 'FAILED'):
                    assert run['status'] == 'SUCCESS', run.get('log', run)
                    break
                assert time.monotonic() < deadline, 'dbt debug did not finish'
                time.sleep(1)
            assert subprocess.check_output(['docker', 'inspect', NOTEBOOK, '--format', '{{.State.StartedAt}}'], text=True).strip() == server_started
            assert subprocess.check_output(['docker', 'inspect', SQL, '--format', '{{.State.StartedAt}}'], text=True).strip() == sql_started
            assert not errors, errors
            compute.screenshot(path=str(ROOT / 'docs/compute-restart.png'))
            print('PASS: dbt connects after restart; Jupyter and SQL containers never restart; no browser JavaScript errors', flush=True)
        finally:
            if session:
                api('DELETE', '/api/sessions/' + session['id'])
            if created:
                api('DELETE', '/api/contents/' + fixture)
            browser.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        message = traceback.format_exc()
        for name, value in ENV.items():
            if len(value) > 5 and any(part in name for part in ('TOKEN', 'SECRET', 'PASSWORD', 'ACCESS_KEY')):
                message = message.replace(value, '[REDACTED]')
        print('FAIL: ' + message, file=sys.stderr)
        raise SystemExit(1)
