"""Authenticated Jupyter endpoints used by the native Lab extension."""
import asyncio
import json
import os
import uuid
from pathlib import Path
from urllib.parse import quote
import boto3
from botocore.config import Config
import httpx
from jupyter_server.base.handlers import JupyterHandler
from jupyter_server.utils import url_path_join
from tornado import web
from config import ROOT, RUNTIME, identifier, uc, all_catalogs, timezone_name
from cluster_restarts import ClusterRestarts
from file_deletion import delete_batch, delete_target
import git_integration
from catalog_functions import create_payload
from catalog_actions import full_name

def _jupyter_server_extension_points(): return [{'module':'lakehouse_server'}]

def storage():
    return boto3.client('s3',endpoint_url=os.getenv('S3_ENDPOINT') or
        f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'],
        region_name='auto',config=Config(signature_version='s3v4',s3={'addressing_style':'path'}))

UPLOADS=RUNTIME/'uploads'

async def runner_request(method,path,payload=None):
    async with httpx.AsyncClient(timeout=7200 if path in ('sql','tables/delete') else 60) as client:
        response=await client.request(method,os.getenv('RUNNER_URL','http://runner:8765')+'/'+path,
            headers={'X-Runner-Token':os.environ['RUNNER_TOKEN']},json=payload)
        if response.is_error:
            try: message=response.json().get('detail',response.text[:3000])
            except ValueError: message=response.text[:3000]
            raise ValueError(str(message))
        return response.json()

async def registry_request(method):
    async with httpx.AsyncClient(timeout=120) as client:
        response=await client.request(method,'http://registry:8080/registry/'+('status' if method=='GET' else 'sync'),
            headers={'X-Runner-Token':os.environ['RUNNER_TOKEN']})
        if response.is_error:raise ValueError('Registry is pending; check docker compose logs registry before resetting metadata')
        return response.json()

class API(JupyterHandler):
    def finish_json(self,value,status=200):
        self.set_status(status); self.set_header('Content-Type','application/json'); self.set_header('Cache-Control','no-store')
        self.finish(json.dumps(value,default=str))

    async def runner(self,method,path,payload=None):
        return await runner_request(method,path,payload)

    @property
    def restarts(self):
        if 'lakehouse_restarts' not in self.settings:
            self.settings['lakehouse_restarts']=ClusterRestarts(self.kernel_manager,runner_request)
        return self.settings['lakehouse_restarts']

    @web.authenticated
    async def get(self,path):
        try:
            if path=='catalogs': result={'catalogs':await asyncio.to_thread(all_catalogs)}
            elif path in ('schemas','tables','volumes','functions'):
                params={'catalog_name':identifier(self.get_argument('catalog'))}
                if path!='schemas': params['schema_name']=identifier(self.get_argument('schema'))
                if self.get_argument('page_token',''): params['page_token']=self.get_argument('page_token')
                result=await asyncio.to_thread(uc,'GET',path,None,params)
            elif path=='function':
                name=full_name(self.get_argument('name'))
                result=await asyncio.to_thread(uc,'GET','functions/'+quote(name,safe=''))
            elif path=='table':
                name=self.get_argument('name'); [identifier(p) for p in name.split('.')]
                if len(name.split('.'))!=3: raise ValueError('Expected catalog.schema.table')
                result=await asyncio.to_thread(uc,'GET','tables/'+quote(name,safe=''))
                result['authorization']={'enforced':False,'mode':'Single trusted workspace',
                    'note':'UC authorization is disabled. These are metadata, not per-user data access controls.'}
            elif path=='files':
                prefix=self.get_argument('prefix','incoming/')
                if prefix.startswith('/') or '..' in prefix.split('/'): raise ValueError('Invalid prefix')
                args={'Bucket':os.environ['R2_BUCKET'],'Prefix':prefix,'Delimiter':'/','MaxKeys':200}
                if self.get_argument('page_token',''): args['ContinuationToken']=self.get_argument('page_token')
                response=await asyncio.to_thread(storage().list_objects_v2,**args)
                result={'folders':[p['Prefix'] for p in response.get('CommonPrefixes',[])],
                    'files':[{'key':p['Key'],'size':p['Size']} for p in response.get('Contents',[])],
                    'next_page_token':response.get('NextContinuationToken'),'bucket':os.environ['R2_BUCKET']}
            elif path=='download':
                key=self.get_argument('key')
                if key.startswith('/') or '..' in key.split('/'): raise ValueError('Invalid key')
                url=storage().generate_presigned_url('get_object',Params={'Bucket':os.environ['R2_BUCKET'],'Key':key},ExpiresIn=300)
                return self.redirect(url)
            elif path=='cluster':
                result=await self.runner('GET','config')
                sessions=await self.session_manager.list_sessions()
                paths={s['kernel']['id']:s['path'] for s in sessions if s.get('kernel')}
                result.update(kernels=[{'id':k['id'],'state':k['execution_state'],'path':paths.get(k['id'],k['id'])}
                                       for k in self.kernel_manager.list_kernels()],
                    cpu_visible=os.cpu_count(),mode='Spark local; notebook kernels and SQL service have separate JVMs',
                    restart=self.restarts.snapshot())
                try:
                    sql_state=await self.runner('GET','sql/status')
                    result['sql_status']='RUNNING' if sql_state['state']=='READY' else sql_state['state']
                    if sql_state.get('error'): result['sql_error']=sql_state['error']
                except Exception as e: result['sql_status']='UNAVAILABLE'; result['sql_error']=str(e)
            elif path.startswith('cluster/restarts/'):
                result=self.restarts.snapshot(path.rsplit('/',1)[1])
            elif path=='preferences':result={'timezone':timezone_name()}
            elif path=='catalog-registry':result=await registry_request('GET')
            elif path=='git/status':result=await asyncio.to_thread(git_integration.status,self.get_argument('path','.'),ROOT)
            elif path=='git/preview':result=await asyncio.to_thread(git_integration.preview,self.get_argument('path','.'),ROOT)
            elif path=='maintenance' or path.startswith(('history/','runs/','workflow-history/','docs/')):
                query=self.request.query
                result=await self.runner('GET',path+('?' + query if query else ''))
            elif path in ('jobs','flows','executions'): result=await self.runner('GET',path)
            elif path.startswith('jobs/'): result=await self.runner('GET',path)
            elif path=='upload':
                meta=self.upload_meta(self.get_argument('id'))
                def uploaded_parts():
                    parts=[]
                    for page in storage().get_paginator('list_parts').paginate(Bucket=os.environ['R2_BUCKET'],Key=meta['key'],UploadId=meta['upload_id']):
                        parts.extend(page.get('Parts',[]))
                    return parts
                result={'id':self.get_argument('id'),'key':meta['key'],'parts':await asyncio.to_thread(uploaded_parts)}
            else: raise ValueError('Unknown endpoint')
            self.finish_json(result)
        except Exception as e: self.finish_json({'error':str(e)},400)

    def upload_meta(self,id):
        if not __import__('re').fullmatch('[a-f0-9]{32}',id): raise ValueError('Invalid upload ID')
        path=UPLOADS/(id+'.json')
        if not path.is_file(): raise ValueError('Upload session not found')
        return json.loads(path.read_text())

    @web.authenticated
    async def post(self,path):
        try:
            if path=='upload/part':
                id=self.get_argument('id'); meta=self.upload_meta(id); number=int(self.get_argument('part'))
                if not 1<=number<=10000 or not 0<len(self.request.body)<=32*1024*1024: raise ValueError('Invalid part')
                result=await asyncio.to_thread(storage().upload_part,Bucket=os.environ['R2_BUCKET'],Key=meta['key'],
                    UploadId=meta['upload_id'],PartNumber=number,Body=self.request.body)
                return self.finish_json({'ETag':result['ETag'],'PartNumber':number})
            data=json.loads(self.request.body or '{}')
            if path=='catalog-registry/sync':result=await registry_request('POST')
            elif path=='functions':
                result=await asyncio.to_thread(uc,'POST','functions',create_payload(data))
            elif path=='functions/delete':
                name=full_name(data.get('name'))
                if data.get('confirmation')!=name:raise ValueError('Confirm the full function name')
                result=await asyncio.to_thread(uc,'DELETE','functions/'+quote(name,safe=''))
            elif path=='tables/delete':result=await self.runner('POST',path,data)
            elif path.startswith('git/'):
                result=await asyncio.to_thread(git_integration.action,path[4:],data,ROOT)
            elif path in ('catalogs','schemas'):
                identifier(data['name'])
                payload={'name':data['name'],'comment':data.get('comment','')}
                if path=='catalogs': payload['storage_root']=f"s3://{os.environ['R2_BUCKET']}/warehouse/{data['name']}"
                else: payload['catalog_name']=identifier(data['catalog_name'])
                result=await asyncio.to_thread(uc,'POST',path,payload)
                if path=='catalogs':
                    await asyncio.to_thread(uc,'POST','schemas',{'name':'default','catalog_name':data['name']})
            elif path=='cluster/restart': result=await self.restarts.start(data)
            elif path in ('sql','config','jobs','flows','maintenance'): result=await self.runner('POST',path,data)
            elif path.startswith('flows/') and path.endswith('/execute'): result=await self.runner('POST',path,data)
            elif path=='files/delete':
                delete_target(data)
                result=await asyncio.to_thread(delete_batch,storage(),os.environ['R2_BUCKET'],data)
            elif path=='upload/start':
                key=data['key']
                if not key.startswith('incoming/') or '..' in key.split('/') or key.endswith('/') or len(key)>1000:
                    raise ValueError('Upload destination must be a file under incoming/')
                # Never overwrite existing objects silently.
                s3=storage()
                try: await asyncio.to_thread(s3.head_object,Bucket=os.environ['R2_BUCKET'],Key=key)
                except s3.exceptions.ClientError as e:
                    if e.response['ResponseMetadata']['HTTPStatusCode']!=404: raise
                else: raise ValueError('File already exists; choose another name or folder')
                size=int(data.get('size',0))
                if not 0<size<=32*1024*1024*10000: raise ValueError('File size must be 1 byte to 312 GiB')
                result=await asyncio.to_thread(s3.create_multipart_upload,Bucket=os.environ['R2_BUCKET'],Key=key)
                id=uuid.uuid4().hex; UPLOADS.mkdir(parents=True,exist_ok=True)
                (UPLOADS/(id+'.json')).write_text(json.dumps({'key':key,'upload_id':result['UploadId'],'size':size}))
                result={'id':id,'part_size':32*1024*1024}
            elif path in ('upload/complete','upload/abort'):
                id=data['id']; meta=self.upload_meta(id); client=storage()
                args={'Bucket':os.environ['R2_BUCKET'],'Key':meta['key'],'UploadId':meta['upload_id']}
                if path.endswith('complete'):
                    parts=[]; total=0
                    for page in client.get_paginator('list_parts').paginate(**args):
                        parts += [{'ETag':p['ETag'],'PartNumber':p['PartNumber']} for p in page.get('Parts',[])]
                        total += sum(p['Size'] for p in page.get('Parts',[]))
                    if not parts: raise ValueError('Upload has no parts')
                    if total!=meta['size']: raise ValueError('Upload incomplete; resume before completing')
                    result=await asyncio.to_thread(client.complete_multipart_upload,**args,MultipartUpload={'Parts':parts})
                else: result=await asyncio.to_thread(client.abort_multipart_upload,**args)
                (UPLOADS/(id+'.json')).unlink()
            else: raise ValueError('Unknown endpoint')
            self.finish_json(result)
        except Exception as e: self.finish_json({'error':str(e)},400)

class Artifact(JupyterHandler):
    @web.authenticated
    async def get(self,run_id,asset=''):
        import mimetypes
        from run_store import artifact_path
        try:
            docs=self.request.path.startswith(url_path_join(self.settings['base_url'],'lakehouse/docs/'))
            relative='target/'+(asset or 'index.html') if docs else self.get_argument('path')
            path=artifact_path(run_id,relative)
            self.set_header('Cache-Control','no-store')
            self.set_header('X-Content-Type-Options','nosniff')
            self.set_header('Content-Type',mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
            if docs:
                if path.suffix not in ('.html','.json','.js','.css','.svg','.png','.woff','.woff2','.ico'):raise ValueError('Unsupported docs asset')
                self.set_header('Content-Security-Policy',"default-src 'self' data: blob:; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'self'")
            else:self.set_header('Content-Disposition','attachment; filename="'+path.name.replace('"','')+'"')
            with path.open('rb') as stream:
                while chunk:=stream.read(256*1024):self.write(chunk);await self.flush()
            self.finish()
        except (ValueError,FileNotFoundError):raise web.HTTPError(404)

def _load_jupyter_server_extension(server):
    base=server.web_app.settings['base_url']
    server.web_app.add_handlers('.*$',[(url_path_join(base,'lakehouse/api/(.*)'),API),
        (url_path_join(base,'lakehouse/docs/([a-f0-9]{32})/(.*)'),Artifact),
        (url_path_join(base,'lakehouse/artifacts/([a-f0-9]{32})'),Artifact)])
    server.log.info('Lakehouse V3 API registered; native UI is in JupyterLab')
