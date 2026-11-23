"""Internal UC proxy, durable R2 registry and startup replay barrier."""
import asyncio
from contextlib import asynccontextmanager
import logging
import os
import threading

from fastapi import FastAPI, Header, HTTPException, Request, Response
import httpx

from catalog_registry import Registry, enabled

LOG = logging.getLogger('catalog-registry')
engine = None
guard = threading.RLock()


def interval():
    value = int(os.getenv('UC_REGISTRY_SYNC_SECONDS', '60'))
    if not 10 <= value <= 3600: raise ValueError('UC_REGISTRY_SYNC_SECONDS must be 10..3600')
    return value


def sync():
    with guard:
        if engine is None: return {'enabled': False, 'ready': True}
        return engine.sync()


async def reconcile():
    while True:
        await asyncio.sleep(interval())
        try: await asyncio.to_thread(sync)
        except Exception: LOG.error('Registry reconciliation failed; metadata writes are blocked', exc_info=True)


@asynccontextmanager
async def lifespan(app):
    global engine
    interval()
    if enabled():
        engine = Registry()
        await asyncio.to_thread(engine.initialize)
    task = asyncio.create_task(reconcile())
    try: yield
    finally:
        task.cancel()
        try: await task
        except asyncio.CancelledError: pass


app = FastAPI(lifespan=lifespan)


def auth(token):
    import hmac
    expected = os.getenv('RUNNER_TOKEN', '')
    if not expected or not hmac.compare_digest(token or '', expected): raise HTTPException(401, 'Unauthorized')


@app.get('/health')
def health():
    if engine is not None and not engine.ready: raise HTTPException(503, 'Registry synchronization pending')
    return {'ready': True}


@app.get('/registry/status')
def status(x_runner_token: str = Header(default='')):
    auth(x_runner_token)
    return engine.status() if engine else {'enabled': False, 'ready': True}


@app.post('/registry/sync')
def manual_sync(x_runner_token: str = Header(default='')):
    auth(x_runner_token)
    try: return sync()
    except Exception:
        LOG.error('Registry sync failed', exc_info=True)
        raise HTTPException(503, 'Registry sync failed; inspect service logs')


@app.post('/registry/functions/replace')
def function_replace(payload: dict,x_runner_token: str = Header(default='')):
    auth(x_runner_token)
    from catalog_registry import Upstream
    from function_mutations import replace_function
    try:
        with guard:return replace_function(payload,Upstream(),engine)
    except ValueError as error:raise HTTPException(400,str(error))


def is_metadata(method, path):
    return method in ('POST', 'PATCH', 'PUT', 'DELETE') and any(
        path == 'api/2.1/unity-catalog/' + kind or path.startswith('api/2.1/unity-catalog/' + kind + '/')
        for kind in ('catalogs', 'schemas', 'tables', 'volumes','functions'))


def forward(method, path, query, body, content_type, authorization):
    mutation = is_metadata(method, path)
    # Serialize snapshot reads with all proxy metadata writes.
    lock = guard if mutation else threading.RLock()
    with lock:
        if mutation and engine:
            if not engine.ready: raise HTTPException(503, 'Registry is pending; check Catalog registry status before retrying')
            if method == 'POST' and path.rsplit('/', 1)[-1] in ('tables', 'volumes'):
                import json
                from catalog_registry import name
                try: candidate = name(json.loads(body))
                except (ValueError, TypeError): candidate = ''
                kind = path.rsplit('/', 1)[-1]
                if any(item['kind'] == kind and name(item['record']) == candidate
                       for item in getattr(engine, 'state', {}).get('unrestored', [])):
                    raise HTTPException(409, 'This name belongs to an unrestored managed object in R2. Recover its metadata before reusing the name.')
            engine.dirty()
        try:
            with httpx.Client(timeout=120, follow_redirects=False) as client:
                result = client.request(method, os.getenv('UC_UPSTREAM_URL', 'http://catalog:8080').rstrip('/') + '/' + path,
                    params=query, content=body, headers={'Content-Type': content_type,
                    'Authorization': authorization or 'Bearer not-used'})
        except httpx.HTTPError:
            if mutation and engine:
                engine.ready = False
                engine.error = 'UC response unknown; reconciliation required before retry'
            raise HTTPException(503, 'UC unavailable; a submitted metadata change may already have been applied')
        if mutation and engine:
            try: engine.sync()
            except Exception:
                LOG.error('UC mutation completed but registry sync failed', exc_info=True)
                raise HTTPException(503, 'UC change may already have succeeded; R2 registry is pending. Check before retrying.')
        return Response(content=result.content, status_code=result.status_code,
                        headers={'Content-Type': result.headers.get('content-type', 'application/json')})


@app.api_route('/{path:path}', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
async def proxy(path: str, request: Request):
    body = await request.body()
    if len(body) > 16 * 1024 * 1024: raise HTTPException(413, 'UC request exceeds 16 MiB')
    return await asyncio.to_thread(forward, request.method, path, str(request.url.query), body,
                                  request.headers.get('content-type', 'application/json'), request.headers.get('authorization', ''))


if __name__ == '__main__':
    import sys
    if len(sys.argv) == 2 and sys.argv[1] in ('status', 'sync'):
        import json
        action = sys.argv[1]
        with httpx.Client(timeout=120) as client:
            r = client.request('GET' if action == 'status' else 'POST', 'http://127.0.0.1:8080/registry/' + action,
                               headers={'X-Runner-Token': os.environ['RUNNER_TOKEN']})
            r.raise_for_status(); print(json.dumps(r.json(), indent=2))
    else:
        import uvicorn
        uvicorn.run(app, host='0.0.0.0', port=8080)
