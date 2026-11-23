import copy

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from catalog_registry import Registry
from function_mutations import digest,replace_function
from sql_functions import parse_create
from test_catalog_registry import Store
import registry_service


OLD=parse_create('CREATE FUNCTION cat.tools.f(x INT) RETURNS INT RETURN x + 1')[0]
NEW={**OLD,'routine_definition':'x + 2'}


class UC:
    def __init__(self):self.function=copy.deepcopy(OLD);self.fail=0;self.posts=[]
    def request(self,method,path,data=None):
        if method=='GET':
            if self.function is None:
                response=httpx.Response(404,request=httpx.Request('GET','http://fixture'))
                raise httpx.HTTPStatusError('missing',request=response.request,response=response)
            return copy.deepcopy(self.function)
        if method=='DELETE':self.function=None;return {}
        if self.fail:
            self.fail-=1;raise RuntimeError('injected create failure')
        self.posts.append(data);self.function=copy.deepcopy(data['function_info']);return self.function
    def scan(self,bucket):
        return {'version':2,'bucket':bucket,'catalogs':[{'name':'cat'}],
                'schemas':[{'name':'tools','catalog_name':'cat'}],'tables':[],'volumes':[],
                'functions':[copy.deepcopy(self.function)] if self.function else []}


def setup(tmp_path):
    uc=UC();store=Store();engine=Registry(store,uc,'fixture',tmp_path/'state.json');engine.initialize()
    return uc,store,engine


def test_replace_compares_current_definition_then_syncs_new_body(tmp_path):
    uc,store,engine=setup(tmp_path)
    replace_function({'function_info':NEW,'expected':digest(OLD)},uc,engine)
    assert engine.document['functions'][0]['routine_definition']=='x + 2'
    assert not engine.state.get('function_replacement') and not engine.state['dirty']


def test_stale_update_and_signature_changes_never_delete_old_function(tmp_path):
    uc,store,engine=setup(tmp_path);previous=store.body
    with pytest.raises(HTTPException,match='concurrently'):replace_function({'function_info':NEW,'expected':'stale'},uc,engine)
    changed=copy.deepcopy(NEW);changed['input_params']['parameters'][0]['name']='other'
    with pytest.raises(HTTPException,match='same parameter'):replace_function({'function_info':changed,'expected':digest(OLD)},uc,engine)
    assert uc.function==OLD and store.body==previous


def test_failed_create_recovers_previous_function_before_publishing(tmp_path):
    uc,store,engine=setup(tmp_path);previous=store.body;uc.fail=1
    with pytest.raises(HTTPException,match='replacement failed'):replace_function({'function_info':NEW,'expected':digest(OLD)},uc,engine)
    assert uc.function==OLD and store.body==previous


def test_failed_recovery_preserves_last_r2_definition_and_recovers_after_restart(tmp_path):
    uc,store,engine=setup(tmp_path);previous=store.body;uc.fail=2
    with pytest.raises(HTTPException):replace_function({'function_info':NEW,'expected':digest(OLD)},uc,engine)
    assert uc.function is None and store.body==previous and not engine.ready
    assert engine.state.get('function_replacement')
    again=Registry(store,uc,'fixture',tmp_path/'state.json');again.initialize()
    assert uc.function==OLD and again.ready and not again.state.get('function_replacement')


def test_r2_failure_after_replace_remains_pending_without_rolling_back_committed_change(tmp_path):
    uc,store,engine=setup(tmp_path);previous=store.body;store.fail=True
    with pytest.raises(HTTPException,match='R2 sync'):replace_function({'function_info':NEW,'expected':digest(OLD)},uc,engine)
    assert uc.function==NEW and store.body==previous and not engine.ready
    store.fail=False;engine.sync();assert engine.document['functions'][0]==NEW


def test_replace_control_requires_internal_auth(monkeypatch):
    monkeypatch.setenv('RUNNER_TOKEN','fixture-token')
    assert TestClient(registry_service.app).post('/registry/functions/replace',json={}).status_code==401


def test_uc_delete_accepts_plain_text_acknowledgement(monkeypatch):
    from catalog_registry import Upstream
    from config import uc
    import urllib.request
    from io import BytesIO
    class Client:
        def __init__(self,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def request(self,*args,**kwargs):
            return httpx.Response(200,text='200 OK',request=httpx.Request('DELETE','http://fixture'))
    monkeypatch.setattr(httpx,'Client',Client)
    monkeypatch.setattr(urllib.request,'urlopen',lambda *args,**kwargs:BytesIO(b'200 OK'))
    assert Upstream().request('DELETE','functions/c.s.f')=={}
    assert uc('DELETE','functions/c.s.f')=={}
