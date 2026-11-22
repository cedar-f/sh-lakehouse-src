"""Build with Linux root-only source modes, then verify non-root runtime access.

Run from the repository: python3 tests/image_permissions.py
Requires Docker; does not connect to R2, start the stack or touch data volumes.
"""
import io
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def context(folder):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w') as archive:
        for path in sorted(folder.rglob('*')):
            relative = path.relative_to(folder).as_posix()
            if ('__pycache__' in path.parts or 'node_modules' in path.parts
                    or relative == 'labextension/labextension'
                    or relative.startswith('labextension/labextension/')):
                continue
            if path.is_symlink():
                raise ValueError('Unexpected source symlink: ' + relative)
            item = tarfile.TarInfo(relative)
            item.uid = item.gid = 0
            # Keep dependency inputs cacheable, but reproduce restrictive Python,
            # template and startup script modes from a root checkout under 077.
            restricted = (relative.endswith('.py') or relative == 'start.sh'
                          or relative.startswith(('templates', 'tests')))
            item.mode = (0o700 if restricted else 0o755) if path.is_dir() else (0o600 if restricted else 0o755)
            if path.is_dir():
                item.type = tarfile.DIRTYPE
                archive.addfile(item)
            else:
                body = path.read_bytes()
                item.size = len(body)
                archive.addfile(item, io.BytesIO(body))
    return stream.getvalue()


def build(folder, image):
    subprocess.run(['docker', 'build', '--progress=plain', '-t', image, '-'],
                   input=context(folder), check=True)


def main():
    runtime = 'r2-lakehouse-permissions-runtime:test'
    catalog = 'r2-lakehouse-permissions-catalog:test'
    build(ROOT/'runtime', runtime)
    check = '''
import os
from pathlib import Path
assert os.getuid() == 1000, 'Test must use the configured analyst user'
import platform_bootstrap, file_deletion, lakehouse_server
for root in (Path('/opt/lakehouse'), Path('/usr/local/share/jupyter/labextensions/@lakehouse/workspace')):
    for path in [root, *root.rglob('*')]:
        assert os.access(path, os.R_OK), str(path)
        if path.is_dir(): assert os.access(path, os.X_OK), str(path)
        elif path.is_file():
            with path.open('rb') as stream: stream.read(1)
assert not os.access('/opt/lakehouse/platform_bootstrap.py', os.W_OK)
result = platform_bootstrap.seed_sample(Path('/tmp/permission-starter'), 'demo', 'Etc/UTC')
assert result == {'project': 'created', 'flow': 'created'}, result
print('PASS root-only source modes: analyst imports backend, reads UI/templates and seeds starter; code remains read-only.')
'''
    subprocess.run(['docker', 'run', '--rm', runtime, 'python3', '-c', check], check=True)
    build(ROOT/'catalog', catalog)
    subprocess.run(['docker', 'run', '--rm', '--entrypoint', '/bin/bash', catalog,
                    '-c', 'test -r /opt/start-r2.sh && test -x /opt/start-r2.sh && test "$(id -u)" != 0'], check=True)
    print('PASS catalog startup script is readable/executable by its non-root user.')


if __name__ == '__main__':
    main()
