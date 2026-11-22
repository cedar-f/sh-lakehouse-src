"""Explicit migration of V2's R2 name registry to real UC external tables."""
import json,os,sys
from urllib.error import HTTPError
from urllib.parse import urlparse
from config import uc,identifier
from lakehouse_server import storage
from spark_session import create_spark,refresh_catalogs

apply='--apply' in sys.argv
client=storage(); items=[]
for page in client.get_paginator('list_objects_v2').paginate(Bucket=os.environ['R2_BUCKET'],Prefix='_lakehouse_registry/v1/'):
    for item in page.get('Contents',[]):
        if not item['Key'].endswith('.json'): continue
        obj=client.get_object(Bucket=os.environ['R2_BUCKET'],Key=item['Key'])
        try: record=json.load(obj['Body'])
        finally: obj['Body'].close()
        parts=record['full_name'].split('.')
        if len(parts)!=3: raise ValueError('Invalid V2 table name')
        for part in parts: identifier(part)
        uri=urlparse(record['storage_location'])
        if uri.scheme not in ('s3','s3a') or uri.netloc!=os.environ['R2_BUCKET'] or "'" in uri.path or '..' in uri.path.split('/'):
            raise ValueError('Invalid V2 table location')
        items.append((parts,'s3://'+uri.netloc+uri.path))
for parts,location in items: print('.'.join(parts)+' -> '+location)
if not apply: raise SystemExit('Preview only. Re-run with --apply to register these tables; Delta files are not copied.')
spark=create_spark()
hc=spark.sparkContext._jsc.hadoopConfiguration()
hc.set('fs.s3a.access.key',os.environ['R2_ACCESS_KEY_ID'])
hc.set('fs.s3a.secret.key',os.environ['R2_SECRET_ACCESS_KEY'])
hc.set('fs.s3a.aws.credentials.provider','org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider')
for (catalog,schema,name),location in items:
    for resource,data in [('catalogs',{'name':catalog,'storage_root':f"s3://{os.environ['R2_BUCKET']}/warehouse/{catalog}"}),('schemas',{'name':schema,'catalog_name':catalog})]:
        try: uc('POST',resource,data)
        except HTTPError as e:
            if e.code!=409 and 'ALREADY_EXISTS' not in e.read().decode(): raise
    refresh_catalogs(spark)
    # Explicit external registration; the original V2 files remain in their original location.
    spark.sql(f"CREATE TABLE IF NOT EXISTS `{catalog}`.`{schema}`.`{name}` USING DELTA LOCATION '{location}'")
    print('Registered '+catalog+'.'+schema+'.'+name)
spark.stop()
