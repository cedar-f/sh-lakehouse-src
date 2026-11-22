"""Workspace Git onboarding and a per-user agent shared with jupyterlab-git."""
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import tempfile
import threading

LOCK = threading.RLock()
PREVIEW_SECRET = os.urandom(32)
MAX_FILES = 2000
MAX_BYTES = 100 * 1024 * 1024
ASKPASS = Path(__file__).with_name('git_askpass.py')
# GitHub's published Ed25519 host key. Verify the fingerprint before changing it.
# https://api.github.com/meta and GitHub Docs /githubs-ssh-key-fingerprints
GITHUB_KEY = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl'
GITHUB_FINGERPRINT = 'SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU'
IGNORE = '''# BEGIN Lakehouse workspace defaults
.env
.env.*
!.env.example
.ssh/
.secrets/
profiles.yml
profiles.yaml
*.pem
*.key
*.dump
*.sqlite
*.sqlite-*
*.vhdx
*.tar.gz
backups/
.lakehouse/
.ipynb_checkpoints/
**/.ipynb_checkpoints/
__pycache__/
runs/
spark-warehouse/
metastore_db/
derby.log
*.pid
**/target/
**/logs/
**/dbt_packages/
# END Lakehouse workspace defaults
'''


def run(args, cwd=None, env=None, timeout=30, check=True):
    result = subprocess.run(args, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                            capture_output=True, timeout=timeout, start_new_session=True)
    if check and result.returncode:
        # SSH/Git diagnostics contain paths and public URLs, never request secrets.
        message = (result.stderr or result.stdout).decode('utf-8', 'replace')[-3000:]
        raise ValueError(message.strip() or 'Git command failed')
    return result


def ssh_home():
    directory = Path.home() / '.ssh'
    if directory.is_symlink():
        raise ValueError('The SSH directory must not be a symlink')
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory.chmod(0o700)
    return directory


def agent_env(passphrase=''):
    if not isinstance(passphrase, str) or '\n' in passphrase or '\r' in passphrase or len(passphrase) > 4096:
        raise ValueError('Invalid SSH passphrase')
    return {**os.environ, 'SSH_AUTH_SOCK': str(ssh_home() / 'lakehouse-agent.sock'),
            'SSH_ASKPASS': str(ASKPASS),
            'SSH_ASKPASS_REQUIRE': 'force', 'DISPLAY': 'lakehouse:0',
            'LAKEHOUSE_SSH_PASSPHRASE': passphrase}


def ensure_agent():
    with LOCK:
        env = agent_env()
        path = Path(env['SSH_AUTH_SOCK'])
        probe = run(['ssh-add', '-l'], env=env, check=False)
        if probe.returncode in (0, 1):
            return env
        if path.exists() or path.is_symlink():
            info = path.lstat()
            if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
                raise ValueError('Unexpected SSH agent socket; inspect it before restarting')
            path.unlink()
        run(['ssh-agent', '-a', str(path), '-s'], env=env)
        # Passwordless keys are ready after restart; encrypted keys stay locked.
        key = ssh_home() / 'id_ed25519'
        if key.is_file() and not key.is_symlink():
            run(['ssh-add', str(key)], env=env, check=False)
        return env


def key_status():
    directory = ssh_home()
    key, public = directory / 'id_ed25519', directory / 'id_ed25519.pub'
    for path in (key, public):
        if path.is_symlink():
            raise ValueError('SSH key files must not be symlinks')
    public_key = public.read_text().strip() if public.is_file() and public.stat().st_size < 16384 else ''
    fingerprint = ''
    if public_key:
        result = run(['ssh-keygen', '-lf', str(public)], check=False)
        if result.returncode == 0:
            fingerprint = result.stdout.decode().split()[1]
        else:
            public_key = ''
    probe = run(['ssh-add', '-l'], env=agent_env(), check=False)
    loaded = bool(fingerprint and fingerprint in probe.stdout.decode('utf-8', 'replace'))
    return {'key_exists': key.is_file(), 'public_key': public_key, 'fingerprint': fingerprint,
            'agent_running': probe.returncode in (0, 1), 'key_loaded': loaded,
            'key_path': str(key), 'scope': 'Current Jupyter Linux user'}


def create_key(payload):
    with LOCK:
        directory = ssh_home()
        key = directory / 'id_ed25519'
        if key.exists() or key.is_symlink() or key.with_suffix('.pub').exists():
            raise ValueError('An SSH key already exists. Reuse/unlock it; no key was overwritten.')
        phrase = payload.get('passphrase', '')
        env = agent_env(phrase)
        with tempfile.TemporaryDirectory(prefix='lakehouse-key-', dir=directory) as folder:
            temporary = Path(folder) / 'key'
            command = ['ssh-keygen', '-q', '-t', 'ed25519', '-C', 'lakehouse-github', '-f', str(temporary)]
            if not phrase:
                command += ['-N', '']
            result = run(command, env=env, check=False)
            if result.returncode:
                raise ValueError('SSH key creation failed. No existing key was changed.')
            # Exclusive creation also protects against another process creating a key.
            with key.open('xb') as stream:
                key.chmod(0o600)
                stream.write(temporary.read_bytes())
            with (directory / 'id_ed25519.pub').open('x') as stream:
                stream.write(temporary.with_suffix('.pub').read_text())
        unlock({'passphrase': phrase})
        return key_status()


def unlock(payload):
    with LOCK:
        ensure_agent()
        key = ssh_home() / 'id_ed25519'
        if not key.is_file() or key.is_symlink():
            raise ValueError('Create an SSH key first')
        key.chmod(0o600)
        result = run(['ssh-add', str(key)], env=agent_env(payload.get('passphrase', '')), check=False)
        if result.returncode:
            raise ValueError('Could not unlock the SSH key. Check its passphrase.')
        return key_status()


def github_remote(value):
    if not isinstance(value, str):
        raise ValueError('Enter a GitHub repository URL')
    match = re.fullmatch(r'(?:git@github\.com:|https://github\.com/)([A-Za-z0-9][A-Za-z0-9-]*)/([A-Za-z0-9_.-]+?)(?:\.git)?/?', value.strip())
    if not match or match[2] in ('.', '..'):
        raise ValueError('Use git@github.com:OWNER/REPO.git or https://github.com/OWNER/REPO')
    return f'git@github.com:{match[1]}/{match[2]}.git'


def ssh_command():
    directory = ssh_home()
    known = directory / 'lakehouse_known_hosts'
    if known.is_symlink():
        raise ValueError('The managed known-hosts file must not be a symlink')
    expected = 'SHA256:' + base64.b64encode(hashlib.sha256(base64.b64decode(GITHUB_KEY.split()[1])).digest()).decode().rstrip('=')
    if expected != GITHUB_FINGERPRINT:
        raise RuntimeError('GitHub host key fingerprint mismatch in application configuration')
    known.write_text('github.com ' + GITHUB_KEY + '\n')
    known.chmod(0o600)
    return shlex.join(['ssh', '-i', str(directory / 'id_ed25519'), '-o', 'IdentitiesOnly=yes',
                       '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15',
                       '-o', 'StrictHostKeyChecking=yes', '-o', 'HostKeyAlgorithms=ssh-ed25519',
                       '-o', 'UserKnownHostsFile=' + str(known)])


def git(args, cwd, check=True, network=False):
    env = {**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'GIT_LITERAL_PATHSPECS': '1',
           'SSH_AUTH_SOCK': str(ssh_home() / 'lakehouse-agent.sock')}
    if network:
        env['GIT_SSH_COMMAND'] = ssh_command()
    return run(['git', *args], cwd, env, timeout=90 if network else 30, check=check)


def workspace_path(value, root):
    if not isinstance(value, str) or '\x00' in value or '\\' in value or Path(value).is_absolute():
        raise ValueError('Choose a relative directory inside the workspace; use . for its root')
    root = Path(root).resolve()
    path = (root / value).resolve()
    if not path.is_relative_to(root) or not path.is_dir():
        raise ValueError('Choose an existing directory inside the workspace')
    # The wizard handles ordinary repositories only, never worktrees/submodules.
    marker = path / '.git'
    if marker.exists() and (marker.is_symlink() or not marker.is_dir()):
        raise ValueError('Linked worktrees and submodules must be managed with the native Git panel')
    result = git(['rev-parse', '--show-toplevel'], path, check=False)
    if result.returncode == 0 and Path(result.stdout.decode().strip()).resolve() != path:
        raise ValueError('This directory is inside another repository. Select the repository root.')
    if result.returncode and marker.exists():
        raise ValueError('Git could not open this repository; inspect its ownership/configuration')
    return path


def text(args, path, default=''):
    result = git(args, path, check=False)
    return result.stdout.decode('utf-8', 'replace').strip() if result.returncode == 0 else default


def status(value, root):
    path = workspace_path(value, root)
    result = {'path': str(path.relative_to(Path(root).resolve())) or '.', 'ssh': key_status(),
              'initialized': (path / '.git').is_dir()}
    if result['initialized']:
        result.update(branch=text(['symbolic-ref', '--short', 'HEAD'], path),
                      head=text(['rev-parse', '--verify', 'HEAD'], path),
                      remote=text(['config', '--local', '--get', 'remote.origin.url'], path),
                      name=text(['config', 'user.name'], path), email=text(['config', 'user.email'], path),
                      upstream=text(['rev-parse', '--abbrev-ref', '@{upstream}'], path))
    return result


def configure(payload, root):
    with LOCK:
        path = workspace_path(payload.get('path', '.'), root)
        remote = github_remote(payload.get('remote', ''))
        branch = payload.get('branch', 'main')
        if not isinstance(branch, str) or branch.startswith('-') or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_./-]{0,100}', branch):
            raise ValueError('Invalid branch name')
        if git(['check-ref-format', '--branch', branch], path, check=False).returncode:
            raise ValueError('Invalid branch name')
        name, email = payload.get('name', '').strip(), payload.get('email', '').strip()
        if not name or len(name) > 200 or re.search(r'[\x00-\x1f<>]', name):
            raise ValueError('Enter your Git author name')
        if not re.fullmatch(r'[^\s<>@]+@[^\s<>@]+', email) or len(email) > 254:
            raise ValueError('Enter your Git author email')
        ignore = path / '.gitignore'
        if ignore.is_symlink():
            raise ValueError('.gitignore must not be a symlink')
        existing = text(['config', '--local', '--get', 'remote.origin.url'], path)
        if existing and github_remote(existing) != remote:
            raise ValueError('origin points to another repository. It was not changed.')
        if not (path / '.git').exists():
            git(['init', '--initial-branch=' + branch], path)
        actual = text(['symbolic-ref', '--short', 'HEAD'], path)
        if not actual or actual != branch:
            raise ValueError('Choose the existing branch ' + (actual or '(detached HEAD)') + '; no branch was renamed')
        git(['remote', 'set-url' if existing else 'add', 'origin', remote], path)
        for key, value in [('user.name', name), ('user.email', email), ('core.sshCommand', ssh_command())]:
            git(['config', '--local', key, value], path)
        ensure_ignore(path)
        return status(payload.get('path', '.'), root)


def ensure_ignore(path):
    ignore = path / '.gitignore'
    if ignore.is_symlink():
        raise ValueError('.gitignore must not be a symlink')
    content = ignore.read_text(encoding='utf-8') if ignore.exists() else ''
    begin, end = '# BEGIN Lakehouse workspace defaults', '# END Lakehouse workspace defaults'
    if begin in content:
        if content.count(begin) != 1 or content.count(end) != 1 or content.index(end) < content.index(begin):
            raise ValueError('Repair the incomplete managed .gitignore block before connecting')
        updated = re.sub(re.escape(begin) + r'.*?' + re.escape(end), IGNORE.rstrip('\n'), content, flags=re.S)
    else:
        updated = content + ('\n' if content and not content.endswith('\n') else '') + IGNORE
    if updated != content:
        ignore.write_text(updated, encoding='utf-8', newline='\n')


def clone_repository(payload, root):
    """Clone to a new/empty workspace directory; never overlay existing files."""
    with LOCK:
        root = Path(root).resolve()
        value = payload.get('path', '')
        remote = github_remote(payload.get('remote', ''))
        if not isinstance(value, str) or not value or '\x00' in value or '\\' in value or Path(value).is_absolute():
            raise ValueError('Choose a relative clone destination inside the workspace')
        destination = (root / value).resolve()
        if destination == root:
            raise ValueError('Clone into a separate subfolder, not the workspace root')
        if not destination.is_relative_to(root) or not destination.parent.is_dir():
            raise ValueError('The destination parent must exist inside the workspace')
        if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
            raise ValueError('Clone requires a new or empty directory; existing workspace files were kept')
        parent = destination if destination.exists() else destination.parent
        if git(['rev-parse', '--show-toplevel'], parent, check=False).returncode == 0:
            raise ValueError('Do not clone inside another repository; select a separate workspace directory')
        ensure_agent()
        with tempfile.TemporaryDirectory(prefix='.lakehouse-clone-', dir=root) as temporary:
            checkout = Path(temporary) / 'checkout'
            git(['clone', '--', remote, str(checkout)], root, network=True)
            branch = text(['symbolic-ref', '--short', 'HEAD'], checkout)
            if not branch:
                raise ValueError('Remote has no default branch; initialize the empty GitHub repository instead')
            settings = {**payload, 'path': str(checkout.relative_to(root)), 'branch': branch}
            configure(settings, root)
            if destination.exists():
                destination.rmdir()  # Refuses files added by another client during clone.
            checkout.rename(destination)
        return status(str(destination.relative_to(root)), root)


def check_remote(payload):
    ensure_agent()
    remote = github_remote(payload.get('remote', ''))
    result = git(['ls-remote', '--heads', '--tags', remote], Path.home(), network=True)
    return {'remote': remote, 'readable': True, 'empty': not bool(result.stdout.strip()),
            'note': 'Read access verified. Write access is verified by push.'}


def blocked_file(path, relative):
    parts = Path(relative).parts
    if any(p in ('.ssh', '.secrets', '.lakehouse') for p in parts):
        return 'Private/runtime directory'
    if any((p == '.env' or p.startswith('.env.')) and p != '.env.example' for p in parts):
        return 'Private environment file'
    if path.name in ('profiles.yml', 'id_ed25519', 'id_rsa') or path.suffix.lower() in ('.pem', '.key', '.dump', '.sqlite', '.vhdx'):
        return 'Credential/database file'
    if path.is_symlink() or not path.is_file():
        return 'Symlink, nested repository or non-regular file'
    if path.stat().st_size > 20 * 1024 * 1024:
        return 'File exceeds the initial-commit limit of 20 MiB'
    return ''


def preview(value, root):
    path = workspace_path(value, root)
    if not (path / '.git').is_dir():
        raise ValueError('Initialize/connect the repository first')
    if text(['rev-parse', '--verify', 'HEAD'], path):
        raise ValueError('This repository already has commits. Use the native Git panel.')
    raw = git(['ls-files', '--cached', '--others', '--exclude-standard', '-z'], path).stdout
    names = sorted(set(raw.decode('utf-8', 'strict').strip('\x00').split('\x00')) - {''})
    if len(names) > MAX_FILES:
        raise ValueError('Initial commit supports up to 2000 files; narrow the directory or update .gitignore')
    files, total = [], 0
    for name in names:
        candidate = path / name
        if candidate.is_symlink() or not candidate.resolve().is_relative_to(path):
            reason = 'Symlink or path outside repository'
        else:
            reason = blocked_file(candidate, name)
        digest, size = '', 0
        if not reason:
            size = candidate.stat().st_size
            total += size
            if total > MAX_BYTES:
                raise ValueError('Initial commit preview exceeds 100 MiB; update .gitignore or use Git LFS')
            body = candidate.read_bytes()
            digest = hashlib.sha256(body).hexdigest()
            if re.search(rb'-----BEGIN (?:OPENSSH |RSA |EC |ENCRYPTED )?PRIVATE KEY-----', body):
                reason = 'Private key content detected'
        files.append({'path': name, 'size': size, 'blocked': reason, 'digest': digest})
    index = path / '.git/index'
    basis = {'path': str(path), 'files': files, 'index': hashlib.sha256(index.read_bytes()).hexdigest() if index.exists() else ''}
    token = hmac.new(PREVIEW_SECRET, json.dumps(basis, sort_keys=True).encode(), hashlib.sha256).hexdigest()
    return {'files': [{k: v for k, v in f.items() if k != 'digest'} for f in files], 'token': token,
            'total_bytes': total, 'note': 'Review files and notebook outputs. Secret detection is not exhaustive.'}


def initial_commit(payload, root):
    with LOCK:
        value = payload.get('path', '.')
        path = workspace_path(value, root)
        current = preview(value, root)
        if not hmac.compare_digest(str(payload.get('token', '')), current['token']):
            raise ValueError('Files or Git staging changed. Refresh the preview before committing.')
        selected = payload.get('files', [])
        allowed = {f['path'] for f in current['files'] if not f['blocked']}
        if not isinstance(selected, list) or not selected or any(not isinstance(p, str) or p not in allowed for p in selected):
            raise ValueError('Select reviewed, non-blocked files for the initial commit')
        selected = sorted(set(selected))
        message = payload.get('message', '').strip()
        if not message or len(message) > 2000 or '\x00' in message:
            raise ValueError('Enter a commit message (up to 2000 characters)')
        staged = set(git(['diff', '--cached', '--name-only', '-z'], path).stdout.decode().strip('\x00').split('\x00')) - {''}
        if staged - set(selected):
            raise ValueError('Other files are already staged. Review them in the native Git panel first.')
        git(['add', '--', *selected], path)
        staged_after = set(git(['diff', '--cached', '--name-only', '-z'], path).stdout.decode().strip('\x00').split('\x00')) - {''}
        if staged_after != set(selected):
            raise ValueError('The Git index changed. Review staging in the native Git panel.')
        git(['commit', '-m', message], path)
        return {'head': text(['rev-parse', 'HEAD'], path), 'committed': len(selected), 'pushed': False}


def initial_push(payload, root):
    with LOCK:
        value = payload.get('path', '.')
        path = workspace_path(value, root)
        info = status(value, root)
        remote = github_remote(info.get('remote', ''))
        if payload.get('confirmation') != remote:
            raise ValueError('Confirm the exact repository URL before the first push')
        if not info.get('head') or not info.get('branch'):
            raise ValueError('Create a commit on a branch before pushing')
        ensure_agent()
        refs = git(['ls-remote', '--heads', '--tags', remote], path, network=True).stdout.decode().splitlines()
        expected = info['head'] + '\trefs/heads/' + info['branch']
        if refs and refs != [expected]:
            raise ValueError('GitHub repository is not empty. Use the native Git panel to fetch/reconcile; no force push was attempted.')
        git(['push', '--porcelain', '--set-upstream', 'origin', info['branch']], path, network=True)
        return {'pushed': True, 'head': info['head'], 'branch': info['branch'], 'remote': remote}


def action(name, payload, root):
    if not isinstance(payload, dict):
        raise ValueError('Expected a JSON object')
    handlers = {'key': create_key, 'unlock': unlock, 'test': check_remote,
                'clone': lambda p: clone_repository(p, root),
                'init': lambda p: configure(p, root), 'commit': lambda p: initial_commit(p, root),
                'push': lambda p: initial_push(p, root)}
    if name not in handlers:
        raise ValueError('Unknown Git setup action')
    with LOCK:
        return handlers[name](payload)


if __name__ == '__main__':
    import sys
    if sys.argv[1:] != ['agent-start']:
        raise SystemExit('Usage: git_integration.py agent-start')
    ensure_agent()
