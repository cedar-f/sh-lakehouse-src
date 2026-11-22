"""Git setup regression tests use temporary homes/repositories, never GitHub."""
import os
from pathlib import Path
import subprocess

import pytest

import git_integration as gi


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    home, root = tmp_path / 'home', tmp_path / 'workspace'
    home.mkdir(); root.mkdir()
    monkeypatch.setenv('HOME', str(home))
    for name in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_CONFIG_GLOBAL', 'GIT_CONFIG_SYSTEM'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('GIT_CONFIG_NOSYSTEM', '1')
    helper = home / 'askpass'
    helper.write_text(gi.ASKPASS.read_text()); helper.chmod(0o700)
    monkeypatch.setattr(gi, 'ASKPASS', helper)
    agent = subprocess.Popen(['ssh-agent', '-D', '-a', str(gi.ssh_home() / 'lakehouse-agent.sock')],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    import time
    for _ in range(100):
        if gi.run(['ssh-add', '-l'], env=gi.agent_env(), check=False).returncode in (0, 1):break
        time.sleep(.02)
    try:yield root
    finally:
        agent.terminate(); agent.wait(timeout=10)


def connect(root, **changes):
    return gi.configure({'path': '.', 'remote': 'https://github.com/example/workspace',
                         'branch': 'main', 'name': 'Example Analyst', 'email': 'analyst@example.com', **changes}, root)


def commit(root):
    view = gi.preview('.', root)
    return gi.initial_commit({'path': '.', 'token': view['token'],
                              'files': [f['path'] for f in view['files'] if not f['blocked']],
                              'message': 'Initial commit'}, root)


@pytest.mark.parametrize('value', ['https://evil.example/a/b', 'ssh://root@github.com/a/b',
    'https://token@github.com/a/b', 'git@github.com:a/b;whoami', '-u root', 'https://github.com/a/../b'])
def test_remote_validation(value):
    with pytest.raises(ValueError):gi.github_remote(value)


def test_github_url_is_normalized():
    assert gi.github_remote('https://github.com/example/workspace.git') == 'git@github.com:example/workspace.git'
    assert gi.github_remote('git@github.com:example/workspace.git') == 'git@github.com:example/workspace.git'


def test_encrypted_key_unlocked_for_independent_native_git_process(workspace):
    phrase = 'test phrase with spaces $ and quotes "'
    created = gi.create_key({'passphrase': phrase})
    assert created['key_exists'] and created['key_loaded'] and created['public_key'].startswith('ssh-ed25519 ')
    private = Path(created['key_path'])
    assert private.stat().st_mode & 0o777 == 0o600
    before = private.read_bytes()
    with pytest.raises(ValueError, match='already exists'):gi.create_key({'passphrase': 'new'})
    assert private.read_bytes() == before
    gi.run(['ssh-add', '-D'], env=gi.agent_env())
    with pytest.raises(ValueError, match='passphrase'):gi.unlock({'passphrase': 'wrong'})
    assert not gi.key_status()['key_loaded']
    gi.unlock({'passphrase': phrase})
    # No passphrase is passed to this separate process. It uses the same socket
    # that the Jupyter server/native Git subprocess inherits at startup.
    env = {**os.environ, 'SSH_AUTH_SOCK': str(private.parent / 'lakehouse-agent.sock')}
    result = subprocess.run(['ssh-add', '-T', str(private.with_suffix('.pub'))], env=env, capture_output=True)
    assert result.returncode == 0
    assert phrase not in str(created)


def test_passwordless_key_and_pinned_host_key(workspace):
    assert gi.create_key({})['key_loaded']
    command = gi.ssh_command()
    assert 'StrictHostKeyChecking=yes' in command and 'BatchMode=yes' in command
    assert (Path.home()/'.ssh/lakehouse_known_hosts').read_text().startswith('github.com ssh-ed25519 ')


def test_init_preview_commit_and_native_second_commit(workspace):
    (workspace/'analysis.sql').write_text('SELECT 1;')
    (workspace/'.env').write_text('PRIVATE=not-for-git')
    (workspace/'private.txt').write_text('-----BEGIN OPENSSH PRIVATE KEY-----\nfixture')
    state = connect(workspace)
    assert state['branch'] == 'main' and not state['head']
    view = gi.preview('.', workspace)
    assert '.env' not in {f['path'] for f in view['files']}
    assert next(f for f in view['files'] if f['path']=='private.txt')['blocked']
    result = commit(workspace)
    assert result['committed'] == 2 and not result['pushed']
    tracked = gi.git(['ls-files'], workspace).stdout.decode().splitlines()
    assert tracked == ['.gitignore', 'analysis.sql']
    # Native Git commands reuse the same repository and local author config.
    (workspace/'analysis.sql').write_text('SELECT 2;')
    gi.git(['add', 'analysis.sql'], workspace);gi.git(['commit', '-m', 'Second commit'], workspace)
    assert gi.text(['rev-list', '--count', 'HEAD'], workspace) == '2'
    with pytest.raises(ValueError, match='already has commits'):gi.preview('.', workspace)


def test_changed_preview_and_unreviewed_staging_cannot_be_committed(workspace):
    connect(workspace)
    (workspace/'a.sql').write_text('SELECT 1')
    view = gi.preview('.', workspace)
    (workspace/'a.sql').write_text('SELECT 2')
    payload = {'token': view['token'], 'files': ['a.sql'], 'message': 'first'}
    with pytest.raises(ValueError, match='changed'):gi.initial_commit(payload, workspace)
    gi.git(['add', '.gitignore'], workspace)
    payload['token'] = gi.preview('.', workspace)['token']
    with pytest.raises(ValueError, match='Other files'):gi.initial_commit(payload, workspace)
    assert not gi.text(['rev-parse', '--verify', 'HEAD'], workspace)


def test_path_boundaries_and_existing_remote_are_preserved(workspace, tmp_path):
    outside = tmp_path/'outside';outside.mkdir()
    (workspace/'escape').symlink_to(outside, target_is_directory=True)
    for path in ('..', '../outside', str(outside), 'escape'):
        with pytest.raises(ValueError):gi.workspace_path(path, workspace)
    connect(workspace)
    (workspace/'nested').mkdir()
    with pytest.raises(ValueError, match='inside another'):gi.workspace_path('nested', workspace)
    with pytest.raises(ValueError, match='another repository'):connect(workspace, remote='git@github.com:example/other.git')
    assert gi.status('.', workspace)['remote'] == 'git@github.com:example/workspace.git'


def test_first_push_sets_upstream_and_rejects_nonempty_remote(workspace, tmp_path, monkeypatch):
    connect(workspace);commit(workspace)
    remote = tmp_path/'remote.git'
    subprocess.run(['git', 'init', '--bare', str(remote)], capture_output=True, check=True)
    # Redirect the public URL to a local bare repository: no credentials/network.
    gi.git(['config', '--local', 'url.'+remote.as_uri()+'.insteadOf', 'git@github.com:example/workspace.git'], workspace)
    original_text=gi.text
    monkeypatch.setattr(gi,'text',lambda args,path,default='':
        'git@github.com:example/workspace.git' if args==['remote','get-url','origin'] else original_text(args,path,default))
    payload={'confirmation':'git@github.com:example/workspace.git'}
    assert gi.initial_push(payload, workspace)['pushed']
    assert gi.status('.', workspace)['upstream']=='origin/main'
    assert gi.initial_push(payload, workspace)['pushed']  # idempotent retry
    (workspace/'next.sql').write_text('SELECT 2')
    gi.git(['add','next.sql'],workspace);gi.git(['commit','-m','next'],workspace)
    with pytest.raises(ValueError, match='not empty'):gi.initial_push(payload, workspace)
    # Ordinary native Git push is permitted after onboarding.
    gi.git(['push'],workspace)
    assert gi.run(['git','--git-dir',str(remote),'rev-parse','main']).stdout.decode().strip()==gi.status('.',workspace)['head']


def test_symbolic_ignore_is_rejected_before_init(workspace, tmp_path):
    target=tmp_path/'ignore';target.write_text('keep me')
    (workspace/'.gitignore').symlink_to(target)
    with pytest.raises(ValueError, match='symlink'):connect(workspace)
    assert target.read_text()=='keep me' and not (workspace/'.git').exists()


def test_ignore_preserves_custom_rules_and_updates_managed_block(workspace):
    ignore=workspace/'.gitignore'
    ignore.write_text('custom-data/\n')
    connect(workspace); first=ignore.read_text()
    connect(workspace)
    assert ignore.read_text()==first and first.startswith('custom-data/\n')
    for name in ('.env', 'nested/profiles.yml', 'nested/key.pem', 'backups/a.txt', 'dbt/target/a.json'):
        assert subprocess.run(['git','check-ignore',name],cwd=workspace,capture_output=True).returncode==0
    assert subprocess.run(['git','check-ignore','.env.example'],cwd=workspace,capture_output=True).returncode!=0
    ignore.write_text(first.replace('*.pem\n',''))
    connect(workspace)
    assert '*.pem\n' in ignore.read_text() and ignore.read_text().count('# BEGIN Lakehouse')==1


def test_clone_existing_repository_and_native_git_handoff(workspace, tmp_path, monkeypatch):
    source=tmp_path/'source';source.mkdir()
    subprocess.run(['git','init','--initial-branch=main',str(source)],check=True,capture_output=True)
    gi.git(['config','user.name','Fixture'],source);gi.git(['config','user.email','fixture@example.com'],source)
    (source/'model.sql').write_text('SELECT 1;')
    (source/'.gitignore').write_text('my-custom/\n')
    gi.git(['add','.'],source);gi.git(['commit','-m','source'],source)
    config=tmp_path/'global.gitconfig'
    monkeypatch.setenv('GIT_CONFIG_GLOBAL',str(config))
    gi.git(['config','--global','url.'+source.as_uri()+'.insteadOf','git@github.com:example/workspace.git'],workspace)
    result=gi.clone_repository({'path':'cloned','remote':'https://github.com/example/workspace',
        'name':'Analyst','email':'analyst@example.com'},workspace)
    checkout=workspace/'cloned'
    assert result['head'] and result['branch']=='main' and result['upstream']=='origin/main'
    assert (checkout/'model.sql').read_text()=='SELECT 1;'
    assert (checkout/'.gitignore').read_text().startswith('my-custom/\n')
    assert '.env' in (checkout/'.gitignore').read_text()
    assert gi.text(['config','core.sshCommand'],checkout)==gi.ssh_command()
    gi.git(['add','.gitignore'],checkout);gi.git(['commit','-m','workspace defaults'],checkout)
    with pytest.raises(ValueError,match='new or empty'):gi.clone_repository({'path':'cloned','remote':result['remote']},workspace)
    assert (checkout/'model.sql').exists()


@pytest.mark.parametrize('path',['.','..','/tmp/elsewhere','missing-parent/child'])
def test_clone_rejects_invalid_destinations_before_network(workspace,path):
    with pytest.raises(ValueError):
        gi.clone_repository({'path':path,'remote':'git@github.com:example/workspace.git'},workspace)
