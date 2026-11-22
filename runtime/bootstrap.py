import os
from urllib.error import HTTPError
from config import ROOT, uc, identifier, timezone_name
from platform_bootstrap import ensure_layout, storage, sample_enabled, seed_sample
catalog=identifier(os.getenv('DEFAULT_CATALOG','lakehouse'))
schema=identifier(os.getenv('DEFAULT_SCHEMA','default'))
bucket=os.environ['R2_BUCKET']
print('R2 layout:', ensure_layout(storage(), bucket), flush=True)
seed = sample_enabled()
resources=[('catalogs',{'name':catalog,'storage_root':f's3://{bucket}/warehouse/{catalog}'}),
    ('schemas',{'name':'default','catalog_name':catalog})]
if schema!='default': resources.append(('schemas',{'name':schema,'catalog_name':catalog}))
if seed and schema != 'dbt_sample':
    resources.append(('schemas',{'name':'dbt_sample','catalog_name':catalog}))
resources.append(
    ('volumes',{'name':'incoming','catalog_name':catalog,'schema_name':schema,'volume_type':'EXTERNAL',
                'storage_location':f's3://{bucket}/incoming/'}))
for resource,data in resources:
    try: uc('POST',resource,data)
    except HTTPError as e:
        if e.code != 409 and 'ALREADY_EXISTS' not in e.read().decode(): raise
print('Catalog, schema and incoming volume initialized')
if seed:
    print('dbt starter:', seed_sample(ROOT, catalog, timezone_name()))
    print('Load dbt_sample_pipeline in Workflows, then Save & publish / Execute. Schedule is off.')
