"""Idempotent R2 layout and opt-out starter project provisioning."""
import json
import os
from pathlib import Path
import shutil
import tempfile

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


def storage():
    return boto3.client('s3',
        endpoint_url=os.getenv('S3_ENDPOINT') or f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
        aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'],
        region_name='auto', config=Config(signature_version='s3v4', s3={'addressing_style': 'path'}))


def layout_prefixes():
    backup = os.getenv('BACKUP_PREFIX', 'platform-backups/v3').strip().rstrip('/')
    if (not backup or backup.startswith('/') or '\\' in backup
            or any(p in ('', '.', '..') for p in backup.split('/'))
            or backup.split('/')[0] in ('incoming', 'warehouse')
            or any(ord(c) < 32 for c in backup)):
        raise ValueError('BACKUP_PREFIX must be a separate relative prefix, e.g. platform-backups/v3')
    return ('warehouse/', 'incoming/', backup + '/')


def ensure_layout(client, bucket):
    results = {}
    for prefix in layout_prefixes():
        # Existing content defines the folder even without a directory marker.
        if client.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=1).get('Contents'):
            results[prefix] = 'reused'
            continue
        try:
            client.put_object(Bucket=bucket, Key=prefix, Body=b'', IfNoneMatch='*')
            results[prefix] = 'created'
        except ClientError as error:
            if error.response.get('ResponseMetadata', {}).get('HTTPStatusCode') != 412:
                raise
            results[prefix] = 'reused'
    return results


def sample_enabled():
    value = os.getenv('SEED_SAMPLE_DBT', 'true').strip().lower()
    if value not in ('true', 'false'):
        raise ValueError('SEED_SAMPLE_DBT must be true or false')
    return value == 'true'


def sample_flow(catalog, timezone):
    nodes = []
    for index, command in enumerate(('seed', 'build', 'docs')):
        nodes.append({'id': command, 'kind': 'dbt', 'path': 'dbt_sample',
            'command': command,
            'dependsOn': [] if index == 0 else [nodes[-1]['id']],
            'parameters': {}, 'timeout': 7200, 'attempts': 1,
            'x': 30 + 240 * index, 'y': 50})
    return {'id': 'dbt_sample_pipeline', 'description': 'Sample: seed orders, build/test totals, generate dbt Docs',
        'cron': '', 'scheduleEnabled': False, 'timezone': timezone, 'nodes': nodes}


def seed_sample(root, catalog, timezone):
    """Never replace an existing project or flow, including user customizations."""
    import yaml
    from workflows import compile_flow
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    project = root / 'dbt_sample'
    created = False
    if not project.exists() and not project.is_symlink():
        temporary = Path(tempfile.mkdtemp(prefix='.dbt-sample-', dir=root))
        try:
            shutil.copytree(Path(__file__).parent / 'templates/dbt_sample', temporary, dirs_exist_ok=True)
            config = temporary / 'dbt_project.yml'
            data = yaml.safe_load(config.read_text())
            data['vars']['lakehouse_catalog'] = catalog
            config.write_text(yaml.safe_dump(data, sort_keys=False), encoding='utf-8')
            try:
                temporary.rename(project)
                created = True
            except FileExistsError:
                pass
        finally:
            if temporary.exists():
                if not temporary.resolve().is_relative_to(root.resolve()):
                    raise ValueError('Temporary project escaped workspace')
                shutil.rmtree(temporary)
    flows = root / 'workflows'
    if not flows.resolve().is_relative_to(root.resolve()):
        raise ValueError('Workflows must stay inside the workspace')
    flows.mkdir(exist_ok=True)
    flow = sample_flow(catalog, timezone)
    path = flows / (flow['id'] + '.json')
    flow_created = False
    if path.exists() or path.with_suffix('.yml').exists():
        return {'project': 'created' if created else 'reused', 'flow': 'reused'}
    compiled = yaml.safe_dump(compile_flow(flow), sort_keys=False)
    try:
        with path.open('x', encoding='utf-8') as stream:
            json.dump(flow, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        flow_created = True
    except FileExistsError:
        pass
    if flow_created:
        with path.with_suffix('.yml').open('x', encoding='utf-8') as stream:
            stream.write(compiled)
    return {'project': 'created' if created else 'reused', 'flow': 'created' if flow_created else 'reused'}
