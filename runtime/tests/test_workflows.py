import copy
import pytest
from workflows import compile_flow
from config import safe_path

def flow():
    return {'id':'daily','cron':'0 7 * * *','scheduleEnabled':False,'nodes':[
        {'id':'seed','kind':'dbt','path':'dbt','command':'seed','dependsOn':[]},
        {'id':'build','kind':'dbt','path':'dbt','command':'build','dependsOn':['seed'],'attempts':2}]}

def test_dependencies_and_schedule_are_preserved():
    result=compile_flow(flow())
    assert result['tasks'][0]['tasks'][1]['dependsOn']==['seed']
    assert result['tasks'][0]['tasks'][1]['task']['retry']['maxAttempts']==2
    assert result['triggers'][0]['disabled'] is True

def test_cycles_rejected_before_publishing():
    f=flow(); f['nodes'][0]['dependsOn']=['build']
    with pytest.raises(ValueError,match='cycle'): compile_flow(f)

def test_missing_dependency_rejected():
    f=flow(); f['nodes'][0]['dependsOn']=['unknown']
    with pytest.raises(ValueError,match='dependency'): compile_flow(f)

def test_shell_commands_cannot_be_injected_as_dbt_command():
    f=flow(); f['nodes'][0]['command']='build; rm -rf /'
    with pytest.raises(ValueError,match='dbt command'): compile_flow(f)

def test_notebook_cannot_escape_workspace():
    f={'id':'escape','nodes':[{'id':'n','kind':'notebook','path':'../../etc/passwd.ipynb'}]}
    with pytest.raises(ValueError,match='workspace'): compile_flow(f)

def test_invalid_cron_rejected():
    f=flow(); f['cron']='every day'
    with pytest.raises(ValueError,match='cron'): compile_flow(f)
