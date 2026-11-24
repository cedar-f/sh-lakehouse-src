"""SQL view operations through the native Spark/UC connector."""
from urllib.error import HTTPError
from urllib.parse import quote

from catalog_actions import full_name
from sql_functions import split_statements, tokens, word


def create_view(payload,lookup,execute):
    name=full_name(payload.get('name'))
    query=payload.get('sql','')
    if not isinstance(query,str) or len(query.encode())>1024*1024:raise ValueError('View query must be at most 1 MiB')
    statements=split_statements(query)
    first=tokens(statements[0]) if len(statements)==1 else []
    if not first or not any(word(first[0],w) for w in ('SELECT','WITH')):
        raise ValueError('Enter one SELECT or WITH query for the view')
    try:lookup('GET','tables/'+quote(name,safe=''))
    except HTTPError as error:
        if error.code!=404:raise
    else:raise ValueError('This name already exists. Use a new view name; native UC replacement is not supported.')
    catalog,schema,_=name.split('.')
    comment=payload.get('comment','')
    if not isinstance(comment,str) or len(comment)>20000:raise ValueError('Invalid view comment')
    annotation=" COMMENT '"+comment.replace('\\','\\\\').replace("'","\\'")+"'" if comment else ''
    sql='CREATE VIEW '+'.'.join('`'+p+'`' for p in name.split('.'))+annotation+' AS '+statements[0]
    execute(sql,catalog=catalog,schema=schema)
    return lookup('GET','tables/'+quote(name,safe=''))


def drop_views(payload,lookup,execute):
    names=payload.get('names')
    if not isinstance(names,list) or not 1<=len(names)<=100:raise ValueError('Select 1..100 views')
    names=[full_name(n) for n in names]
    if len(set(names))!=len(names) or payload.get('confirmation')!='DELETE' or payload.get('confirmed_names')!=names:
        raise ValueError('Confirm DELETE and the exact selected view list')
    results=[];stopped=False
    for name in names:
        if stopped:results.append({'name':name,'status':'NOT_ATTEMPTED'});continue
        try:
            value=lookup('GET','tables/'+quote(name,safe=''))
            if value.get('table_type')!='VIEW':raise ValueError('Selected object is not a SQL view; refusing to drop it')
            catalog,schema,_=name.split('.')
            execute('DROP VIEW '+'.'.join('`'+p+'`' for p in name.split('.')),catalog=catalog,schema=schema)
            results.append({'name':name,'status':'DELETED'})
        except HTTPError as error:
            if error.code==404:results.append({'name':name,'status':'MISSING'})
            else:results.append({'name':name,'status':'FAILED','error':str(error)});stopped=True
        except Exception as error:results.append({'name':name,'status':'FAILED','error':str(error)});stopped=True
    return {'results':results,'deleted':sum(r['status']=='DELETED' for r in results),'stopped':stopped}
