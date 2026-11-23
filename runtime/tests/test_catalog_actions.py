from unittest.mock import Mock
from urllib.error import HTTPError

import pytest
from fastapi.testclient import TestClient

from catalog_actions import drop_tables
from catalog_functions import create_payload, definition
import runner


def batch():
    return {'names':['sales.a.one','sales.b.two'],'confirmation':'DELETE',
            'confirmed_names':['sales.a.one','sales.b.two']}


def test_drop_is_quoted_and_uses_each_tables_namespace():
    sql=Mock();lookup=Mock();result=drop_tables(batch(),lookup,sql)
    assert result['deleted']==2
    assert sql.call_args_list[0].args==('DROP TABLE `sales`.`a`.`one`',)
    assert sql.call_args_list[1].kwargs=={'catalog':'sales','schema':'b'}


@pytest.mark.parametrize('change',[
    {'confirmation':'yes'},{'confirmed_names':['sales.b.two','sales.a.one']},
    {'names':['sales.a.one; DROP SCHEMA sales']},{'names':[]},{'names':['a.b.c']*101}])
def test_invalid_or_unconfirmed_drop_never_executes_sql(change):
    data={**batch(),**change};sql=Mock();lookup=Mock()
    with pytest.raises(ValueError):drop_tables(data,lookup,sql)
    sql.assert_not_called();lookup.assert_not_called()


def test_drop_stops_on_unknown_result_and_reports_not_attempted():
    sql=Mock(side_effect=RuntimeError('R2 registry pending'))
    result=drop_tables(batch(),Mock(),sql)
    assert [r['status'] for r in result['results']]==['FAILED','NOT_ATTEMPTED']
    assert 'may already' in result['results'][0]['note'] and sql.call_count==1


def test_already_missing_table_is_reported_without_drop():
    sql=Mock();lookup=Mock(side_effect=HTTPError('',404,'missing',{},None))
    result=drop_tables(batch(),lookup,sql)
    assert all(r['status']=='MISSING' for r in result['results'])
    sql.assert_not_called()


def test_delete_endpoint_requires_runner_auth(monkeypatch):
    monkeypatch.setenv('RUNNER_TOKEN','fixture-token');client=TestClient(runner.app)
    assert client.post('/tables/delete',json=batch()).status_code==401


def test_simple_python_function_builds_native_uc_request_without_execution():
    f=create_payload({'name':'increase','catalog_name':'sales','schema_name':'a','language':'PYTHON',
        'parameters':[{'name':'x','type':'INT'}],'return_type':'INT','body':'raise RuntimeError("never run")'})['function_info']
    assert f['routine_body']=='EXTERNAL' and f['external_language']=='PYTHON'
    assert f['input_params']['parameters'][0]['position']==0
    assert create_payload({'function_info':{**f,'function_id':'generated','created_at':123}})=={'function_info':f}


def test_complex_native_definition_preserves_parameters_and_return_type():
    f=create_payload({'name':'f','catalog_name':'c','schema_name':'s','language':'SQL',
        'parameters':[],'return_type':'INT','body':'1'})['function_info']
    f['data_type']='DECIMAL';f['full_data_type']='DECIMAL(10,2)'
    assert create_payload({'function_info':f})['function_info']['full_data_type']=='DECIMAL(10,2)'


@pytest.mark.parametrize('params',[[{'name':'x','type':'invalid'}],[{'name':'x','type':'INT'},{'name':'x','type':'INT'}]])
def test_invalid_function_parameter_definition_is_rejected(params):
    with pytest.raises(ValueError):create_payload({'name':'f','catalog_name':'c','schema_name':'s',
        'parameters':params,'body':'return 1'})
