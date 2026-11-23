"""Real UC/PostgreSQL restart/replay with a file-backed fake R2 object.

No production env, Docker volumes, S3 data or GitHub are used. Requires images:
LAKEHOUSE_REGISTRY_TEST_IMAGE (runtime), LAKEHOUSE_CATALOG_TEST_IMAGE (catalog).
Run on the host: python tests/registry_integration.py
"""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid


def stage(phase):
    from botocore.exceptions import ClientError
    from catalog_registry import Registry, Upstream
    from catalog_functions import create_payload, definition
    class Store:
        path=Path('/fixture/current.json')
        def get_object(self,**args):
            if not self.path.exists():raise ClientError({'Error':{'Code':'NoSuchKey'}},'GetObject')
            body=self.path.read_bytes()
            return {'Body':io.BytesIO(body),'ETag':'"'+hashlib.sha256(body).hexdigest()+'"'}
        def put_object(self,**args):
            assert args['Key']=='_lakehouse/registry/v1/current.json'
            old=self.get_object()['ETag'] if self.path.exists() else None
            if args.get('IfNoneMatch')=='*' and old is not None or args.get('IfMatch',old)!=old:
                raise ClientError({'Error':{'Code':'PreconditionFailed'}},'PutObject')
            self.path.write_bytes(args['Body'])
            return {'ETag':self.get_object()['ETag']}
    upstream=Upstream()
    if phase=='export':
        upstream.request('POST','catalogs',{'name':'empty','comment':'Empty catalog','properties':{'department':'finance'},'storage_root':'s3://fixture/catalog-empty'})
        upstream.request('POST','catalogs',{'name':'sales','comment':'Sales','storage_root':'s3://fixture/catalog-sales'})
        upstream.request('POST','schemas',{'name':'empty_schema','catalog_name':'sales','comment':'Empty schema',
            'properties':{'tier':'planned'},'storage_root':'s3://fixture/separate-schema-root'})
        upstream.request('POST','schemas',{'name':'raw','catalog_name':'sales'})
        upstream.request('POST','volumes',{'name':'landing','catalog_name':'sales','schema_name':'raw','comment':'Landing files',
            'volume_type':'EXTERNAL','storage_location':'s3://fixture/incoming'})
        upstream.request('POST','tables',{'name':'orders','catalog_name':'sales','schema_name':'raw','comment':'External fixture',
            'table_type':'EXTERNAL','data_source_format':'DELTA','storage_location':'s3://fixture/external/orders',
            'columns':[{'name':'id','type_text':'int','type_name':'INT','type_json':'{"name":"id","type":"integer","nullable":true,"metadata":{}}','position':0,'nullable':True}]})
        function=create_payload({'name':'increment','catalog_name':'sales','schema_name':'raw','language':'PYTHON',
            'return_type':'INT','parameters':[{'name':'value','type':'INT'}],'body':'return value + 1',
            'comment':'Portable increment'})
        upstream.request('POST','functions',function)
    registry=Registry(Store(),upstream,'fixture',Path('/tmp/registry-state.json'))
    registry.initialize()
    data=upstream.scan('fixture')
    assert {c['name'] for c in data['catalogs']}=={'empty','sales'}
    c=next(c for c in data['catalogs'] if c['name']=='empty')
    assert c['comment']=='Empty catalog' and c['properties']=={'department':'finance'}
    s=next(s for s in data['schemas'] if s['name']=='empty_schema')
    assert s['comment']=='Empty schema' and s['properties']=={'tier':'planned'}
    assert s['storage_root']=='s3://fixture/separate-schema-root'
    assert data['volumes'][0]['storage_location']=='s3://fixture/incoming'
    assert data['volumes'][0]['comment']=='Landing files'
    assert data['tables'][0]['storage_location']=='s3://fixture/external/orders'
    assert data['functions'][0]['routine_definition']=='return value + 1'
    assert data['functions'][0]['input_params']['parameters'][0]['type_name']=='INT'
    assert data['functions'][0]['comment']=='Portable increment'
    assert registry.ready and not registry.status()['unrestored']
    print('PASS real UC '+phase+': empty catalog/schema, comments, properties, roots, external volume/table, Python function definition')


def main():
    root=Path(__file__).resolve().parents[1]
    tag='registry-check-'+uuid.uuid4().hex[:10]
    pg=tag+'-postgres';cat=tag+'-catalog'
    runtime=os.getenv('LAKEHOUSE_REGISTRY_TEST_IMAGE','r2-lakehouse-v3-runtime:local')
    catalog=os.getenv('LAKEHOUSE_CATALOG_TEST_IMAGE','r2-lakehouse-v3-catalog:local')
    def docker(*args):return subprocess.check_output(['docker',*args],text=True).strip()
    try:
        docker('network','create',tag)
        docker('run','-d','--name',pg,'--network',tag,'-e','POSTGRES_USER=lakehouse',
            '-e','POSTGRES_PASSWORD=fixture-only','-e','POSTGRES_DB=unitycatalog','postgres:16.6')
        for _ in range(60):
            r=subprocess.run(['docker','exec',pg,'pg_isready','-U','lakehouse'],capture_output=True)
            if r.returncode==0:break
            time.sleep(1)
        else:raise RuntimeError('Fixture PostgreSQL did not start')
        def start_catalog():
            docker('run','-d','--name',cat,'--network',tag,'--network-alias','catalog',
                '--add-host','postgres:'+docker('inspect',pg,'--format','{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'),
                '-e','POSTGRES_PASSWORD=fixture-only','-e','R2_BUCKET=fixture',
                '-e','R2_ACCESS_KEY_ID=fixture','-e','R2_SECRET_ACCESS_KEY=fixture',catalog)
            for _ in range(90):
                r=subprocess.run(['docker','exec',cat,'wget','-q','-O','-',
                    'http://127.0.0.1:8080/api/2.1/unity-catalog/catalogs'],capture_output=True)
                if r.returncode==0:return
                time.sleep(1)
            raise RuntimeError('Fixture UC did not start')
        start_catalog()
        with tempfile.TemporaryDirectory(prefix='lakehouse-registry-integration-') as folder:
            def run_stage(phase):
                print(docker('run','--rm','--network',tag,'--entrypoint','python3',
                    '-v',str(root)+':/project:ro','-v',folder+':/fixture','-e','PYTHONPATH=/project/runtime',
                    '-e','UC_UPSTREAM_URL=http://catalog:8080','-e','UC_REGISTRY_PREFIX=_lakehouse/registry/v1',
                    runtime,'/project/tests/registry_integration.py','stage',phase))
            run_stage('export')
            before=Path(folder,'current.json').read_bytes()
            docker('rm','-f',cat)
            docker('exec',pg,'psql','-U','lakehouse','-d','postgres','-c','DROP DATABASE unitycatalog WITH (FORCE)')
            docker('exec',pg,'psql','-U','lakehouse','-d','postgres','-c','CREATE DATABASE unitycatalog')
            start_catalog()
            run_stage('restore')
            assert Path(folder,'current.json').read_bytes()==before
        print('PASS UC metadata destroyed/recreated, replayed from portable registry; registry object unchanged, no live R2/data access.')
    finally:
        for container in (cat,pg):subprocess.run(['docker','rm','-fv',container],capture_output=True)
        subprocess.run(['docker','network','rm',tag],capture_output=True)


if __name__=='__main__':
    if len(sys.argv)>2 and sys.argv[1]=='stage':stage(sys.argv[2])
    else:main()
