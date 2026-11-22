"""Explicit local metadata reset. Never deletes workspace files or R2 objects."""
import argparse
import json
from pathlib import Path
import subprocess

KEYS = ('postgres_data', 'lakehouse_data', 'kestra_storage', 'kestra_tmp')


def command(args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def reset():
    config = json.loads(command(['docker', 'compose', 'config', '--format', 'json']))
    project = config['name']
    existing = set(command(['docker', 'volume', 'ls', '-q']).splitlines())
    volumes = []
    for key in KEYS:
        definition = config['volumes'][key]
        name = definition['name']
        if definition.get('external'):
            raise ValueError('Refusing to reset an external volume: ' + key)
        if name not in existing:
            continue
        info = json.loads(command(['docker', 'volume', 'inspect', name]))[0]
        labels = info.get('Labels') or {}
        if labels.get('com.docker.compose.project') != project or labels.get('com.docker.compose.volume') != key:
            raise ValueError('Refusing a volume not owned by this Compose project: ' + key)
        volumes.append(name)
    print('Resetting local UC/Kestra metadata, run history and artifacts for project ' + project, flush=True)
    print('Preserving .env, workspace, SSH keys, dependency caches and all R2 objects.', flush=True)
    command(['docker', 'compose', 'down'])
    if volumes:
        # Docker refuses to remove a volume still in use; never force it.
        command(['docker', 'volume', 'rm', *volumes])
    print('Local metadata reset completed. Start again to initialize the catalog and R2 layout.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--confirm-reset-metadata', action='store_true', required=True)
    parser.parse_args()
    project_root = Path(__file__).resolve().parent.parent
    import os
    os.chdir(project_root)
    reset()
