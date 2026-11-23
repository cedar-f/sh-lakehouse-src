"""Compare-and-replace UC functions under the registry service's metadata lock."""
import hashlib
import json
import logging
from urllib.parse import quote

from fastapi import HTTPException
import httpx

from catalog_functions import definition, validate_function

LOG = logging.getLogger('catalog-registry')


def digest(value):
    def clean(value):
        if isinstance(value,dict):return {k:clean(v) for k,v in value.items() if v not in (None,'',{},[])}
        if isinstance(value,list):return [clean(v) for v in value]
        return value
    return hashlib.sha256(json.dumps(clean(definition(value)),sort_keys=True).encode()).hexdigest()


def recover_replacement(upstream,intent):
    """Never publish a missing function during a partially completed replacement."""
    path='functions/'+quote(intent['name'],safe='')
    try:current=upstream.request('GET',path)
    except httpx.HTTPStatusError as error:
        if error.response.status_code!=404:raise
        current=upstream.request('POST','functions',{'function_info':intent['old']})
    if digest(current) not in (digest(intent['old']),digest(intent['new'])):
        raise ValueError('Function replacement recovery conflicts with an unrelated definition')
    return current


def replace_function(payload,upstream,engine=None):
    value=validate_function(definition(payload.get('function_info',{})))
    name='.'.join(value[k] for k in ('catalog_name','schema_name','name'))
    path='functions/'+quote(name,safe='')
    if engine and not engine.ready:raise HTTPException(503,'Registry pending; check status before replacing a function')
    old=upstream.request('GET',path)
    if payload.get('expected')!=digest(old):raise HTTPException(409,'Function changed concurrently; read the current definition before retrying')
    if old.get('routine_body')!='SQL' or value.get('routine_body')!='SQL':
        raise HTTPException(400,'SQL replacement cannot replace a Python/external function')
    signature=lambda f:[(p['name'],p['type_name'],p.get('type_precision'),p.get('type_scale')) for p in f['input_params']['parameters']]
    if signature(old)!=signature(value):raise HTTPException(400,'OR REPLACE requires the same parameter names/types; use a new function name for a different signature')
    intent={'name':name,'old':definition(old),'new':value}
    if engine:
        engine.state['function_replacement']=intent
        engine.dirty()
    deleted=False
    try:
        upstream.request('DELETE',path);deleted=True
        result=upstream.request('POST','functions',{'function_info':value})
    except Exception as error:
        LOG.exception('UC function replacement failed at %s',name)
        if deleted and engine is None:
            try:
                upstream.request('GET',path)
            except httpx.HTTPStatusError as missing:
                if missing.response.status_code==404:
                    try:upstream.request('POST','functions',{'function_info':definition(old)})
                    except Exception:pass
            except Exception:pass
        if engine:
            try:engine.sync()
            except Exception:
                engine.ready=False;engine.error='Function replacement recovery pending; inspect UC and registry before retrying'
        raise HTTPException(503,'Function replacement failed; check current UC definition and registry before retrying. Previous definition restoration was attempted when safe.') from error
    if engine:
        try:engine.sync()
        except Exception as error:
            raise HTTPException(503,'Function was replaced in UC but R2 sync is pending; check before retrying') from error
    return result
