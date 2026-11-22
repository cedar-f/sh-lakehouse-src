"""Opt-in integration test: creates a uniquely named Delta table on the configured R2."""
import json,os,time,uuid
import httpx
name='v3_check_'+uuid.uuid4().hex[:8]
base='http://127.0.0.1:8765'
headers={'X-Runner-Token':os.environ['RUNNER_TOKEN']}
with httpx.Client(timeout=600,headers=headers) as c:
    result=c.post(base+'/sql',json={'sql':f'CREATE TABLE {name} USING DELTA AS SELECT 1 AS id, \'V3\' AS label'})
    result.raise_for_status()
    result=c.post(base+'/sql',json={'sql':f'SELECT * FROM {name}'})
    result.raise_for_status(); assert result.json()['rows']==[[1,'V3']],result.text
    from config import uc,settings
    s=settings(); full=s['default_catalog']+'.'+s['default_schema']+'.'+name
    table=uc('GET','tables/'+full)
    assert table['table_type']=='MANAGED',table
    assert table['storage_location'].startswith('s3://'+os.environ['R2_BUCKET']+'/'),table
    print('PASS: CREATE TABLE defaults to UC managed Delta; SELECT succeeds; metadata is persisted in UC.')
    print('Test table retained for inspection: '+full)
