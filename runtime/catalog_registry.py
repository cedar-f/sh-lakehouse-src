"""Portable UC definitions on R2. No table/volume data or database dumps."""
import hashlib
import json
import os
from pathlib import Path
import threading
import time
from urllib.parse import quote, urlparse
import uuid

from botocore.exceptions import ClientError
import httpx

from config import RUNTIME, identifier
from platform_bootstrap import storage
from catalog_functions import FUNCTION_FIELDS, definition as function_definition, validate_function

MAX_BYTES = 16 * 1024 * 1024
FIELDS = {
    'catalogs': ('name', 'comment', 'properties', 'storage_root', 'storage_location'),
    'schemas': ('name', 'catalog_name', 'comment', 'properties', 'storage_root', 'storage_location'),
    'volumes': ('name', 'catalog_name', 'schema_name', 'comment', 'volume_type', 'storage_location'),
    'tables': ('name', 'catalog_name', 'schema_name', 'comment', 'properties', 'table_type',
               'data_source_format', 'columns', 'storage_location'),
    'functions': FUNCTION_FIELDS,
}


def enabled():
    value = os.getenv('UC_REGISTRY_ENABLED', 'true').lower()
    if value not in ('true', 'false'):
        raise ValueError('UC_REGISTRY_ENABLED must be true or false')
    return value == 'true'


def registry_key():
    prefix = os.getenv('UC_REGISTRY_PREFIX', '_lakehouse/registry/v1').strip().rstrip('/')
    if (not prefix or prefix.startswith('/') or '\\' in prefix or
        any(p in ('', '.', '..') for p in prefix.split('/')) or
        prefix.split('/')[0] in ('warehouse', 'incoming') or any(ord(c) < 32 for c in prefix)):
        raise ValueError('UC_REGISTRY_PREFIX must be a separate relative metadata prefix')
    return prefix + '/current.json'


def name(record):
    return '.'.join(record[k] for k in ('catalog_name', 'schema_name', 'name') if k in record)


def definitions(records, kind):
    if kind=='functions':return sorted((function_definition(r) for r in records),key=name)
    return sorted(({k: r[k] for k in FIELDS[kind] if r.get(k) is not None} for r in records), key=name)


def fingerprint(document):
    # Generated namespace paths change with new UC object IDs. They are informational.
    logical = {kind: [{k: v for k, v in r.items() if not (
        kind in ('catalogs', 'schemas') and k == 'storage_location')} for r in document.get(kind,[])] for kind in FIELDS}
    return hashlib.sha256(json.dumps(logical, sort_keys=True).encode()).hexdigest()


def validate(document, bucket):
    if document.get('version') not in (1,2) or document.get('bucket') != bucket:
        raise ValueError('Registry version or bucket mismatch; registry was not modified')
    if document['version']==1:document.setdefault('functions',[])
    for kind in FIELDS:
        if not isinstance(document.get(kind), list):
            raise ValueError('Invalid registry collection: ' + kind)
        seen = set()
        for r in document[kind]:
            if not isinstance(r, dict): raise ValueError('Invalid registry record')
            for field in ('name', 'catalog_name', 'schema_name'):
                if field in r: identifier(r[field])
            if not r.get('name') or (kind != 'catalogs' and not r.get('catalog_name')) or (
                kind in ('tables', 'volumes','functions') and not r.get('schema_name')):
                raise ValueError('Missing namespace in registry')
            if name(r) in seen: raise ValueError('Duplicate registry record: ' + name(r))
            seen.add(name(r))
            if kind=='functions':validate_function(r)
            if kind!='functions' and r.get('properties') is not None and (not isinstance(r['properties'], dict) or
                any(not isinstance(k, str) or not isinstance(v, str) for k, v in r['properties'].items())):
                raise ValueError('Invalid registry properties')
            if 'comment' in r and not isinstance(r['comment'], str): raise ValueError('Invalid comment')
            for field in ('storage_root', 'storage_location'):
                if r.get(field):
                    u = urlparse(r[field])
                    if u.scheme not in ('s3', 's3a') or u.netloc != bucket or not u.path.strip('/') or '..' in u.path.split('/'):
                        raise ValueError('Registry location must be a path in the configured R2 bucket')
    cats = {r['name'] for r in document['catalogs']}
    schemas = {name(r) for r in document['schemas']}
    if any(r['catalog_name'] not in cats for r in document['schemas']) or any(
        r['catalog_name'] + '.' + r['schema_name'] not in schemas for k in ('tables', 'volumes','functions') for r in document[k]):
        raise ValueError('Registry contains missing parent namespaces')


class Upstream:
    def __init__(self):
        self.base = os.getenv('UC_UPSTREAM_URL', 'http://catalog:8080').rstrip('/') + '/api/2.1/unity-catalog/'

    def request(self, method, path, data=None, params=None):
        with httpx.Client(timeout=60, follow_redirects=False) as client:
            response = client.request(method, self.base + path, json=data, params=params,
                                      headers={'Authorization': 'Bearer not-used'})
            response.raise_for_status()
            return response.json() if response.content else {}

    def listing(self, kind, **params):
        result, seen = [], set()
        while True:
            page = self.request('GET', kind, params=params)
            result.extend(page.get(kind, []))
            token = page.get('next_page_token')
            if not token: return result
            if token in seen: raise ValueError('UC pagination repeated a token')
            seen.add(token); params['page_token'] = token

    def scan(self, bucket):
        result = {'version': 2, 'bucket': bucket, **{k: [] for k in FIELDS}}
        for c in self.listing('catalogs'):
            result['catalogs'].append(self.request('GET', 'catalogs/' + quote(c['name'], safe='')))
            for s in self.listing('schemas', catalog_name=c['name']):
                full = c['name'] + '.' + s['name']
                result['schemas'].append(self.request('GET', 'schemas/' + quote(full, safe='')))
                for kind in ('tables', 'volumes','functions'):
                    for r in self.listing(kind, catalog_name=c['name'], schema_name=s['name']):
                        result[kind].append(self.request('GET', kind + '/' + quote(full + '.' + r['name'], safe='')))
        for kind in FIELDS: result[kind] = definitions(result[kind], kind)
        validate(result, bucket)
        return result


class Registry:
    def __init__(self, store=None, upstream=None, bucket=None, state=None):
        self.store = store if store is not None else storage()
        self.uc = upstream if upstream is not None else Upstream()
        self.bucket = bucket or os.environ['R2_BUCKET']
        self.key = registry_key()
        self.path = Path(state) if state else RUNTIME / 'registry' / 'state.json'
        self.lock = threading.RLock()
        self.etag = None
        self.document = None
        self.state = json.loads(self.path.read_text()) if self.path.exists() else {}
        self.ready = False
        self.error = ''
        self.last_sync = None

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(uuid.uuid4().hex + '.tmp')
        temporary.write_text(json.dumps(self.state), encoding='utf-8')
        temporary.replace(self.path)

    def read(self):
        try:
            response = self.store.get_object(Bucket=self.bucket, Key=self.key)
        except ClientError as e:
            if str(e.response.get('Error', {}).get('Code')) in ('NoSuchKey', '404'):
                return None, None
            raise
        stream = response['Body']
        try: body = stream.read(MAX_BYTES + 1)
        finally: stream.close()
        if len(body) > MAX_BYTES: raise ValueError('Registry exceeds 16 MiB')
        document = json.loads(body)
        validate(document, self.bucket)
        return document, response['ETag']

    def restore(self, document, etag):
        self.state = {'bucket': self.bucket, 'key': self.key, 'etag': etag,
                      'restoring': True, 'unrestored': []}
        self.save()
        live = self.uc.scan(self.bucket)
        for kind in FIELDS:
            existing = {name(r): r for r in live[kind]}
            for r in document[kind]:
                if kind == 'volumes' and r.get('volume_type') != 'EXTERNAL' or (
                    kind == 'tables' and (r.get('table_type') != 'EXTERNAL' or r.get('data_source_format') != 'DELTA')):
                    self.state['unrestored'].append({'kind': kind, 'record': r,
                        'reason': 'Only external Delta tables and external volumes can be replayed safely'})
                    continue
                payload = {k: v for k, v in r.items() if not (kind in ('catalogs', 'schemas') and k == 'storage_location')
                           and not (k == 'comment' and not v)}
                if name(r) in existing:
                    actual = {k: v for k, v in existing[name(r)].items() if not (kind in ('catalogs', 'schemas') and k == 'storage_location')}
                    # UC may omit empty fields, but must not silently replace a conflicting object.
                    clean = lambda d: {k: v for k, v in d.items() if v not in (None, '', {})}
                    if clean(actual) != clean(payload):
                        raise ValueError('Restore conflict at ' + kind + '/' + name(r))
                else:
                    self.uc.request('POST', kind, {'function_info':payload} if kind=='functions' else payload)
        self.state['restoring'] = False
        self.state['dirty'] = False
        self.save()

    def initialize(self):
        with self.lock:
            remote, etag = self.read()
            live = self.uc.scan(self.bucket)
            owned = (self.state.get('bucket') == self.bucket and self.state.get('key') == self.key and
                     self.state.get('etag') == etag)
            if remote is not None and (not live['catalogs'] or owned and self.state.get('restoring')):
                self.restore(remote, etag)
            # v1 never tracked functions. On an unanchored upgrade, adopt the
            # existing UC functions only when every previously tracked asset agrees.
            comparable = {**live,'functions':[]} if remote is not None and remote.get('version')==1 and not remote['functions'] else live
            if remote is not None and not owned and live['catalogs'] and fingerprint(comparable) != fingerprint(remote):
                raise ValueError('Existing UC conflicts with R2 registry. Refusing to overwrite either source; see CATALOG_REGISTRY.md')
            self.document, self.etag = remote, etag
            self.state.update(bucket=self.bucket, key=self.key, etag=etag)
            self.sync()

    def sync(self):
        with self.lock:
            try:
                _, current_etag = self.read()
                if current_etag != self.etag:
                    raise ValueError('R2 registry changed or disappeared externally; refusing a stale writer')
                live = self.uc.scan(self.bucket)
                # Keep inventory of unsupported managed objects after portable replay.
                keep = []
                parents = {name(s) for s in live['schemas']}
                for item in self.state.get('unrestored', []):
                    kind, r = item['kind'], item['record']
                    if r['catalog_name'] + '.' + r['schema_name'] in parents and name(r) not in {name(x) for x in live[kind]}:
                        live[kind].append(r); keep.append(item)
                self.state['unrestored'] = keep
                for kind in FIELDS: live[kind] = definitions(live[kind], kind)
                validate(live, self.bucket)
                live['version']=2
                if self.document is None or self.document.get('version')!=2 or fingerprint(live) != fingerprint(self.document):
                    live['updated_at'] = time.time()
                    body = json.dumps(live, ensure_ascii=False, sort_keys=True).encode()
                    if len(body) > MAX_BYTES: raise ValueError('Registry exceeds 16 MiB')
                    condition = {'IfMatch': self.etag} if self.etag else {'IfNoneMatch': '*'}
                    result = self.store.put_object(Bucket=self.bucket, Key=self.key, Body=body,
                        ContentType='application/json', **condition)
                    self.document, self.etag = live, result['ETag']
                self.state.update(etag=self.etag, dirty=False)
                self.save()
                self.ready, self.error, self.last_sync = True, '', time.time()
                return self.status()
            except Exception as e:
                self.ready = False
                self.error = type(e).__name__ + ': registry sync failed; inspect registry service logs'
                raise

    def dirty(self):
        self.state['dirty'] = True
        self.save()

    def status(self):
        return {'enabled': True, 'ready': self.ready, 'bucket': self.bucket, 'key': self.key,
                'last_sync': self.last_sync, 'pending': bool(self.state.get('dirty')), 'error': self.error,
                'counts': {k: len((self.document or {}).get(k, [])) for k in FIELDS},
                'nonportable': [{'kind': kind, 'name': name(r)} for kind in ('volumes', 'tables')
                    for r in (self.document or {}).get(kind, []) if (
                        kind == 'volumes' and r.get('volume_type') != 'EXTERNAL' or
                        kind == 'tables' and (r.get('table_type') != 'EXTERNAL' or r.get('data_source_format') != 'DELTA'))],
                'unrestored': [{'kind': x['kind'], 'name': name(x['record']), 'reason': x['reason']}
                               for x in self.state.get('unrestored', [])]}
