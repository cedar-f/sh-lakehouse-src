"""Isolated Files tree/clipboard/metadata UI, no .env or R2 access."""
import os
import subprocess
import time
import urllib.request
import uuid
from urllib.parse import parse_qs,urlparse
from playwright.sync_api import sync_playwright


def main():
    container='file-metadata-ui-'+uuid.uuid4().hex[:10]
    image=os.getenv('LAKEHOUSE_FILES_TEST_IMAGE','r2-lakehouse-v3-runtime:local')
    def docker(*args):return subprocess.check_output(['docker',*args],text=True).strip()
    key='incoming/finance/transactions.csv';prefix='incoming/finance/';calls=[];fail_once=[True]
    try:
        docker('run','-d','--name',container,'-p','127.0.0.1::8888','-e','JUPYTER_TOKEN=fixture',image,'bash','/opt/lakehouse/start.sh','notebook')
        base='http://'+docker('port',container,'8888/tcp').splitlines()[0]
        for _ in range(60):
            try:urllib.request.urlopen(base+'/api/status?token=fixture',timeout=2);break
            except Exception:time.sleep(1)
        else:raise TimeoutError('Jupyter fixture did not start')
        def api(route):
            url=urlparse(route.request.url);path=url.path.split('/lakehouse/api/')[1];q=parse_qs(url.query,keep_blank_values=True)
            if path=='preferences':value={'timezone':'Asia/Ho_Chi_Minh'}
            elif path=='catalogs':value={'catalogs':[]}
            elif path=='files':
                folder=q.get('prefix',[''])[0];calls.append(folder)
                value={'bucket':'fixture','folders':['incoming/'] if not folder else [prefix] if folder=='incoming/' else [],
                    'files':[{'key':key,'size':30,'updated_at':'2026-11-24T00:00:00+00:00'}] if folder==prefix else [],'next_page_token':None}
            elif path=='file':
                target=q['key'][0];kind=q['kind'][0]
                if kind=='file' and fail_once[0]:
                    fail_once[0]=False;route.fulfill(status=400,json={'error':'Fixture metadata temporarily unavailable'});return
                value={'bucket':'fixture','key':target,'kind':kind,'object_id':'fixture/'+target,'object_id_kind':'bucket/key address (not a provider UUID)',
                    'spark_path':'s3a://fixture/'+target,'s3_path':'s3://fixture/'+target,'created_at':None,
                    'created_at_source':'R2 S3 does not report original creation time','virtual':kind=='folder',
                    'note':'Virtual prefix with no independent dates' if kind=='folder' else 'ETag is opaque'}
                if kind=='file':value.update(size=30,updated_at='2026-11-24T00:00:00+00:00',etag='fixture-etag-2',content_type='text/csv',metadata={'source':'fixture'})
            else:raise AssertionError(path)
            route.fulfill(json=value)
        with sync_playwright() as pw:
            options={'headless':True}
            if os.getenv('LAKEHOUSE_TEST_BROWSER'):options['executable_path']=os.environ['LAKEHOUSE_TEST_BROWSER']
            browser=pw.chromium.launch(**options)
            context=browser.new_context(permissions=['clipboard-read','clipboard-write'],viewport={'width':1500,'height':1250},timezone_id='UTC')
            page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.route('**/lakehouse/api/**',api)
            page.goto(base+'/lab?token=fixture')
            page.locator('.lh-sidebar').get_by_role('button',name='Files',exact=True).click()
            panel=page.locator('#lakehouse-Files');folder=panel.locator('.lh-tree-folder[data-prefix="'+prefix+'"]');folder.wait_for()
            assert prefix not in calls and folder.get_attribute('aria-expanded')=='false'
            panel.get_by_role('button',name='Copy path folder '+prefix,exact=True).click()
            panel.get_by_text('Copied: s3a://fixture/'+prefix,exact=True).wait_for()
            assert page.evaluate('navigator.clipboard.readText()')=='s3a://fixture/'+prefix
            assert folder.get_attribute('aria-expanded')=='false'
            panel.get_by_role('button',name='Details folder '+prefix,exact=True).click()
            detail=panel.locator('.lh-file-detail');detail.get_by_text('Virtual folder prefix',exact=True).wait_for()
            assert 'Not reported' in detail.inner_text() and prefix not in calls
            folder.locator(':scope > .lh-tree-row').click()
            panel.get_by_role('link',name='transactions.csv',exact=True).wait_for()
            panel.get_by_role('button',name='Details file '+key,exact=True).click()
            detail.get_by_text('Fixture metadata temporarily unavailable',exact=True).wait_for()
            panel.get_by_role('button',name='Details file '+key,exact=True).click()
            detail.get_by_text('fixture-etag-2',exact=True).wait_for()
            assert '07:00:00 Asia/Ho_Chi_Minh' in detail.inner_text()
            page.evaluate("window.readClipboard = navigator.clipboard.readText.bind(navigator.clipboard); Object.defineProperty(navigator, 'clipboard', {value: undefined})")
            panel.get_by_role('button',name='Copy path file '+key,exact=True).click()
            panel.get_by_text('Copied: s3a://fixture/'+key,exact=True).wait_for()
            assert page.evaluate('window.readClipboard()')=='s3a://fixture/'+key
            detail.get_by_role('button',name='Copy read code',exact=True).click()
            assert '.csv("s3a://fixture/'+key+'")' in page.evaluate('window.readClipboard()')
            if os.getenv('LAKEHOUSE_FILES_SCREENSHOT'):
                panel.evaluate('element=>element.scrollTop=0');page.screenshot(path=os.environ['LAKEHOUSE_FILES_SCREENSHOT'],full_page=True)
            assert not errors,errors
            browser.close()
        print('PASS Files lazy tree, file/folder path copy incl. fallback, metadata/error recovery, UTC-to-workspace timezone and read code')
    finally:subprocess.run(['docker','rm','-f',container],capture_output=True)


if __name__=='__main__':main()
