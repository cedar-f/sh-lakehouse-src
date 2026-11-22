"""Offline archive round trip; S3 uploads/downloads are a local in-memory fake."""
import hashlib,json,sys
from pathlib import Path
import boto3,pytest

@pytest.mark.parametrize('legacy',[False,True])
def test_backup_round_trip_accepts_old_and_new_runtime_archive(tmp_path,monkeypatch,legacy):
    mounts={name:tmp_path/name for name in ('workspace','kestra-storage','runtime','backups')}
    for path in mounts.values():path.mkdir()
    (mounts['workspace']/'notebook.ipynb').write_text('user notebook')
    (mounts['kestra-storage']/'execution').write_text('kestra output')
    (mounts['runtime']/'run.json').write_text('run metadata and logs')
    stamp='20261121T120000Z';backup=mounts['backups']/stamp;backup.mkdir()
    for db in ('unitycatalog','kestra'):(backup/(db+'.dump')).write_bytes(b'database dump fixture')
    uploaded={}
    class FakeS3:
        def upload_file(self,path,bucket,key):uploaded[key]=Path(path).read_bytes()
        def download_file(self,bucket,key,path):Path(path).write_bytes(uploaded[key])
    monkeypatch.setattr(boto3,'client',lambda *a,**k:FakeS3())
    monkeypatch.setenv('R2_ACCOUNT_ID','fixture');monkeypatch.setenv('R2_ACCESS_KEY_ID','fixture');monkeypatch.setenv('R2_SECRET_ACCESS_KEY','fixture');monkeypatch.setenv('R2_BUCKET','fixture')
    monkeypatch.setenv('BACKUP_PREFIX','fixture')
    text=(Path(__file__).parents[1]/'backup_storage.py').read_text()
    for source,target in [('/workspace','workspace'),('/kestra-storage','kestra-storage'),('/var/lib/lakehouse','runtime'),('/backups','backups')]:
        text=text.replace(repr(source),repr(str(mounts[target])))
    monkeypatch.setattr(sys,'argv',['backup_storage.py','create',stamp]);exec(compile(text,'backup_storage.py','exec'),{})
    manifest_key='fixture/'+stamp+'/manifest.json';manifest=json.loads(uploaded[manifest_key])
    assert 'runtime.tar.gz' in manifest['files']
    if legacy:
        del manifest['files']['runtime.tar.gz'];uploaded[manifest_key]=json.dumps(manifest).encode()
    for folder,name in [('workspace','notebook.ipynb'),('kestra-storage','execution'),('runtime','run.json')]:
        (mounts[folder]/name).unlink()
    monkeypatch.setattr(sys,'argv',['backup_storage.py','restore',stamp,'--replace-metadata'])
    with pytest.raises(SystemExit) as result:exec(compile(text,'backup_storage.py','exec'),{})
    assert result.value.code==0
    assert (mounts['workspace']/'notebook.ipynb').read_text()=='user notebook'
    assert (mounts['kestra-storage']/'execution').read_text()=='kestra output'
    assert (mounts['runtime']/'run.json').exists() is not legacy
