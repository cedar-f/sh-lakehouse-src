import copy
from urllib.error import HTTPError

import pytest

from sql_functions import SQLFunctions, parse_create, split_statements


CREATE="CREATE FUNCTION cat.tools.add_one(value INT) RETURNS INT COMMENT 'Increment' RETURN value + 1"


class UC:
    def __init__(self):self.data={};self.calls=[]
    def request(self,method,path,data=None,params=None):
        self.calls.append((method,path,data))
        if path.startswith('schemas/'):return {}
        if path=='functions' and method=='GET':return {'functions':list(self.data.values())}
        if path=='functions' and method=='POST':
            value=copy.deepcopy(data['function_info']);name='.'.join(value[k] for k in ('catalog_name','schema_name','name'))
            self.data[name]=value;return value
        name=path.removeprefix('functions/')
        if name not in self.data:raise HTTPError('',404,'missing',{},None)
        if method=='GET':return copy.deepcopy(self.data[name])
        if method=='DELETE':return self.data.pop(name)
        raise AssertionError((method,path))


def engine(uc=None):
    uc=uc or UC();native=[]
    def execute(sql):native.append(sql);return {'query':sql}
    value=SQLFunctions(execute,lambda cols,rows:{'columns':cols,'rows':rows},request=uc.request)
    return value,uc,native


def test_parse_decimal_empty_params_comments_and_native_metadata():
    value,replace,exists=parse_create("CREATE OR REPLACE FUNCTION `cat`.`tools`.`f`(value DECIMAL(10,2)) RETURNS DECIMAL(12,2) LANGUAGE SQL DETERMINISTIC COMMENT 'don''t lose comments' RETURN value * 2")
    assert replace and not exists
    assert value['comment']=="don't lose comments" and value['full_data_type']=='DECIMAL(12,2)'
    assert value['input_params']['parameters'][0]['type_scale']==2
    assert parse_create("CREATE FUNCTION c.s.f() RETURNS STRING RETURN 'x'")[0]['input_params']=={'parameters':[]}


@pytest.mark.parametrize('sql',[
    'CREATE FUNCTION f(x INT) RETURNS INT RETURN x',
    'CREATE FUNCTION c.s.f(x INT) RETURNS TABLE RETURN SELECT x',
    'CREATE FUNCTION c.s.f(x INT DEFAULT 1) RETURNS INT RETURN x',
    'CREATE FUNCTION c.s.f(x INT,) RETURNS INT RETURN x',
    'CREATE FUNCTION c.s.f(x INT,x INT) RETURNS INT RETURN x',
    'CREATE FUNCTION c.s.f(x INT) RETURNS INT RETURN (SELECT 1)',
    'CREATE OR REPLACE FUNCTION IF NOT EXISTS c.s.f() RETURNS INT RETURN 1',
    'CREATE FUNCTION c.s.f() RETURNS INT DETERMINISTIC NOT DETERMINISTIC RETURN 1',
])
def test_unsupported_ddl_fails_before_persistence(sql):
    value,uc,_=engine()
    with pytest.raises(ValueError):value.run(sql)
    assert not any(call[0]=='POST' for call in uc.calls)


def test_splitter_does_not_split_inside_strings_quoted_names_or_nested_comments():
    assert len(split_statements("SELECT ';'; /* outer /* nested ; */ comment */ SELECT 'a'';b' -- ;\n;"))==2
    with pytest.raises(ValueError):split_statements('/* incomplete')


def test_create_validates_in_spark_before_uc_then_query_binds_full_name():
    value,uc,native=engine();value.run(CREATE)
    assert 'TEMPORARY FUNCTION' in native[0]
    assert uc.data['cat.tools.add_one']['routine_body']=='SQL'
    result=value.run("SELECT cat.tools.add_one(10), 'cat.tools.add_one(99)' -- cat.tools.add_one(3)")
    assert '`_lh_uc_' in result['query']
    assert "'cat.tools.add_one(99)'" in result['query'] and '-- cat.tools.add_one(3)' in result['query']


def test_invalid_spark_expression_is_never_persisted():
    uc=UC()
    def invalid(sql):raise RuntimeError('unresolved column')
    value=SQLFunctions(invalid,lambda *a:None,request=uc.request)
    with pytest.raises(RuntimeError):value.run(CREATE)
    assert not uc.data


def test_duplicate_if_not_exists_and_drop_refresh_in_same_session():
    value,uc,native=engine();value.run(CREATE)
    with pytest.raises(ValueError,match='already exists'):value.run(CREATE)
    count=len(native)
    value.run(CREATE.replace('CREATE FUNCTION','CREATE FUNCTION IF NOT EXISTS'))
    assert len(native)==count
    value.run('DROP FUNCTION cat.tools.add_one')
    with pytest.raises(ValueError,match='not found'):value.run('SELECT cat.tools.add_one(1)')
    value.run('DROP FUNCTION IF EXISTS cat.tools.add_one')


def test_function_updates_and_deletions_are_seen_by_existing_session():
    value,uc,native=engine();value.run(CREATE)
    value.run('SELECT cat.tools.add_one(1)')
    uc.data['cat.tools.add_one']['routine_definition']='value + 5'
    value.run('SELECT cat.tools.add_one(1)')
    assert any(sql.endswith('RETURN value + 5') for sql in native)


def test_restart_new_engine_loads_uc_without_recreating_definition():
    first,uc,_=engine();first.run(CREATE)
    second,_,native=engine(uc);second.run('SELECT cat.tools.add_one(9)')
    assert len(native)==2 and len(uc.data)==1


def test_dependencies_are_bound_and_cycles_rejected():
    value,uc,native=engine();value.run(CREATE)
    value.run('CREATE FUNCTION cat.tools.twice(x INT) RETURNS INT RETURN cat.tools.add_one(x) * 2')
    value.run('SELECT cat.tools.twice(5)')
    assert native[-2].count('_lh_uc_')==2
    uc.data['cat.tools.add_one']['routine_definition']='cat.tools.twice(value)'
    with pytest.raises(ValueError,match='Cyclic'):value.run('SELECT cat.tools.twice(1)')


def test_describe_show_and_native_builtin_passthrough():
    value,uc,native=engine();value.run(CREATE)
    assert value.run('SHOW FUNCTIONS IN cat.tools')['rows']==[['cat.tools.add_one']]
    assert value.run("SHOW USER FUNCTIONS IN cat.tools LIKE 'add*'")['rows']==[['cat.tools.add_one']]
    assert ['Body','value + 1'] in value.run('DESCRIBE FUNCTION EXTENDED cat.tools.add_one')['rows']
    for sql in ('DESCRIBE FUNCTION abs','SHOW FUNCTIONS IN default','DROP FUNCTION IF EXISTS local_fn','SELECT abs(-1)'):
        assert value.run(sql)=={'query':sql}


def test_python_registration_is_not_executed_as_sql():
    value,uc,_=engine();value.run(CREATE);uc.data['cat.tools.add_one']['routine_body']='EXTERNAL'
    with pytest.raises(ValueError,match='Python/external'):value.run('SELECT cat.tools.add_one(1)')


def test_table_targets_and_column_lists_are_not_resolved_as_functions():
    value,uc,native=engine();value.run(CREATE)
    for sql in ('CREATE TABLE cat.tools.t(id INT) USING DELTA',
                'CREATE TABLE IF NOT EXISTS cat.tools.t(id INT) USING DELTA',
                'CREATE VIEW cat.tools.v(id) AS SELECT 1',
                'INSERT INTO cat.tools.t(id) VALUES (1)',
                'INSERT OVERWRITE TABLE cat.tools.t(id) SELECT 1'):
        assert value.run(sql)=={'query':sql}
    result=value.run('INSERT INTO cat.tools.t(id) SELECT cat.tools.add_one(1)')
    assert 'cat.tools.t(id)' in result['query'] and '`_lh_uc_' in result['query']
    assert not any(path=='functions/cat.tools.t' for method,path,_ in uc.calls)


def test_scalar_from_keyword_is_supported_without_permitting_table_queries():
    value=parse_create('CREATE FUNCTION cat.tools.day_of(v DATE) RETURNS INT RETURN extract(DAY FROM v)')[0]
    assert value['routine_definition']=='extract(DAY FROM v)'
