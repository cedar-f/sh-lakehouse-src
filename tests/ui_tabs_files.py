"""UI regression checks against a running V3 (only incoming/ test files are written).

Install tests/requirements-ui.txt and run `python -m playwright install chromium`.
Run from the project directory: python tests/ui_tabs_files.py
Optional: LAKEHOUSE_TEST_URL and LAKEHOUSE_TEST_BROWSER.
"""
import json
import os
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import boto3
from botocore.config import Config
from playwright.sync_api import sync_playwright


ROOT=Path(__file__).resolve().parents[1]
ENV=dict(line.split('=',1) for line in (ROOT/'.env').read_text(encoding='utf-8-sig').splitlines()
         if '=' in line and not line.startswith('#'))
URL=os.getenv('LAKEHOUSE_TEST_URL','http://127.0.0.1:8888').rstrip('/')
PREFIX='incoming/000_ui_tree_'+uuid.uuid4().hex[:12]+'/'
FILES={PREFIX+'readme.txt':b'Tree regression',PREFIX+'nested/data.csv':b'id\n1\n',
       PREFIX+'nested/deeper/info.json':b'{"ok":true}',PREFIX+'empty/':b''}
UPLOADED=PREFIX+'nested/uploaded.txt'


def main():
    client=boto3.client('s3',endpoint_url=ENV.get('S3_ENDPOINT') or
        'https://'+ENV['R2_ACCOUNT_ID']+'.r2.cloudflarestorage.com',region_name='auto',
        aws_access_key_id=ENV['R2_ACCESS_KEY_ID'],aws_secret_access_key=ENV['R2_SECRET_ACCESS_KEY'],
        config=Config(signature_version='s3v4'))
    bucket=ENV['R2_BUCKET']
    try:
        for key,body in FILES.items():client.put_object(Bucket=bucket,Key=key,Body=body)
        with sync_playwright() as playwright:
            options={'headless':True}
            if os.getenv('LAKEHOUSE_TEST_BROWSER'):options['executable_path']=os.environ['LAKEHOUSE_TEST_BROWSER']
            browser=playwright.chromium.launch(**options)
            page=browser.new_page(viewport={'width':1450,'height':1000})
            errors=[];requests=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            def requested(request):
                if '/lakehouse/api/files?' in request.url:
                    requests.append(parse_qs(urlparse(request.url).query,keep_blank_values=True).get('prefix',[''])[0])
            page.on('request',requested)
            page.goto(URL+'/lab',wait_until='domcontentloaded')
            page.get_by_label('Password or token:').fill(ENV['JUPYTER_TOKEN'])
            page.get_by_role('button',name='Log in',exact=True).click()
            page.get_by_role('heading',name='Catalog',exact=True).wait_for(timeout=60000)

            def open_panel(name,heading):
                page.locator('.lh-sidebar').get_by_role('button',name=name,exact=True).click()
                page.get_by_role('heading',name=heading,exact=True).wait_for(timeout=45000)
                assert page.locator('#lakehouse-'+name).count()==1

            def close_panel(name):
                tab=page.get_by_role('tab',name=name,exact=True)
                tab.locator('.lm-TabBar-tabCloseIcon').click()
                tab.wait_for(state='detached')

            headings={'Catalog':'Catalog','Files':'Files on R2','Compute':'Compute','SQL':'SQL editor',
                'dbt':'dbt','Runs':'Runs','Workflows':'Workflows','GitHub':'GitHub','Notebook':'Run saved notebook'}
            for name,heading in headings.items():
                open_panel(name,heading)
                for _ in range(2):close_panel(name);open_panel(name,heading)
                close_panel(name)
            print('PASS: all 9 panels close/reopen twice without reload',flush=True)
            open_panel('SQL','SQL editor')
            page.get_by_label('Spark SQL',exact=True).fill('SELECT 42 AS preserved_edit')
            close_panel('SQL');open_panel('SQL','SQL editor')
            assert page.get_by_label('Spark SQL',exact=True).input_value()=='SELECT 42 AS preserved_edit'
            close_panel('SQL')

            open_panel('Files','Files on R2')
            tree=page.get_by_role('tree',name='R2 file tree')
            def folder(prefix):return tree.locator('.lh-tree-folder[data-prefix="'+prefix+'"]')
            root_folder=folder('');root_folder.wait_for()
            root_folder.locator(':scope > .lh-tree-row .lh-tree-name').filter(has_text='r2://').wait_for()
            fixture=folder(PREFIX);fixture.wait_for(timeout=30000)
            assert PREFIX not in requests and PREFIX+'nested/' not in requests
            fixture.locator(':scope > .lh-tree-row').click()
            fixture.get_by_role('link',name='readme.txt',exact=True).wait_for()
            assert PREFIX in requests and PREFIX+'nested/' not in requests
            fixture.locator(':scope > .lh-tree-row').click()
            assert not fixture.get_by_role('link',name='readme.txt',exact=True).is_visible()
            before=requests.count(PREFIX)
            fixture.locator(':scope > .lh-tree-row').click()
            assert requests.count(PREFIX)==before
            nested=folder(PREFIX+'nested/');nested.locator(':scope > .lh-tree-row').click()
            nested.get_by_role('link',name='data.csv',exact=True).wait_for()
            assert PREFIX+'nested/deeper/' not in requests
            assert page.get_by_label('Upload folder',exact=True).input_value()==PREFIX+'nested/'
            close_panel('Files');open_panel('Files','Files on R2')
            assert nested.get_attribute('aria-expanded')=='true'
            assert nested.get_by_role('link',name='data.csv',exact=True).is_visible()
            nested.focus();page.keyboard.press('ArrowLeft')
            assert nested.get_attribute('aria-expanded')=='false'
            page.keyboard.press('ArrowRight')
            assert nested.get_attribute('aria-expanded')=='true'
            folder(PREFIX+'nested/deeper/').locator(':scope > .lh-tree-row').click()
            folder(PREFIX+'nested/deeper/').get_by_role('link',name='info.json',exact=True).wait_for()
            folder(PREFIX+'empty/').locator(':scope > .lh-tree-row').click()
            folder(PREFIX+'empty/').get_by_text('Empty folder',exact=True).wait_for()
            # Return to the nested upload destination without collapsing it.
            nested.focus();page.keyboard.press('Enter');page.keyboard.press('Enter')
            page.locator('.lh-drop input[type="file"]').set_input_files(
                {'name':'uploaded.txt','mimeType':'text/plain','buffer':b'Uploaded through the tree'})
            nested.get_by_role('link',name='uploaded.txt',exact=True).wait_for(timeout=45000)
            response=client.get_object(Bucket=bucket,Key=UPLOADED)
            try:assert response['Body'].read()==b'Uploaded through the tree'
            finally:response['Body'].close()
            assert '/lakehouse/api/download?key=' in nested.get_by_role('link',name='uploaded.txt',exact=True).get_attribute('href')
            page.locator('#lakehouse-Files').screenshot(path=str(ROOT/'docs/files-tree.png'))
            print('PASS: real R2 nesting, lazy loading, collapse/reopen, keyboard and upload to selected folder',flush=True)

            # Exercise pagination and retry using deterministic responses for one UI-only folder.
            paged='incoming/ui_pagination_check/'
            state={'failed_once':False}
            def route_files(route):
                query=parse_qs(urlparse(route.request.url).query,keep_blank_values=True)
                prefix=query.get('prefix',[''])[0]
                if prefix==paged:
                    if not state['failed_once']:
                        state['failed_once']=True;route.fulfill(status=503,json={'error':'Temporary test failure'});return
                    second=bool(query.get('page_token'))
                    route.fulfill(json={'bucket':bucket,'folders':[],
                        'files':[{'key':paged+('second.txt' if second else 'first.txt'),'size':5}],
                        'next_page_token':None if second else 'page-2'});return
                response=route.fetch();data=response.json()
                if prefix=='incoming/':data['folders']=list(dict.fromkeys([*data['folders'],paged]))
                route.fulfill(response=response,json=data)
            page.route('**/lakehouse/api/files?**',route_files)
            page.get_by_role('button',name='Refresh tree',exact=True).click()
            paged_node=folder(paged);paged_node.wait_for(timeout=30000)
            paged_node.locator(':scope > .lh-tree-row').click()
            paged_node.get_by_role('button',name='Retry',exact=True).click()
            paged_node.get_by_role('link',name='first.txt',exact=True).wait_for()
            paged_node.get_by_role('button',name='Load more in ui_pagination_check',exact=True).click()
            paged_node.get_by_role('link',name='second.txt',exact=True).wait_for()
            assert paged_node.get_by_role('link',name='first.txt',exact=True).count()==1
            assert paged_node.get_by_role('button',name='Load more in ui_pagination_check',exact=True).count()==0
            assert not errors,errors
            print('PASS: paginated tree appends files, retries failures and has no page errors',flush=True)
            page.unroute_all(behavior='wait')
            browser.close()
    finally:
        for key in [*FILES,UPLOADED]:client.delete_object(Bucket=bucket,Key=key)


if __name__=='__main__':main()
