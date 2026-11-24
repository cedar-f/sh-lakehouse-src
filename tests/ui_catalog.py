"""Catalog UI regressions with fixture API; no R2, user tables or .env."""
import json
import os
import subprocess
import time
import urllib.request
import uuid
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import sync_playwright


def main():
    name='catalog-ui-'+uuid.uuid4().hex[:10]
    image=os.getenv('LAKEHOUSE_CATALOG_UI_IMAGE','r2-lakehouse-v3-runtime:local')
    def docker(*args):return subprocess.check_output(['docker',*args],text=True).strip()
    tables=['one','two'];functions=[];deletes=[];creates=[];function_deletes=[];views=[];view_creates=[];view_deletes=[]
    try:
        docker('run','-d','--name',name,'-p','127.0.0.1::8888','-e','JUPYTER_TOKEN=fixture',
               image,'bash','/opt/lakehouse/start.sh','notebook')
        base='http://'+docker('port',name,'8888/tcp').splitlines()[0]
        for _ in range(60):
            try:urllib.request.urlopen(base+'/api/status?token=fixture',timeout=2);break
            except Exception:time.sleep(1)
        else:raise TimeoutError('Jupyter did not start')
        def api(route):
            url=urlparse(route.request.url);path=url.path.split('/lakehouse/api/')[1];q=parse_qs(url.query)
            if path=='preferences':value={'timezone':'Asia/Ho_Chi_Minh'}
            elif path=='catalogs':value={'catalogs':[{'name':'alpha'},{'name':'sales'}]}
            elif path=='schemas':value={'schemas':[{'name':'raw'},{'name':'clean'}]}
            elif path=='tables':
                cat=q['catalog'][0];sch=q['schema'][0]
                value={'tables':[{'name':n,'full_name':cat+'.'+sch+'.'+n,'table_type':'EXTERNAL','data_source_format':'DELTA','table_id':'table-id-'+n,'created_at':1795478400000,'updated_at':1795482000000} for n in tables]+views}
            elif path=='volumes':value={'volumes':[]}
            elif path=='functions' and route.request.method=='GET':value={'functions':functions}
            elif path=='functions':
                d=route.request.post_data_json;creates.append(d)
                f={'name':d['name'],'full_name':d['catalog_name']+'.'+d['schema_name']+'.'+d['name'],
                   'routine_body':'EXTERNAL','external_language':'PYTHON','full_data_type':d['return_type'],
                   'routine_definition':d['body'],'comment':d['comment'],'is_deterministic':False,'sql_data_access':'NO_SQL',
                   'input_params':{'parameters':[{'name':p['name'],'type_text':p['type'].lower()} for p in d['parameters']]}}
                functions.append(f);value=f
            elif path=='function':value=next(f for f in functions if f['full_name']==q['name'][0])
            elif path=='catalog':value={'name':'sales','id':'catalog-fixture-id','created_at':1795478400000,'owner':'analyst','storage_root':'s3://fixture/warehouse/sales'}
            elif path=='schema':value={'name':'clean','schema_id':'schema-fixture-id','catalog_name':'sales','created_at':1795478400000}
            elif path=='views':
                d=route.request.post_data_json;view_creates.append(d)
                value={'name':d['name'].split('.')[-1],'full_name':d['name'],'table_type':'VIEW','table_id':'view-fixture-id','created_at':1795478400000,'comment':d['comment'],'view_definition':d['sql'],'view_dependencies':{'dependencies':[]},'columns':[{'name':'answer','type_text':'int','nullable':False,'position':0}]};views.append(value)
            elif path=='views/delete':
                d=route.request.post_data_json;view_deletes.append(d);views.clear();value={'results':[{'name':n,'status':'DELETED'} for n in d['names']],'deleted':len(d['names'])}
            elif path=='functions/delete':
                d=route.request.post_data_json;function_deletes.append(d);functions.clear();value={}
            elif path=='table':value=next((v for v in views if v['full_name']==q['name'][0]),{'columns':[{'name':'id','type_text':'int'}],'table_id':'table-fixture-id','created_at':1795478400000,'table_type':'EXTERNAL','storage_location':'s3://fixture/one'})
            elif path=='tables/delete':
                d=route.request.post_data_json;deletes.append(d);results=[]
                for index,full in enumerate(d['names']):
                    failed=len(deletes)==1 and index==1
                    results.append({'name':full,'status':'FAILED' if failed else 'DELETED','error':'Fixture pending' if failed else ''})
                    if not failed:tables.remove(full.split('.')[-1])
                value={'results':results}
            else:raise AssertionError(path)
            route.fulfill(json=value)
        with sync_playwright() as pw:
            opts={'headless':True}
            if os.getenv('LAKEHOUSE_TEST_BROWSER'):opts['executable_path']=os.environ['LAKEHOUSE_TEST_BROWSER']
            browser=pw.chromium.launch(**opts);context=browser.new_context(permissions=['clipboard-read','clipboard-write'],viewport={'width':1450,'height':1050})
            page=context.new_page();errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)));page.route('**/lakehouse/api/**',api)
            page.goto(base+'/lab?token=fixture');page.locator('.lh-sidebar').get_by_role('button',name='Catalog',exact=True).click()
            panel=page.locator('#lakehouse-Catalog')
            panel.get_by_label('Catalog',exact=True).select_option('sales')
            panel.get_by_label('Schema',exact=True).select_option('clean')
            panel.get_by_label('Asset type').select_option('tables');panel.get_by_label('Search catalog assets').fill('one')
            panel.get_by_role('button',name='one',exact=True).wait_for()
            panel.get_by_role('button',name='Copy full name',exact=True).first.click()
            panel.get_by_text('Copied: sales.clean.one',exact=True).wait_for()
            assert page.evaluate('navigator.clipboard.readText()')=='sales.clean.one'
            panel.get_by_role('button',name='one',exact=True).click()
            panel.locator('.lh-asset-properties').get_by_text('table-fixture-id',exact=True).wait_for()
            assert 'Asia/Ho_Chi_Minh' in panel.inner_text()
            panel.get_by_role('button',name='Refresh',exact=True).click()
            panel.get_by_role('button',name='one',exact=True).wait_for()
            assert panel.get_by_label('Catalog',exact=True).input_value()=='sales'
            assert panel.get_by_label('Schema',exact=True).input_value()=='clean'
            assert panel.get_by_label('Asset type').input_value()=='tables'
            assert panel.get_by_label('Search catalog assets').input_value()=='one'
            panel.get_by_label('Search catalog assets').fill('')
            page.evaluate("window.readClipboard = navigator.clipboard.readText.bind(navigator.clipboard); Object.defineProperty(navigator, 'clipboard', {value: undefined})")
            panel.get_by_role('button',name='Copy full name',exact=True).nth(1).click()
            panel.get_by_text('Copied: sales.clean.two',exact=True).wait_for()
            assert page.evaluate('window.readClipboard()')=='sales.clean.two'
            panel.get_by_label('Select all visible tables',exact=True).check()
            panel.get_by_role('button',name='Delete selected tables',exact=True).click()
            dialog=page.locator('.jp-Dialog');dialog.get_by_role('button',name='Cancel',exact=True).click()
            assert not deletes
            panel.get_by_role('button',name='Delete selected tables',exact=True).click()
            dialog.get_by_label('Type DELETE to confirm').fill('DELETE');dialog.get_by_role('button',name='Delete selected',exact=True).click()
            panel.get_by_text('Fixture pending',exact=True).wait_for()
            panel.get_by_text('1 tables selected (max 100)',exact=True).wait_for()
            assert deletes[0]['names']==['sales.clean.one','sales.clean.two']
            assert deletes[0]['confirmed_names']==deletes[0]['names']
            panel.get_by_role('button',name='Delete selected tables',exact=True).click()
            dialog.get_by_label('Type DELETE to confirm').fill('DELETE');dialog.get_by_role('button',name='Delete selected',exact=True).click()
            panel.get_by_text('0 tables selected (max 100)',exact=True).wait_for()
            assert deletes[1]['names']==['sales.clean.two']
            panel.get_by_role('button',name='+ Function',exact=True).click()
            panel.get_by_label('Function name',exact=True).fill('increment')
            panel.get_by_label('Description',exact=True).fill('Increment an integer')
            panel.get_by_role('button',name='Register function',exact=True).click()
            panel.get_by_role('heading',name='sales.clean.increment',exact=True).wait_for()
            panel.get_by_label('Asset type').select_option('functions')
            panel.get_by_role('button',name='increment',exact=True).wait_for()
            if os.getenv('LAKEHOUSE_CATALOG_SCREENSHOT'):
                page.screenshot(path=os.environ['LAKEHOUSE_CATALOG_SCREENSHOT'],full_page=True)
            assert creates[0]['catalog_name']=='sales' and creates[0]['schema_name']=='clean'
            assert creates[0]['body']=='return value + 1'
            panel.get_by_role('button',name='Delete function',exact=True).first.click()
            dialog.locator('input').fill('sales.clean.increment');dialog.locator('button').last.click()
            panel.get_by_text('Deleted function: sales.clean.increment',exact=True).wait_for()
            assert function_deletes==[{'name':'sales.clean.increment','confirmation':'sales.clean.increment'}]
            panel.get_by_role('button',name='Catalog details',exact=True).click()
            panel.locator('.lh-asset-properties').get_by_text('catalog-fixture-id',exact=True).wait_for()
            panel.get_by_role('button',name='Schema details',exact=True).click()
            panel.locator('.lh-asset-properties').get_by_text('schema-fixture-id',exact=True).wait_for()
            panel.get_by_role('button',name='+ View',exact=True).click()
            panel.get_by_label('View name',exact=True).fill('answer_view')
            panel.get_by_label('View SELECT query',exact=True).fill('SELECT 42 AS answer')
            panel.get_by_label('View description',exact=True).fill('A persistent SQL view')
            panel.get_by_role('button',name='Create view',exact=True).click()
            panel.get_by_role('heading',name='sales.clean.answer_view',exact=True).wait_for()
            panel.locator('.lh-asset-properties').get_by_text('view-fixture-id',exact=True).wait_for()
            panel.get_by_label('Asset type').select_option('views')
            panel.get_by_label('Search catalog assets').fill('answer')
            panel.get_by_role('button',name='Refresh',exact=True).click()
            panel.get_by_role('button',name='answer_view',exact=True).wait_for()
            assert panel.get_by_label('Asset type').input_value()=='views' and panel.get_by_label('Search catalog assets').input_value()=='answer'
            assert view_creates[0]['name']=='sales.clean.answer_view'
            panel.get_by_role('button',name='Copy definition',exact=True).click()
            assert page.evaluate('window.readClipboard()')=='SELECT 42 AS answer'
            if os.getenv('LAKEHOUSE_CATALOG_SCREENSHOT'):page.screenshot(path=os.environ['LAKEHOUSE_CATALOG_SCREENSHOT'],full_page=True)
            panel.get_by_label('Select view sales.clean.answer_view',exact=True).check()
            panel.get_by_role('button',name='Delete selected views',exact=True).click()
            dialog.get_by_label('Type DELETE to confirm').fill('DELETE');dialog.get_by_role('button',name='Delete views',exact=True).click()
            panel.get_by_text('No matching assets.',exact=True).wait_for()
            assert view_deletes[0]['names']==['sales.clean.answer_view']
            assert not errors,errors
            browser.close()
        print('PASS Catalog filters, audit metadata/timezone, copy/delete, function and native-view UI contracts')
    finally:subprocess.run(['docker','rm','-f',name],capture_output=True)


if __name__=='__main__':main()
