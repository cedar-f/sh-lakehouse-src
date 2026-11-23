"""Isolated Jupyter dbt/workflow UI contracts, API fixtures only; no .env/R2."""
import os
import subprocess
import time
import urllib.request
import uuid
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright


def main():
    container = 'dbt-project-ui-'+uuid.uuid4().hex[:10]
    image = os.getenv('LAKEHOUSE_DBT_TEST_IMAGE', 'r2-lakehouse-v3-runtime:local')
    def docker(*args):
        return subprocess.check_output(['docker', *args], text=True).strip()
    old = {'id': 'legacy_flow', 'nodes': [{'id': 'legacy_build', 'kind': 'dbt', 'path': 'dbt_old',
           'command': 'build', 'catalog': 'old', 'schema': 'existing', 'dependsOn': [], 'x': 30, 'y': 40}]}
    jobs, published = [], []
    try:
        docker('run', '-d', '--name', container, '-p', '127.0.0.1::8888', '-e', 'JUPYTER_TOKEN=fixture',
               image, 'bash', '/opt/lakehouse/start.sh', 'notebook')
        base = 'http://'+docker('port', container, '8888/tcp').splitlines()[0]
        for _ in range(60):
            try:urllib.request.urlopen(base+'/api/status?token=fixture', timeout=2);break
            except Exception:time.sleep(1)
        else:raise TimeoutError('Jupyter fixture did not start')
        def api(route):
            path = urlparse(route.request.url).path.split('/lakehouse/api/')[1]
            if path == 'catalogs':value = {'catalogs': []}
            elif path == 'preferences':value = {'timezone': 'Asia/Ho_Chi_Minh'}
            elif path == 'flows' and route.request.method == 'GET':value = [old]
            elif path == 'flows':published.append(route.request.post_data_json);value = {'saved': True}
            elif path == 'jobs':jobs.append(route.request.post_data_json);value = {'id': 'fixture-run'}
            elif path.startswith('docs/latest'):value = {'run_id': 'docs-fixture'}
            else:raise AssertionError(path)
            route.fulfill(json=value)
        with sync_playwright() as pw:
            options = {'headless': True}
            if os.getenv('LAKEHOUSE_TEST_BROWSER'):options['executable_path'] = os.environ['LAKEHOUSE_TEST_BROWSER']
            browser = pw.chromium.launch(**options)
            page = browser.new_page(viewport={'width': 1400, 'height': 1000})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.route('**/lakehouse/api/**', api)
            page.context.route('**/lakehouse/docs/**', lambda route: route.fulfill(body='<h1>Fixture Docs</h1>', content_type='text/html'))
            page.goto(base+'/lab?token=fixture')
            page.locator('.lh-sidebar').get_by_role('button', name='dbt', exact=True).click()
            panel = page.locator('#lakehouse-dbt')
            panel.get_by_text('Declare vars.lakehouse_catalog', exact=False).wait_for()
            assert not panel.get_by_label('Legacy target schema (optional)').is_visible()
            panel.get_by_label('Project directory in workspace').fill('.')
            panel.get_by_role('button', name='build', exact=True).click()
            dialog = page.locator('.jp-Dialog')
            dialog.wait_for()
            assert 'dbt queued' in dialog.inner_text(), dialog.inner_text()
            dialog.locator('button').last.click()
            assert jobs == [{'kind': 'dbt', 'path': '.', 'command': 'build', 'select': '', 'catalog': '', 'schema': ''}]
            with page.expect_popup() as popup:
                panel.get_by_role('button', name='Open Docs', exact=True).click()
            popup.value.get_by_text('Fixture Docs').wait_for()
            popup.value.close()
            page.locator('.lh-sidebar').get_by_role('button', name='Workflows', exact=True).click()
            panel = page.locator('#lakehouse-Workflows')
            panel.get_by_role('combobox', name='Saved workflow').select_option('legacy_flow')
            panel.get_by_role('button', name='Load', exact=True).click()
            panel.locator('.lh-node').filter(has_text='legacy_build').click()
            assert panel.get_by_label('Legacy target schema (optional)').input_value() == 'existing'
            assert panel.get_by_label('Legacy target schema (optional)').is_visible()
            panel.get_by_role('button', name='Save & publish to Kestra').click()
            panel.get_by_text('Published.', exact=False).wait_for()
            assert published[-1]['nodes'][0]['schema'] == 'existing'
            assert published[-1]['nodes'][0]['catalog'] == 'old'
            panel.get_by_role('button', name='New workflow', exact=True).click()
            panel.get_by_role('button', name='+ dbt', exact=True).click()
            panel.get_by_text('Catalog and model schemas come from', exact=False).wait_for()
            assert not panel.get_by_label('Legacy target schema (optional)').is_visible()
            assert not errors, errors
            browser.close()
        print('PASS dbt project UI, root path, Open Docs, hidden legacy fields, preserved legacy workflow settings')
    finally:
        subprocess.run(['docker', 'rm', '-f', container], capture_output=True)


if __name__ == '__main__':
    main()
