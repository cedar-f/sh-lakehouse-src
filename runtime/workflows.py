"""Compile a validated visual DAG into an executable Kestra flow."""
import json
from graphlib import TopologicalSorter, CycleError
from croniter import croniter
from config import identifier, safe_path, timezone_name
from workflow_runtime import validate

def compile_flow(flow):
    flow_id=identifier(flow['id'])
    validate(flow)
    nodes=flow['nodes']
    graph={n['id']:n.get('dependsOn',[]) for n in nodes}
    for key in ('inputs','variables'):
        if not isinstance(flow.get(key,{}),dict):raise ValueError(key+' must be a JSON object')
    if not 1<=int(flow.get('timeout',86400))<=86400:raise ValueError('Workflow timeout must be 1..86400 seconds')
    advanced=bool(flow.get('inputs') or flow.get('variables') or any(n['kind'] in ('condition','loop','variable') or n.get('parent') or n.get('runWhen','success')!='success' or '{{' in json.dumps(n) for n in nodes))
    tasks=[]
    for node in nodes:
        kind=node['kind']
        if kind in ('condition','loop','variable'):
            if kind=='condition' and not isinstance(node.get('condition'),str):raise ValueError('Condition must be an expression')
            if kind=='variable' and not isinstance(node.get('values',{}),dict):raise ValueError('Variable assignments must be an object')
            continue
        if kind not in ('notebook','dbt','sql'): raise ValueError('Unsupported task kind')
        if not isinstance(node.get('parameters',{}),dict):raise ValueError('Parameters must be a JSON object')
        payload={'kind':kind,'parameters':node.get('parameters',{})}
        if kind=='notebook':
            payload['path']=node['path']; safe_path(node['path'],'.ipynb')
        if kind=='dbt':
            payload.update(path=node.get('path','dbt'),command=node.get('command','build'),
                select=node.get('select',''),catalog=node.get('catalog',''),schema=node.get('schema',''))
            safe_path(payload['path'])
            if payload['command'] not in ('build','run','test','seed','snapshot','docs','deps','debug'):
                raise ValueError('Invalid dbt command')
        if kind=='sql': payload['sql']=node['sql']
        seconds=int(node.get('timeout',7200)); attempts=int(node.get('attempts',1))
        if not 1<=seconds<=86400 or not 1<=attempts<=10: raise ValueError('Invalid timeout/attempts')
        payload['timeout']=seconds
        # One synchronous request for each task. Runner writes durable run output before reply.
        task={'id':node['id'],'type':'io.kestra.plugin.core.http.Request',
            'uri':'http://runner:8765/run','method':'POST','contentType':'application/json',
            'headers':{'X-Runner-Token':'{{ envs.runner_token }}'},
            # Avoid interpreting Jinja-like text in SQL or notebook parameter values.
            'body':json.dumps({'payload_b64':__import__('base64').b64encode(json.dumps(payload).encode()).decode(),
                               'context':{'execution_id':'{{ execution.id }}','flow_id':'{{ flow.id }}','task_id':node['id']}}),
            'timeout':f'PT{seconds+120}S',
            'options':{'timeout':{'connectTimeout':'PT30S','readIdleTimeout':f'PT{seconds+90}S'}}}
        if attempts>1: task['retry']={'type':'constant','interval':'PT30S','maxAttempts':attempts}
        item={'task':task}
        if graph[node['id']]: item['dependsOn']=graph[node['id']]
        tasks.append(item)
    result={'id':flow_id,'namespace':'lakehouse.v3','description':flow.get('description','Lakehouse visual workflow'),
        'tasks':[{'id':'pipeline','type':'io.kestra.plugin.core.flow.Dag','tasks':tasks}]}
    if advanced:
        seconds=int(flow.get('timeout',86400))
        result['inputs']=[{'id':'parameters','type':'JSON','defaults':flow.get('inputs',{})}]
        result['tasks']=[{'id':'workflow','type':'io.kestra.plugin.core.http.Request',
            'uri':'http://runner:8765/workflow/execute','method':'POST','contentType':'application/json',
            'headers':{'X-Runner-Token':'{{ envs.runner_token }}'},
            'body':json.dumps({'flow_b64':__import__('base64').b64encode(json.dumps(flow).encode()).decode(),
                              'execution_id':'{{ execution.id }}','inputs_b64':'{{ inputs | toJson | base64encode }}'}),
            'timeout':f'PT{seconds+120}S','options':{'timeout':{'connectTimeout':'PT30S','readIdleTimeout':f'PT{seconds+90}S'}}}]
    cron=flow.get('cron','').strip()
    if cron:
        if not croniter.is_valid(cron): raise ValueError('Invalid cron expression')
        from zoneinfo import ZoneInfo
        tz=flow.get('timezone') or timezone_name(); ZoneInfo(tz)
        result['triggers']=[{'id':'schedule','type':'io.kestra.plugin.core.trigger.Schedule',
            'cron':cron,'timezone':tz,'disabled':not flow.get('scheduleEnabled',False)}]
    return result
