import pytest
import httpx
from fastapi import HTTPException
from fastapi.testclient import TestClient

import registry_service as service


class Engine:
    def __init__(self):self.ready=True;self.events=[];self.error='';self.fail=False
    def initialize(self):self.events.append('initialize')
    def dirty(self):self.events.append('dirty')
    def sync(self):
        self.events.append('sync')
        if self.fail:self.ready=False;raise RuntimeError('storage unavailable')
        return self.status()
    def status(self):return {'ready':self.ready,'enabled':True}


def test_control_endpoints_require_internal_token_and_health_tracks_pending(monkeypatch):
    engine=Engine()
    monkeypatch.setattr(service,'Registry',lambda:engine)
    monkeypatch.setattr(service,'engine',None)
    monkeypatch.setattr(service,'enabled',lambda:True)
    monkeypatch.setenv('RUNNER_TOKEN','fixture-token')
    with TestClient(service.app) as client:
        assert client.get('/registry/status').status_code==401
        assert client.post('/registry/sync').status_code==401
        assert client.get('/registry/status',headers={'X-Runner-Token':'fixture-token'}).json()['ready']
        assert client.post('/registry/sync',headers={'X-Runner-Token':'fixture-token'}).status_code==200
        engine.ready=False
        assert client.get('/health').status_code==503
    assert engine.events==['initialize','sync']


def client_stub(monkeypatch,engine,response=200):
    class Client:
        def __init__(self,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def request(self,*args,**kwargs):
            engine.events.append('upstream')
            assert kwargs['params']=='catalog_name=sales'
            return httpx.Response(response,json={'name':'sales'})
    monkeypatch.setattr(service.httpx,'Client',Client)
    monkeypatch.setattr(service,'engine',engine)


def test_metadata_ack_only_after_registry_sync_and_read_requests_do_not_export(monkeypatch):
    engine=Engine();client_stub(monkeypatch,engine)
    path='api/2.1/unity-catalog/catalogs'
    assert service.forward('POST',path,'catalog_name=sales',b'{}','application/json','').status_code==200
    assert engine.events==['dirty','upstream','sync']
    engine.events=[]
    service.forward('GET',path,'catalog_name=sales',b'','application/json','')
    assert engine.events==['upstream']


def test_storage_failure_after_uc_write_is_explicit_and_blocks_next_mutation(monkeypatch):
    engine=Engine();engine.fail=True;client_stub(monkeypatch,engine)
    path='api/2.1/unity-catalog/schemas'
    with pytest.raises(HTTPException,match='already have succeeded'):
        service.forward('POST',path,'catalog_name=sales',b'{}','application/json','')
    assert engine.events==['dirty','upstream','sync'] and not engine.ready
    with pytest.raises(HTTPException,match='pending'):
        service.forward('DELETE',path,'catalog_name=sales',b'','application/json','')
    assert engine.events==['dirty','upstream','sync']


def test_new_table_cannot_silently_replace_unrestored_managed_inventory(monkeypatch):
    engine=Engine();client_stub(monkeypatch,engine)
    engine.state={'unrestored':[{'kind':'tables','record':{'catalog_name':'sales','schema_name':'raw','name':'orders'}}]}
    with pytest.raises(HTTPException,match='unrestored managed'):
        service.forward('POST','api/2.1/unity-catalog/tables','catalog_name=sales',
                        b'{"catalog_name":"sales","schema_name":"raw","name":"orders"}','application/json','')
    assert not engine.events


@pytest.mark.parametrize('method,path,expected',[
    ('POST','api/2.1/unity-catalog/tables',True),
    ('PATCH','api/2.1/unity-catalog/volumes/a.b.c',True),
    ('DELETE','api/2.1/unity-catalog/schemas/a.b',True),
    ('GET','api/2.1/unity-catalog/catalogs',False),
    ('POST','api/2.1/unity-catalog/temporary-table-credentials',False),
    ('POST','api/2.1/unity-catalog/tablesx',False),
])
def test_metadata_mutation_classification(method,path,expected):
    assert service.is_metadata(method,path)==expected
