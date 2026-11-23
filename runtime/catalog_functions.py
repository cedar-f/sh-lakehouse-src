"""Portable UC function definitions. Registration never executes user code."""
import json

from config import identifier

FUNCTION_FIELDS = ('name', 'catalog_name', 'schema_name', 'input_params', 'data_type',
    'full_data_type', 'return_params', 'routine_body', 'routine_definition', 'routine_dependencies',
    'parameter_style', 'is_deterministic', 'sql_data_access', 'is_null_call', 'security_type',
    'specific_name', 'comment', 'properties', 'external_language')
REQUIRED = ('name', 'catalog_name', 'schema_name', 'input_params', 'data_type', 'full_data_type',
    'routine_body', 'routine_definition', 'parameter_style', 'is_deterministic', 'sql_data_access',
    'is_null_call', 'security_type', 'specific_name')
PARAM_FIELDS = ('name', 'type_text', 'type_name', 'type_json', 'position', 'type_precision',
    'type_scale', 'type_interval_type', 'parameter_mode', 'parameter_type', 'parameter_default', 'comment')
TYPES = {'INT': 'integer', 'LONG': 'long', 'SHORT': 'short', 'BYTE': 'byte', 'STRING': 'string',
         'BOOLEAN': 'boolean', 'FLOAT': 'float', 'DOUBLE': 'double', 'DATE': 'date',
         'TIMESTAMP': 'timestamp', 'BINARY': 'binary'}


def definition(record):
    value = {key: record[key] for key in FUNCTION_FIELDS if record.get(key) is not None}
    for group in ('input_params', 'return_params'):
        if group in value:
            params = value[group]
            if not isinstance(params, dict) or not isinstance(params.get('parameters', []), list):
                raise ValueError('Invalid function parameters')
            if not all(isinstance(p, dict) for p in params.get('parameters', [])):
                raise ValueError('Invalid function parameter')
            value[group] = {'parameters': [{k: p[k] for k in PARAM_FIELDS if p.get(k) is not None}
                                          for p in params.get('parameters', [])]}
    return value


def validate_function(value):
    if any(key not in value for key in REQUIRED):
        raise ValueError('Function definition is missing required fields')
    for key in ('name', 'catalog_name', 'schema_name'):identifier(value[key])
    if value['routine_body'] not in ('SQL', 'EXTERNAL'):
        raise ValueError('Function routine_body must be SQL or EXTERNAL')
    if not isinstance(value['routine_definition'], str) or not value['routine_definition'].strip():
        raise ValueError('Function body cannot be empty')
    if len(value['routine_definition'].encode()) > 1024*1024:
        raise ValueError('Function body exceeds 1 MiB')
    for key in ('is_deterministic', 'is_null_call'):
        if not isinstance(value[key], bool):raise ValueError('Invalid function boolean: '+key)
    for key in ('data_type', 'full_data_type', 'specific_name'):
        if not isinstance(value[key], str):raise ValueError('Invalid function field: '+key)
    if not value['data_type'] or not value['full_data_type']:
        raise ValueError('Function return type is required')
    if value['parameter_style'] != 'S' or value['security_type'] != 'DEFINER':
        raise ValueError('Unsupported function parameter style or security type')
    if value['sql_data_access'] not in ('NO_SQL', 'CONTAINS_SQL', 'READS_SQL_DATA'):
        raise ValueError('Invalid function SQL data access')
    if value['routine_body']=='EXTERNAL' and (not value.get('external_language') or value['sql_data_access']!='NO_SQL' or value.get('return_params')):
        raise ValueError('External functions require external_language, NO_SQL and no return_params')
    for group in ('input_params', 'return_params'):
        if group not in value:continue
        params=value[group]
        if not isinstance(params, dict) or not isinstance(params.get('parameters'), list):
            raise ValueError('Invalid function parameters')
        seen=set()
        for index, p in enumerate(params['parameters']):
            if not isinstance(p, dict):raise ValueError('Invalid function parameter')
            identifier(p.get('name'))
            if p['name'] in seen or type(p.get('position')) is not int or p['position']!=index:
                raise ValueError('Function parameters require unique names and positions starting at zero')
            seen.add(p['name'])
            for key in ('type_text','type_name','type_json'):
                if not isinstance(p.get(key),str) or not p[key]:raise ValueError('Missing parameter '+key)
            json.loads(p['type_json'])
    # UC function properties are a JSON-encoded string, unlike catalog properties.
    if 'properties' in value:
        if not isinstance(value['properties'],str) or not isinstance(json.loads(value['properties']),dict):
            raise ValueError('Function properties must be a JSON object encoded as a string')
    return value


def create_payload(data):
    if 'function_info' in data:
        return {'function_info': validate_function(definition(data['function_info']))}
    language=data.get('language','PYTHON')
    if language not in ('PYTHON','SQL'):raise ValueError('Choose PYTHON or SQL')
    params=data.get('parameters',[])
    if not isinstance(params,list):raise ValueError('Parameters must be a JSON array')
    converted=[]
    for index,p in enumerate(params):
        if not isinstance(p,dict):raise ValueError('Each parameter must be an object')
        kind=p.get('type','').upper()
        if kind not in TYPES:raise ValueError('Use a supported scalar type or native function_info JSON for complex types')
        converted.append({'name':identifier(p.get('name')),'type_name':kind,'type_text':kind.lower(),
            'type_json':json.dumps({'name':p['name'],'type':TYPES[kind],'nullable':True,'metadata':{}}),
            'position':index,'parameter_mode':'IN','parameter_type':'PARAM',
            **({'comment':p['comment']} if p.get('comment') else {})})
    result=data.get('return_type','STRING').upper()
    if result not in TYPES:raise ValueError('Unsupported return type; use native function_info JSON for complex types')
    value={k:identifier(data.get(k)) for k in ('name','catalog_name','schema_name')}
    value.update(input_params={'parameters':converted},data_type=result,full_data_type=result,
        routine_body='EXTERNAL' if language=='PYTHON' else 'SQL',routine_definition=data.get('body',''),
        parameter_style='S',is_deterministic=data.get('is_deterministic',False),
        sql_data_access='NO_SQL' if language=='PYTHON' else 'READS_SQL_DATA',is_null_call=True,
        security_type='DEFINER',specific_name=value['name'],comment=data.get('comment',''))
    if language=='PYTHON':value['external_language']='PYTHON'
    return {'function_info':validate_function(value)}
