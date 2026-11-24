"""Bounded R2 metadata reads; virtual prefixes have no invented object metadata."""
from datetime import datetime, timezone

from botocore.exceptions import ClientError


def valid_key(key, folder=False):
    if not isinstance(key,str) or key.startswith('/') or '\\' in key or '..' in key.split('/') or any(ord(c)<32 for c in key):
        raise ValueError('Invalid object key')
    if not folder and not key:raise ValueError('A file key is required')
    return key


def iso(value):
    return value.astimezone(timezone.utc).isoformat() if isinstance(value,datetime) else value


def identity(bucket,key,kind):
    return {'bucket':bucket,'key':key,'kind':kind,'object_id':bucket+'/'+key,
            'object_id_kind':'bucket/key address (not a provider UUID)',
            'spark_path':'s3a://'+bucket+'/'+key,'s3_path':'s3://'+bucket+'/'+key,
            'created_at':None,'created_at_source':'R2 S3 does not report original creation time'}


def list_files(client,bucket,prefix,token=''):
    valid_key(prefix,True)
    args={'Bucket':bucket,'Prefix':prefix,'Delimiter':'/','MaxKeys':200}
    if token:args['ContinuationToken']=token
    result=client.list_objects_v2(**args)
    files=[]
    for value in result.get('Contents',[]):
        files.append({**identity(bucket,value['Key'],'file'),'size':value['Size'],
                      'updated_at':iso(value.get('LastModified')),'etag':value.get('ETag','').strip('"'),
                      'storage_class':value.get('StorageClass')})
    return {'bucket':bucket,'folders':[v['Prefix'] for v in result.get('CommonPrefixes',[])],
            'files':files,'next_page_token':result.get('NextContinuationToken')}


def object_detail(client,bucket,key,kind):
    if kind not in ('file','folder'):raise ValueError('Choose file or folder')
    valid_key(key,kind=='folder')
    if kind=='folder' and key and not key.endswith('/'):raise ValueError('Folder prefix must end with /')
    value=identity(bucket,key,kind)
    if not key:return {**value,'virtual':True,'note':'Bucket root; folder dates and total size are not inferred from its children.'}
    try:head=client.head_object(Bucket=bucket,Key=key)
    except ClientError as error:
        if kind=='folder' and str(error.response.get('Error',{}).get('Code')) in ('404','NoSuchKey','NotFound'):
            return {**value,'virtual':True,'note':'Virtual prefix. It has no independent creation/update time, size or provider ID.'}
        raise
    return {**value,'virtual':False,'size':head.get('ContentLength'),
            'updated_at':iso(head.get('LastModified')),'etag':head.get('ETag','').strip('"'),
            'content_type':head.get('ContentType'),'storage_class':head.get('StorageClass'),
            'version_id':head.get('VersionId'),'metadata':head.get('Metadata',{}),
            'note':'Dates/size belong to the marker object only, not the contents of this folder.' if kind=='folder' else
                   'Updated is the current object Last-Modified. ETag is an opaque value, not an object ID or guaranteed MD5.'}
