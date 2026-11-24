import copy
import io
import json

from botocore.exceptions import ClientError
import pytest

from catalog_registry import Registry, Upstream, fingerprint, name, registry_key, validate


def error(code):
    return ClientError({'Error': {'Code': code}, 'ResponseMetadata': {'HTTPStatusCode': 412 if code=='PreconditionFailed' else 403}}, 'fixture')


class Store:
    def __init__(self, document=None):
        self.body=json.dumps(document).encode() if document else None
        self.etag='"0"' if document else None
        self.puts=[];self.fail=False

    def get_object(self, **kwargs):
        if self.fail:raise error('AccessDenied')
        if self.body is None:raise error('NoSuchKey')
        return {'Body':io.BytesIO(self.body),'ETag':self.etag}

    def put_object(self, **kwargs):
        if self.fail:raise error('AccessDenied')
        if kwargs.get('IfNoneMatch')=='*' and self.body is not None or kwargs.get('IfMatch',self.etag)!=self.etag:
            raise error('PreconditionFailed')
        self.body=kwargs['Body'];self.etag='"'+str(len(self.puts)+1)+'"';self.puts.append(kwargs)
        return {'ETag':self.etag}


def document():
    return {'version':2,'bucket':'fixture','catalogs':[
        {'name':'empty','comment':'empty catalog','properties':{'department':'finance'},'storage_root':'s3://fixture/empty'},
        {'name':'sales','comment':'Sales','storage_root':'s3://fixture/warehouse/sales','storage_location':'s3://fixture/warehouse/sales/__unitystorage/catalogs/old'}],
        'schemas':[{'name':'empty_schema','catalog_name':'sales','comment':'No tables','properties':{'stage':'future'},'storage_root':'s3://fixture/separate'},
                   {'name':'raw','catalog_name':'sales'}],
        'volumes':[{'name':'landing','catalog_name':'sales','schema_name':'raw','comment':'CSV files','volume_type':'EXTERNAL','storage_location':'s3://fixture/incoming'}],
        'functions':[],
        'tables':[{'name':'orders','catalog_name':'sales','schema_name':'raw','table_type':'EXTERNAL','data_source_format':'DELTA',
                   'storage_location':'s3://fixture/external/orders','columns':[{'name':'id','type_text':'int','type_name':'INT','type_json':'"integer"','position':0}]}]}


def view(view_name,source=None):
    return {'name':view_name,'catalog_name':'sales','schema_name':'raw','table_type':'VIEW',
            'view_definition':'SELECT 1 AS id' if not source else 'SELECT * FROM '+source,
            'columns':[{'name':'id','type_text':'int','type_name':'INT','type_json':'"integer"','position':0}],
            'view_dependencies':{'dependencies':[{'table':{'table_full_name':source}}] if source else []}}


def test_views_upgrade_registry_and_replay_after_dependencies(tmp_path):
    data=document();data['tables'] += [view('a_child','sales.raw.z_parent'),view('z_parent','sales.raw.orders')]
    store=Store();r=engine(tmp_path/'source',store,UC(data));r.initialize()
    assert json.loads(store.body)['version']==3
    target=UC();restored=engine(tmp_path/'target',store,target);restored.initialize()
    assert [name(p) for k,p in target.posts if k=='tables']==['sales.raw.orders','sales.raw.z_parent','sales.raw.a_child']
    assert not restored.status()['unrestored'] and not restored.status()['nonportable']


def test_view_with_missing_managed_dependency_is_preserved_as_unrestored(tmp_path):
    data=document();data['tables'][0]['table_type']='MANAGED';data['tables'].append(view('read_orders','sales.raw.orders'))
    store=Store(data);target=UC();r=engine(tmp_path,store,target);r.initialize()
    assert len(r.status()['unrestored'])==2
    assert not target.data['tables']
    assert any(t.get('view_definition') for t in json.loads(store.body)['tables'])


class UC:
    def __init__(self, data=None):
        self.data=copy.deepcopy(data) if data is not None else {'version':2,'bucket':'fixture',**{k:[] for k in ('catalogs','schemas','tables','volumes','functions')}}
        self.posts=[];self.fail_on=None

    def scan(self, bucket):return copy.deepcopy(self.data)

    def request(self, method, kind, payload):
        assert method=='POST'
        if kind=='functions':payload=payload['function_info']
        if name(payload)==self.fail_on:raise RuntimeError('interrupted restore')
        assert name(payload) not in {name(x) for x in self.data[kind]}
        self.posts.append((kind,copy.deepcopy(payload)))
        record=copy.deepcopy(payload)
        if kind in ('catalogs','schemas') and record.get('storage_root'):
            record['storage_location']=record['storage_root']+'/__unitystorage/'+kind+'/new-id'
        self.data[kind].append(record)


def engine(tmp_path, store, uc):return Registry(store,uc,'fixture',tmp_path/'state.json')


def test_restore_empty_namespaces_comments_properties_storage_roots_and_external_assets(tmp_path):
    source=document();store=Store(source);uc=UC();r=engine(tmp_path,store,uc);r.initialize()
    assert [k for k,_ in uc.posts]==['catalogs','catalogs','schemas','schemas','volumes','tables']
    assert uc.data['catalogs'][0]['properties']=={'department':'finance'}
    assert uc.data['schemas'][0]['comment']=='No tables' and uc.data['schemas'][0]['storage_root']=='s3://fixture/separate'
    assert uc.data['volumes']==source['volumes']
    assert uc.data['tables']==source['tables']
    assert not store.puts  # Informational generated managed namespace paths are not replayed.
    assert r.status()['ready'] and not r.status()['unrestored']
    assert not r.state['restoring']


def test_live_updates_rename_and_drop_are_synced_without_resurrecting_deleted_objects(tmp_path):
    store=Store();uc=UC(document());r=engine(tmp_path,store,uc);r.initialize()
    assert store.puts[0]['IfNoneMatch']=='*'
    uc.data['schemas'][0]['comment']='Updated'
    r.dirty();r.sync()
    assert json.loads(store.body)['schemas'][0]['comment']=='Updated'
    uc.data['volumes'][0]['name']='new_landing'
    uc.data['tables']=[]
    r.dirty();r.sync()
    saved=json.loads(store.body)
    assert saved['tables']==[] and saved['volumes'][0]['name']=='new_landing'
    restored=UC();engine(tmp_path/'fresh',store,restored).initialize()
    assert not restored.data['tables'] and restored.data['volumes'][0]['name']=='new_landing'


def test_nonempty_uc_conflict_without_local_anchor_is_rejected(tmp_path):
    store=Store(document());other=document();other['catalogs'][0]['comment']='different'
    uc=UC(other)
    with pytest.raises(ValueError,match='conflicts'):engine(tmp_path,store,uc).initialize()
    assert not store.puts and not uc.posts


def test_partial_restore_resumes_and_does_not_overwrite_existing_object(tmp_path):
    store=Store(document());uc=UC();uc.fail_on='sales.raw.landing'
    with pytest.raises(RuntimeError):engine(tmp_path,store,uc).initialize()
    assert json.loads((tmp_path/'state.json').read_text())['restoring']
    uc.fail_on=None
    r=engine(tmp_path,store,uc);r.initialize()
    assert r.ready and len(uc.posts)==6
    assert not store.puts


def test_r2_failure_marks_pending_and_retry_preserves_new_uc_metadata(tmp_path):
    store=Store();uc=UC(document());r=engine(tmp_path,store,uc);r.initialize();old=store.body
    uc.data['catalogs'][0]['comment']='new comment';r.dirty();store.fail=True
    with pytest.raises(ClientError):r.sync()
    assert not r.ready and r.status()['pending'] and store.body==old
    store.fail=False
    # Restart recovers an acknowledged local lineage and flushes the pending change.
    again=engine(tmp_path,store,uc);again.initialize()
    assert again.ready and json.loads(store.body)['catalogs'][0]['comment']=='new comment'


def test_access_denied_is_not_treated_as_missing_registry(tmp_path):
    store=Store();store.fail=True;uc=UC(document())
    with pytest.raises(ClientError):engine(tmp_path,store,uc).initialize()
    assert not store.puts and not uc.posts


def test_conditional_write_refuses_another_writer(tmp_path):
    store=Store(document());uc=UC(document());r=engine(tmp_path,store,uc);r.initialize()
    store.etag='"other-writer"';previous=store.body
    uc.data['catalogs'][0]['comment']='local edit';r.dirty()
    with pytest.raises(ValueError,match='changed or disappeared'):r.sync()
    assert store.body==previous and not r.ready


def test_empty_uc_never_overwrites_nonempty_registry_on_boot(tmp_path):
    store=Store(document());before=store.body;r=engine(tmp_path,store,UC());r.initialize()
    assert r.document['catalogs'] and store.body==before


def test_managed_records_remain_in_inventory_and_are_reported_not_downgraded(tmp_path):
    source=document();source['tables'][0]['table_type']='MANAGED';source['volumes'][0]['volume_type']='MANAGED'
    store=Store(source);uc=UC();r=engine(tmp_path,store,uc);r.initialize()
    assert not uc.data['tables'] and not uc.data['volumes']
    assert len(r.status()['unrestored'])==2 and not store.puts
    uc.data['catalogs'][0]['comment']='a change';r.dirty();r.sync()
    assert json.loads(store.body)['tables'][0]['table_type']=='MANAGED'
    assert json.loads(store.body)['volumes'][0]['volume_type']=='MANAGED'


def test_managed_replay_limit_is_visible_before_any_local_reset(tmp_path):
    source=document();source['tables'][0]['table_type']='MANAGED'
    r=engine(tmp_path,Store(),UC(source));r.initialize()
    assert not r.status()['unrestored']
    assert r.status()['nonportable']==[{'kind':'tables','name':'sales.raw.orders'}]


@pytest.mark.parametrize('change',[
    lambda d:d.update(bucket='different'), lambda d:d.update(version=999),
    lambda d:d['catalogs'].append(d['catalogs'][0]), lambda d:d['schemas'][0].update(catalog_name='missing'),
    lambda d:d['volumes'][0].update(storage_location='s3://another/incoming'),
])
def test_invalid_registry_fails_before_restore_or_publish(tmp_path,change):
    source=document();change(source);store=Store(source);uc=UC()
    with pytest.raises(ValueError):engine(tmp_path,store,uc).initialize()
    assert not uc.posts and not store.puts


def test_scan_includes_empty_namespaces_and_follows_all_pages(monkeypatch):
    uc=Upstream();requests=[]
    def request(method,path,data=None,params=None):
        requests.append((path,dict(params or {})))
        if path=='catalogs':
            return {'catalogs':[{'name':'sales'}]} if params.get('page_token') else {'catalogs':[{'name':'empty'}],'next_page_token':'next'}
        if path=='catalogs/empty':return document()['catalogs'][0]
        if path=='catalogs/sales':return document()['catalogs'][1]
        if path=='schemas':return {'schemas':[]} if params['catalog_name']=='empty' else {'schemas':[{'name':'empty_schema'}]}
        if path=='schemas/sales.empty_schema':return document()['schemas'][0]
        if path in ('tables','volumes','functions'):return {path:[]}
        raise AssertionError(path)
    monkeypatch.setattr(uc,'request',request)
    result=uc.scan('fixture')
    assert len(result['catalogs'])==2 and result['schemas'][0]['properties']=={'stage':'future'}
    assert ('catalogs',{'page_token':'next'}) in requests


@pytest.mark.parametrize('prefix',['','/root','warehouse/meta','incoming/meta','../meta','x//y','x\\y'])
def test_registry_prefix_cannot_target_table_data(monkeypatch,prefix):
    monkeypatch.setenv('UC_REGISTRY_PREFIX',prefix)
    with pytest.raises(ValueError):registry_key()


def function():
    from catalog_functions import create_payload
    return create_payload({'name':'increment','catalog_name':'sales','schema_name':'raw','language':'PYTHON',
        'return_type':'INT','parameters':[{'name':'value','type':'INT'}],'body':'return value + 1',
        'comment':'Increment an integer'})['function_info']


def test_functions_replay_preserves_body_types_comments_and_dependencies(tmp_path):
    source=document();f=function();f['properties']='{"team":"data"}'
    f['routine_dependencies']={'dependencies':[{'table':{'table_full_name':'sales.raw.orders'}}]}
    source['functions']=[f];store=Store(source);uc=UC()
    r=engine(tmp_path,store,uc);r.initialize()
    assert uc.data['functions']==[f] and not store.puts
    assert r.status()['counts']['functions']==1
    uc.data['functions'][0]['routine_definition']='return value + 2'
    r.dirty();r.sync()
    assert json.loads(store.body)['functions'][0]['routine_definition']=='return value + 2'
    uc.data['functions']=[];r.dirty();r.sync()
    restored=UC();engine(tmp_path/'new',store,restored).initialize()
    assert not restored.data['functions']


def test_v1_manifest_upgrades_conditionally_without_losing_existing_assets(tmp_path):
    source=document();source['version']=1;source.pop('functions')
    store=Store(source);uc=UC(document());r=engine(tmp_path,store,uc);r.initialize()
    value=json.loads(store.body)
    assert value['version']==2 and value['functions']==[]
    assert value['tables']==source['tables'] and store.puts[-1]['IfMatch']=='"0"'


def test_v1_upgrade_without_local_state_adopts_previously_untracked_functions(tmp_path):
    source=document();source['version']=1;source.pop('functions')
    live=document();live['functions']=[function()]
    store=Store(source);r=engine(tmp_path,store,UC(live));r.initialize()
    assert json.loads(store.body)['functions']==live['functions']


def test_function_sync_failure_cannot_erase_last_published_definition(tmp_path):
    source=document();source['functions']=[function()];store=Store(source);uc=UC(source)
    r=engine(tmp_path,store,uc);r.initialize();previous=store.body
    uc.data['functions'][0]['routine_definition']='return value + 5';r.dirty();store.fail=True
    with pytest.raises(ClientError):r.sync()
    assert store.body==previous and not r.ready and r.status()['pending']


def test_corrupt_function_is_rejected_before_any_restore(tmp_path):
    source=document();f=function();f['input_params']['parameters'][0]['position']=5;source['functions']=[f]
    uc=UC();store=Store(source)
    with pytest.raises(ValueError):engine(tmp_path,store,uc).initialize()
    assert not uc.posts
