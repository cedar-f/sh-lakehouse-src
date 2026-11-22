"""Isolated Compute registry UI against fixture API responses, no R2/env access.

Requires Docker runtime image and host tests/requirements-ui.txt + Chromium.
LAKEHOUSE_REGISTRY_TEST_IMAGE selects image; LAKEHOUSE_TEST_BROWSER optional.
"""
import os
import subprocess
import time
import urllib.request
import uuid
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright


def main():
    container='registry-ui-'+uuid.uuid4().hex[:10]
    image=os.getenv('LAKEHOUSE_REGISTRY_TEST_IMAGE','r2-lakehouse-v3-runtime:local')
    def docker(*args):return subprocess.check_output(['docker',*args],text=True).strip()
    try:
        docker('run','-d','--name',container,'-p','127.0.0.1::8888','-e','JUPYTER_TOKEN=ui-fixture',
               image,'bash','/opt/lakehouse/start.sh','notebook')
        base='http://'+docker('port',container,'8888/tcp').splitlines()[0]
        for _ in range(60):
            try:urllib.request.urlopen(base+'/api/status?token=ui-fixture',timeout=2);break
            except Exception:time.sleep(1)
        else:raise RuntimeError('Fixture Jupyter did not start')
        state={'enabled':True,'ready':True,'bucket':'fixture','key':'_lakehouse/registry/v1/current.json',
               'last_sync':1795366800,'pending':False,'counts':{'catalogs':2,'schemas':2,'tables':1,'volumes':1},
               'error':'','nonportable':[{'kind':'volumes','name':'sales.raw.managed_files'}],
               'unrestored':[{'kind':'tables','name':'sales.raw.old_managed','reason':'Managed inventory requires separate recovery'}]}
        sync_calls=[]
        def api(route):
            path=urlparse(route.request.url).path.split('/lakehouse/api/')[1]
            if path=='catalogs':value={'catalogs':[]}
            elif path=='cluster':value={'threads':'2','driver_memory':'2g','shuffle_partitions':8,
                'default_catalog':'sales','default_schema':'raw','extra':{},'kernels':[],
                'sql_status':'RUNNING','cpu_visible':2,'restart':None}
            elif path=='preferences':value={'timezone':'Asia/Ho_Chi_Minh'}
            elif path=='catalog-registry/sync':
                assert route.request.method=='POST';sync_calls.append(path)
                state.update(ready=False,pending=True,error='Fixture ETag conflict');value=state
            elif path=='catalog-registry':value=state
            else:raise AssertionError(path)
            route.fulfill(json=value)
        with sync_playwright() as pw:
            options={'headless':True}
            if os.getenv('LAKEHOUSE_TEST_BROWSER'):options['executable_path']=os.environ['LAKEHOUSE_TEST_BROWSER']
            browser=pw.chromium.launch(**options)
            page=browser.new_page(viewport={'width':1400,'height':1100},timezone_id='UTC')
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.route('**/lakehouse/api/**',api)
            page.goto(base+'/lab?token=ui-fixture')
            page.locator('.lh-sidebar').get_by_role('button',name='Compute',exact=True).click(timeout=60000)
            panel=page.locator('#lakehouse-Compute')
            panel.get_by_role('heading',name='Catalog registry on R2',exact=True).wait_for()
            panel.get_by_text('catalogs: 2',exact=True).wait_for()
            panel.get_by_text('tables sales.raw.old_managed: not restored',exact=False).wait_for()
            panel.get_by_text('volumes sales.raw.managed_files: inventory saved',exact=False).wait_for()
            assert 'Asia/Ho_Chi_Minh' in panel.inner_text()
            panel.get_by_role('button',name='Sync registry now',exact=True).click()
            panel.get_by_text('Fixture ETag conflict',exact=True).wait_for()
            assert sync_calls==['catalog-registry/sync']
            state.update(enabled=False)
            panel.get_by_role('button',name='Refresh registry status',exact=True).click()
            panel.get_by_text('Registry disabled.',exact=False).wait_for()
            assert not errors,errors
            browser.close()
        print('PASS registry Compute counts/unrestored/pending/manual sync/disabled/configured timezone; API fixtures only.')
    finally:
        subprocess.run(['docker','rm','-f',container],capture_output=True)


if __name__=='__main__':main()
