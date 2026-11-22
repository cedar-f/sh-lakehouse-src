import hashlib,json,os,subprocess,tarfile,sys,re
from datetime import datetime,timezone
from pathlib import Path
import boto3
from botocore.config import Config

client=boto3.client('s3',endpoint_url=os.getenv('S3_ENDPOINT') or f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
    aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'],
    region_name='auto',config=Config(signature_version='s3v4'))
stamp=sys.argv[2] if len(sys.argv)>2 else datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
if not re.fullmatch('[0-9]{8}T[0-9]{6}Z',stamp): raise SystemExit('Invalid backup timestamp')
root=Path('/backups')/stamp; root.mkdir(parents=True,exist_ok=True)
prefix=os.getenv('BACKUP_PREFIX','platform-backups/v3').strip('/')+'/'+stamp
if len(sys.argv)>1 and sys.argv[1]=='restore':
    if '--replace-metadata' not in sys.argv: raise SystemExit('Restore requires --replace-metadata')
    client.download_file(os.environ['R2_BUCKET'],prefix+'/manifest.json',str(root/'manifest.json'))
    manifest=json.loads((root/'manifest.json').read_text())
    allowed={'unitycatalog.dump','kestra.dump','workspace.tar.gz','kestra-storage.tar.gz'}
    if manifest.get('version')!=3 or manifest.get('bucket')!=os.environ['R2_BUCKET']:
        raise SystemExit('Backup version or R2 bucket does not match this workspace')
    if not allowed.issubset(manifest['files']) or not set(manifest['files']).issubset(allowed|{'runtime.tar.gz'}): raise SystemExit('Invalid backup manifest')
    for name,digest in manifest['files'].items():
        target=root/name; client.download_file(os.environ['R2_BUCKET'],prefix+'/'+name,str(target))
        h=hashlib.sha256()
        with target.open('rb') as f:
            for chunk in iter(lambda:f.read(8*1024*1024),b''): h.update(chunk)
        if h.hexdigest()!=digest: raise SystemExit('Checksum failed: '+name)
    for name,dest in [('workspace.tar.gz','/workspace'),('kestra-storage.tar.gz','/kestra-storage'),('runtime.tar.gz','/var/lib/lakehouse')]:
        if name not in manifest['files']:continue
        with tarfile.open(root/name,'r:gz') as tar:
            for member in tar.getmembers():
                # Backups can contain notebooks and Git files, never escape the destination.
                if member.issym() or member.islnk(): continue
                if not member.name.startswith('data/'): continue
                member.name=member.name[5:]
                resolved=(Path(dest)/member.name).resolve()
                if not resolved.is_relative_to(Path(dest).resolve()): raise SystemExit('Unsafe archive path')
                tar.extract(member,dest)
    print('Backup downloaded and workspace restored; host script will now restore both PostgreSQL databases: '+stamp)
    raise SystemExit(0)
for database in ('unitycatalog','kestra'):
    if not (root/(database+'.dump')).is_file(): raise SystemExit('Host script must create PostgreSQL dumps first')
for source,name in [('/workspace','workspace.tar.gz'),('/kestra-storage','kestra-storage.tar.gz'),('/var/lib/lakehouse','runtime.tar.gz')]:
    with tarfile.open(root/name,'w:gz') as tar: tar.add(source,arcname='data')
manifest={'created':stamp,'version':3,'bucket':os.environ['R2_BUCKET'],'files':{}}
backup_files=[root/name for name in ('unitycatalog.dump','kestra.dump','workspace.tar.gz','kestra-storage.tar.gz','runtime.tar.gz')]
for path in backup_files:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(8*1024*1024),b''): h.update(chunk)
    manifest['files'][path.name]=h.hexdigest()
(root/'manifest.json').write_text(json.dumps(manifest,indent=2))
for path in [*backup_files,root/'manifest.json']: client.upload_file(str(path),os.environ['R2_BUCKET'],prefix+'/'+path.name)
print('Backup uploaded to s3://'+os.environ['R2_BUCKET']+'/'+prefix)
print('Also retain .env and git SSH keys separately, encrypted. They are intentionally absent from this backup.')
