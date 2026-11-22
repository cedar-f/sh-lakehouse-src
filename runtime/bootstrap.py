import os
from urllib.error import HTTPError
from config import uc, identifier
catalog=identifier(os.getenv('DEFAULT_CATALOG','lakehouse'))
schema=identifier(os.getenv('DEFAULT_SCHEMA','default'))
bucket=os.environ['R2_BUCKET']
resources=[('catalogs',{'name':catalog,'storage_root':f's3://{bucket}/warehouse/{catalog}'}),
    ('schemas',{'name':'default','catalog_name':catalog})]
if schema!='default': resources.append(('schemas',{'name':schema,'catalog_name':catalog}))
resources.append(
    ('volumes',{'name':'incoming','catalog_name':catalog,'schema_name':schema,'volume_type':'EXTERNAL',
                'storage_location':f's3://{bucket}/incoming/'}))
for resource,data in resources:
    try: uc('POST',resource,data)
    except HTTPError as e:
        if e.code != 409 and 'ALREADY_EXISTS' not in e.read().decode(): raise
print('Catalog, schema and incoming volume initialized')
