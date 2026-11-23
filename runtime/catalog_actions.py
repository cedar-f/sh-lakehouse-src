"""Bounded, confirmed table drops through Spark, never raw R2 object deletion."""
from urllib.parse import quote
from urllib.error import HTTPError

from config import identifier


def full_name(value):
    if not isinstance(value,str) or len(value.split('.'))!=3:
        raise ValueError('Expected catalog.schema.name')
    return '.'.join(identifier(part) for part in value.split('.'))


def drop_tables(payload, lookup, execute):
    names=payload.get('names')
    if not isinstance(names,list) or not 1<=len(names)<=100:
        raise ValueError('Select 1..100 tables')
    names=[full_name(n) for n in names]
    if len(set(names))!=len(names):raise ValueError('Duplicate table selection')
    if payload.get('confirmation')!='DELETE' or payload.get('confirmed_names')!=names:
        raise ValueError('Confirm DELETE and the exact selected table list')
    results=[];stopped=False
    for name in names:
        if stopped:
            results.append({'name':name,'status':'NOT_ATTEMPTED'});continue
        try:
            lookup('GET','tables/'+quote(name,safe=''))
            catalog,schema,_=name.split('.')
            sql='DROP TABLE '+'.'.join('`'+p+'`' for p in name.split('.'))
            execute(sql,catalog=catalog,schema=schema)
            results.append({'name':name,'status':'DELETED'})
        except HTTPError as error:
            if error.code==404:results.append({'name':name,'status':'MISSING'})
            else:
                results.append({'name':name,'status':'FAILED','error':str(error)});stopped=True
        except Exception as error:
            results.append({'name':name,'status':'FAILED','error':str(error),'note':'The drop may already have been applied. Refresh Catalog and check registry status before retrying.'});stopped=True
    return {'results':results,'deleted':sum(r['status']=='DELETED' for r in results),'stopped':stopped}
