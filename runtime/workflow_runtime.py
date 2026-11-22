"""Bounded workflow control flow with typed references, no Python eval."""
import ast,copy,operator,re,time,uuid,json
from graphlib import TopologicalSorter
from config import RUNTIME,identifier,timezone_name
from run_store import atomic_json,redact,upsert
DIRECTORY=RUNTIME/'workflows'

def expression(text,ctx):
    text=str(text).strip()
    if text.startswith('{{') and text.endswith('}}'):text=text[2:-2].strip()
    if len(text)>4000:raise ValueError('Expression is too long')
    comparisons={ast.Eq:operator.eq,ast.NotEq:operator.ne,ast.Lt:operator.lt,ast.LtE:operator.le,ast.Gt:operator.gt,ast.GtE:operator.ge,ast.In:lambda a,b:a in b,ast.NotIn:lambda a,b:a not in b}
    def visit(n):
        if isinstance(n,ast.Constant):return n.value
        if isinstance(n,ast.Name):
            if n.id in ('true','false','null'):return {'true':True,'false':False,'null':None}[n.id]
            if n.id not in ctx:raise ValueError('Unknown expression name: '+n.id)
            return ctx[n.id]
        if isinstance(n,ast.Attribute):
            v=visit(n.value)
            if not isinstance(v,dict) or n.attr.startswith('_'):raise ValueError('Only JSON object fields are supported')
            return v[n.attr]
        if isinstance(n,ast.Subscript):return visit(n.value)[visit(n.slice)]
        if isinstance(n,(ast.List,ast.Tuple)):return [visit(v) for v in n.elts]
        if isinstance(n,ast.Dict):return {visit(k):visit(v) for k,v in zip(n.keys,n.values)}
        if isinstance(n,ast.UnaryOp) and isinstance(n.op,ast.Not):return not visit(n.operand)
        if isinstance(n,ast.UnaryOp) and isinstance(n.op,ast.USub):return -visit(n.operand)
        if isinstance(n,ast.BoolOp):return all(visit(v) for v in n.values) if isinstance(n.op,ast.And) else any(visit(v) for v in n.values)
        if isinstance(n,ast.Compare):
            left=visit(n.left)
            for op,right_node in zip(n.ops,n.comparators):
                right=visit(right_node)
                if type(op) not in comparisons or not comparisons[type(op)](left,right):return False
                left=right
            return True
        if isinstance(n,ast.BinOp) and type(n.op) in (ast.Add,ast.Sub,ast.Mult,ast.Div,ast.Mod):
            a,b=visit(n.left),visit(n.right)
            if not isinstance(a,(int,float)) or not isinstance(b,(int,float)):raise ValueError('Arithmetic supports numbers only')
            return {ast.Add:operator.add,ast.Sub:operator.sub,ast.Mult:operator.mul,ast.Div:operator.truediv,ast.Mod:operator.mod}[type(n.op)](a,b)
        if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='len' and len(n.args)==1:return len(visit(n.args[0]))
        raise ValueError('Unsupported expression; use JSON fields, comparisons, boolean operators or len()')
    return visit(ast.parse(text,mode='eval').body)

def render(value,ctx):
    if isinstance(value,dict):return {k:render(v,ctx) for k,v in value.items()}
    if isinstance(value,list):return [render(v,ctx) for v in value]
    if not isinstance(value,str):return value
    if re.fullmatch(r'\s*\{\{.*?\}\}\s*',value,re.S):return expression(value,ctx)
    return re.sub(r'\{\{(.*?)\}\}',lambda m:str(expression(m[1],ctx)),value)

def validate(flow):
    nodes=flow.get('nodes',[])
    if not 1<=len(nodes)<=100:raise ValueError('A flow needs 1..100 tasks')
    lookup={identifier(n['id']):n for n in nodes}
    if len(lookup)!=len(nodes):raise ValueError('Duplicate task ID')
    for n in nodes:
        parent=n.get('parent','')
        if parent and (parent not in lookup or lookup[parent]['kind'] not in ('condition','loop')):raise ValueError('Parent must be a condition or loop')
        seen={n['id']};p=parent
        while p:
            if p in seen:raise ValueError('Workflow contains a parent cycle')
            seen.add(p);p=lookup[p].get('parent','')
            if len(seen)>6:raise ValueError('At most 5 nested blocks are supported')
        for dep in n.get('dependsOn',[]):
            if dep not in lookup or lookup[dep].get('parent','')!=parent or lookup[dep].get('branch','then')!=n.get('branch','then') or dep==n['id']:raise ValueError('Invalid dependency: dependencies must refer to a sibling in the same branch')
        if n.get('runWhen','success') not in ('success','failure','always'):raise ValueError('Invalid run condition')
        if n['kind']=='loop' and not 1<=int(n.get('maxIterations',100))<=1000:raise ValueError('Loop limit must be 1..1000')
    for parent in ['',*lookup]:
        group={n['id']:n.get('dependsOn',[]) for n in nodes if n.get('parent','')==parent}
        try:list(TopologicalSorter(group).static_order())
        except Exception as e:raise ValueError('Workflow contains a cycle') from e

def workflow_file(execution_id):
    if not re.fullmatch('[A-Za-z0-9_-]{1,128}',execution_id):raise ValueError('Invalid execution ID')
    return DIRECTORY/execution_id/'execution.json'

def execute_workflow(flow,execution_id,inputs,execute_task):
    validate(flow);path=workflow_file(execution_id)
    ctx={'inputs':copy.deepcopy(flow.get('inputs',{})),'vars':copy.deepcopy(flow.get('variables',{})),'outputs':{},'item':None,'loop':{}}
    ctx['inputs'].update(inputs or {})
    data={'id':execution_id,'name':flow['id'],'flow_id':flow['id'],'kind':'workflow','status':'RUNNING','started':time.time(),'timezone':timezone_name(),'types':sorted({n['kind'] for n in flow['nodes']}),'tasks':[],'inputs':redact(ctx['inputs']),'variables':redact(ctx['vars']),'definition':flow}
    def save():
        atomic_json(path,redact(data));upsert('workflow',{k:v for k,v in data.items() if k not in ('tasks','definition')})
    save();nodes=flow['nodes'];budget=[0];deadline=time.monotonic()+int(flow.get('timeout',86400))
    def group(parent='',branch=None,prefix='',context=None):
        context=context or ctx
        siblings=[n for n in nodes if n.get('parent','')==parent and (branch is None or n.get('branch','then')==branch)]
        lookup={n['id']:n for n in siblings};states={};handled=set()
        for task_id in TopologicalSorter({n['id']:n.get('dependsOn',[]) for n in siblings}).static_order():
            n=lookup[task_id];deps=n.get('dependsOn',[]);when=n.get('runWhen','success')
            run=any(states.get(d)=='FAILED' for d in deps) if when=='failure' else all(states.get(d)=='SUCCESS' for d in deps) if when=='success' else True
            item={'id':prefix+task_id,'task_id':task_id,'name':n.get('name',task_id),'kind':n['kind'],'status':'RUNNING' if run else 'SKIPPED','started':time.time(),'run_ids':[]}
            data['tasks'].append(item);save()
            if not run:states[task_id]='SKIPPED';continue
            budget[0]+=1
            if budget[0]>10000 or time.monotonic()>deadline:raise TimeoutError('Workflow exceeded its task or time budget')
            try:
                if n['kind']=='variable':
                    out=render(n.get('values',{}),context)
                    if not isinstance(out,dict):raise ValueError('Variable assignments must be a JSON object')
                    context['vars'].update(out)
                elif n['kind']=='condition':
                    decision=bool(expression(n.get('condition','true'),context));item['condition']=decision;save()
                    if not group(task_id,'then' if decision else 'else',prefix+task_id+'/',context):raise RuntimeError('Condition branch failed')
                    out={'result':decision}
                elif n['kind']=='loop':
                    values=render(n.get('values',[]),context)
                    if not isinstance(values,list):raise ValueError('Loop values must resolve to a JSON array')
                    if len(values)>int(n.get('maxIterations',100)):raise ValueError('Loop exceeds maxIterations')
                    collected=[]
                    for i,v in enumerate(values):
                        child={**context,'vars':copy.deepcopy(context['vars']),'outputs':copy.deepcopy(context['outputs']),'item':v,'loop':{'index':i,'value':v}}
                        if not group(task_id,None,prefix+task_id+'['+str(i)+']/',child):raise RuntimeError('Loop iteration failed: '+str(i))
                        collected.append({k:v for k,v in child['outputs'].items() if k not in context['outputs']})
                        if len(json.dumps(collected,default=str))>10*1024*1024:raise ValueError('Loop output exceeds 10 MB; return a table/file reference instead of the data')
                    out={'items':collected,'count':len(values)}
                else:
                    payload=render({k:v for k,v in n.items() if k in ('kind','path','command','sql','parameters','select','catalog','schema','timeout')},context)
                    payload['timeout']=min(int(payload.get('timeout',7200)),max(1,int(deadline-time.monotonic())))
                    payload.update(name=n.get('name',task_id),workflow_execution_id=execution_id,flow_id=flow['id'],task_id=task_id,task_path=item['id'])
                    for attempt in range(1,int(n.get('attempts',1))+1):
                        run_id=uuid.uuid4().hex;item['run_ids'].append(run_id);save();result=execute_task({**payload,'attempt':attempt},run_id)
                        if result['status']=='SUCCESS':break
                    if result['status']!='SUCCESS':raise RuntimeError(result.get('error','Task failed'))
                    out=result.get('outputs',{})
                if len(json.dumps(out,default=str))>10*1024*1024:raise ValueError('Task output exceeds 10 MB; return a table/file reference instead of the data')
                item.update(status='SUCCESS',outputs=redact(out));context['outputs'][task_id]=out;states[task_id]='SUCCESS'
                if when=='failure':handled.update(d for d in deps if states.get(d)=='FAILED')
            except Exception as e:item.update(status='FAILED',error=str(e));states[task_id]='FAILED';context['outputs'][task_id]={'error':str(e),'status':'FAILED'}
            item.update(ended=time.time(),duration=round(time.time()-item['started'],3));save()
        return not any(status=='FAILED' and task_id not in handled for task_id,status in states.items())
    try:data['status']='SUCCESS' if group() else 'FAILED'
    except Exception as e:data.update(status='FAILED',error=str(e))
    data.update(ended=time.time(),outputs=redact(ctx['outputs']),variables=redact(ctx['vars']));data['duration']=round(data['ended']-data['started'],3);save();return data
