"""Isolated Git UI regression; no .env, R2 or GitHub credentials are used.

Build runtime image first; install requirements-ui.txt and Chromium on the host.
Run: python tests/ui_git_setup.py
Optional LAKEHOUSE_GIT_TEST_IMAGE and LAKEHOUSE_TEST_BROWSER.
Creates/removes one disposable Docker container, workspace and local bare repo.
"""
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request
import uuid

from playwright.sync_api import sync_playwright


def main():
    name='lakehouse-git-ui-'+uuid.uuid4().hex[:10]
    image=os.getenv('LAKEHOUSE_GIT_TEST_IMAGE','r2-lakehouse-v3-runtime:local')
    token='isolated-git-test'
    def docker(*args):
        return subprocess.check_output(['docker',*args],text=True).strip()
    def inside(code):
        return docker('exec',name,'python3','-c',code)
    try:
        docker('run','-d','--name',name,'-p','127.0.0.1::8888',
               '-e','JUPYTER_TOKEN='+token,'-e','UC_URL=http://127.0.0.1:9',
               image,'bash','/opt/lakehouse/start.sh','notebook')
        base='http://'+docker('port',name,'8888/tcp').splitlines()[0]
        for _ in range(90):
            try:
                urllib.request.urlopen(base+'/api/status?token='+token,timeout=2)
                break
            except Exception:time.sleep(1)
        else:raise AssertionError('Jupyter did not start')
        inside("from pathlib import Path; import subprocess; Path('/workspace/local-code').mkdir(); Path('/workspace/local-code/analysis.sql').write_text('SELECT 1;'); Path('/workspace/local-code/.env').write_text('PRIVATE=fixture'); subprocess.run(['git','init','--bare','--initial-branch=main','/tmp/remote.git'],check=True,capture_output=True); subprocess.run(['git','config','--global','url.file:///tmp/remote.git.insteadOf','git@github.com:example/workspace.git'],check=True)")
        with sync_playwright() as pw:
            options={'headless':True}
            if os.getenv('LAKEHOUSE_TEST_BROWSER'):options['executable_path']=os.environ['LAKEHOUSE_TEST_BROWSER']
            browser=pw.chromium.launch(**options)
            page=browser.new_page(viewport={'width':1400,'height':1100})
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.route('**/lakehouse/api/catalogs',lambda route:route.fulfill(json={'catalogs':[]}))
            page.goto(base+'/lab?token='+token)
            page.locator('.lh-sidebar').get_by_role('button',name='GitHub',exact=True).click(timeout=60000)
            panel=page.locator('#lakehouse-GitHub')
            panel.get_by_label('Repository directory inside workspace',exact=True).fill('local-code')
            panel.get_by_label('Existing GitHub repository URL',exact=True).fill('https://github.com/example/workspace')
            panel.get_by_label('Git author name',exact=True).fill('Example Analyst')
            panel.get_by_label('Git author email',exact=True).fill('analyst@example.com')
            panel.get_by_role('button',name='Initialize / connect repository',exact=True).click()
            panel.get_by_text('Repository initialized and connected.',exact=False).wait_for()
            panel.get_by_label('SSH key passphrase',exact=False).fill('fixture passphrase $ with spaces')
            panel.get_by_role('button',name='Create SSH key',exact=True).click()
            panel.get_by_text('Key created. Add the public key',exact=False).wait_for()
            assert panel.get_by_label('Public key to add on GitHub').input_value().startswith('ssh-ed25519 ')
            panel.get_by_role('button',name='Test repository access',exact=True).click()
            panel.get_by_text('SSH read access works; the GitHub repository is empty.',exact=True).wait_for()
            panel.get_by_role('button',name='Review files',exact=True).click()
            panel.get_by_role('checkbox',name='Include analysis.sql',exact=True).wait_for()
            assert panel.get_by_role('checkbox',name='Include .env',exact=True).count()==0
            panel.get_by_role('button',name='Create initial commit',exact=True).click()
            panel.get_by_text('Initial commit created:',exact=False).wait_for()
            panel.get_by_label('Confirm destination SSH URL before first push').fill('git@github.com:example/workspace.git')
            panel.get_by_role('button',name='Push first commit',exact=True).click()
            panel.get_by_text('Pushed main and set its upstream.',exact=False).wait_for()
            panel.get_by_role('button',name='Open native Git panel',exact=True).click()
            page.locator('#jp-git-sessions').wait_for(state='visible')
            # Exercise the real native extension backend, inherited agent and repo.
            inside("from pathlib import Path; Path('/workspace/local-code/analysis.sql').write_text('SELECT 2;')")
            def native(path,data):
                response=page.request.post(base+'/git/local-code/'+path,headers={'Authorization':'token '+token},data=data)
                assert response.ok,(path,response.status,response.text())
                result=response.json();assert result.get('code',0)==0,(path,result)
                return result
            native('add',{'filename':['analysis.sql'],'add_all':False})
            native('commit',{'commit_msg':'Native second commit'})
            native('push',{'top_repo_path':''})
            count=inside("import subprocess; print(subprocess.check_output(['git','--git-dir=/tmp/remote.git','rev-list','--count','main'],text=True).strip())")
            assert count=='2',count
            page.get_by_role('tab',name='GitHub',exact=True).click()
            panel.get_by_role('button',name='Clone existing repository',exact=True).click()
            panel.get_by_text('Repository cloned with automatic .gitignore.',exact=False).wait_for()
            assert panel.get_by_label('Repository directory inside workspace',exact=True).input_value()=='workspace-code'
            assert inside("from pathlib import Path; print(Path('/workspace/workspace-code/analysis.sql').read_text())")=='SELECT 2;'
            panel.get_by_role('button',name='Open native Git panel',exact=True).click()
            page.locator('#jp-git-sessions').wait_for(state='visible')
            assert not errors,errors
            browser.close()
        # File key survives restart, encrypted identity is locked in the new agent.
        docker('restart',name)
        base='http://'+docker('port',name,'8888/tcp').splitlines()[0]
        for _ in range(90):
            try:
                request=urllib.request.Request(base+'/lakehouse/api/git/status',headers={'Authorization':'token '+token})
                state=json.load(urllib.request.urlopen(request,timeout=2));break
            except Exception:time.sleep(1)
        else:raise AssertionError('Restarted Jupyter did not start')
        assert state['ssh']['key_exists'] and not state['ssh']['key_loaded'],state['ssh']
        print('PASS Git UI init+clone/auto-ignore/encrypted key/first push/native panel+commit+push/restart relock; local bare remote only.')
    finally:
        subprocess.run(['docker','rm','-f',name],capture_output=True)


if __name__=='__main__':main()
