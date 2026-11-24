from urllib.error import HTTPError
import pytest
from view_actions import create_view,drop_views


def test_create_view_validates_single_query_and_uses_native_ddl():
    calls=[]
    def lookup(method,path):
        if calls:return {'table_type':'VIEW','table_id':'fixture-id'}
        raise HTTPError('',404,'missing',{},None)
    def execute(sql,**kwargs):calls.append((sql,kwargs))
    result=create_view({'name':'cat.stg.v','sql':'WITH t AS (SELECT 1 AS id) SELECT * FROM t','comment':"Owner's view"},lookup,execute)
    assert result['table_type']=='VIEW' and calls[0][1]=={'catalog':'cat','schema':'stg'}
    assert calls[0][0].startswith('CREATE VIEW `cat`.`stg`.`v` COMMENT ')
    with pytest.raises(ValueError):create_view({'name':'cat.stg.v','sql':'SELECT 1; DROP TABLE cat.stg.t'},lookup,execute)
    for invalid in ('','-- comment only','/* comment only */','DROP TABLE cat.stg.t'):
        with pytest.raises(ValueError):create_view({'name':'cat.stg.v','sql':invalid},lookup,execute)


def test_drop_views_cannot_delete_tables_and_stops_on_failure():
    executed=[]
    result=drop_views({'names':['c.s.t','c.s.v'],'confirmed_names':['c.s.t','c.s.v'],'confirmation':'DELETE'},
        lambda *args:{'table_type':'MANAGED'},lambda *args,**kw:executed.append(args))
    assert not executed and [r['status'] for r in result['results']]==['FAILED','NOT_ATTEMPTED']
