"""SQL scalar functions backed by UC, bound as session-local Spark SQL functions.

This gateway is deliberately not a Spark catalog plugin: only calls through
the notebook/runner SQL adapters are resolved. Strings/comments are never rewritten.
"""
from dataclasses import dataclass
import fnmatch
import hashlib
import json
import re
from urllib.error import HTTPError
from urllib.parse import quote

from config import identifier, uc
from catalog_functions import validate_function


@dataclass(frozen=True)
class Token:
    text: str
    start: int
    end: int
    kind: str


def tokens(sql):
    result=[];i=0
    while i<len(sql):
        start=i;c=sql[i]
        if c.isspace():i+=1;continue
        if sql.startswith('--',i):
            end=sql.find('\n',i+2);i=len(sql) if end<0 else end+1;continue
        if sql.startswith('/*',i):
            depth=1;i+=2
            while i<len(sql) and depth:
                if sql.startswith('/*',i):depth+=1;i+=2
                elif sql.startswith('*/',i):depth-=1;i+=2
                else:i+=1
            if depth:raise ValueError('Unclosed SQL comment')
            continue
        if c in "'\"`":
            delimiter=c;i+=1
            while i<len(sql):
                if sql[i]==delimiter:
                    if i+1<len(sql) and sql[i+1]==delimiter:i+=2;continue
                    i+=1;break
                if sql[i]=='\\' and delimiter!='`':i+=2
                else:i+=1
            else:raise ValueError('Unclosed SQL string or identifier')
            result.append(Token(sql[start:i],start,i,'identifier' if delimiter=='`' else 'string'));continue
        match=re.match(r'[A-Za-z_][A-Za-z0-9_]*',sql[i:])
        if match:i+=len(match[0]);kind='word'
        else:
            match=re.match(r'\d+',sql[i:])
            if match:i+=len(match[0]);kind='number'
            else:i+=1;kind='symbol'
        result.append(Token(sql[start:i],start,i,kind))
    return result


def split_statements(sql):
    result=[];start=0
    for token in tokens(sql):
        if token.text==';' and token.kind=='symbol':
            part=sql[start:token.start]
            if tokens(part):result.append(part)
            start=token.end
    if tokens(sql[start:]):result.append(sql[start:])
    if not result:raise ValueError('Enter a SQL statement')
    if len(result)>100:raise ValueError('At most 100 SQL statements per request')
    return result


def word(token,value):return token.kind=='word' and token.text.upper()==value


def ident(token):
    if token.kind not in ('word','identifier'):raise ValueError('Expected an identifier')
    return identifier(token.text[1:-1].replace('``','`') if token.kind=='identifier' else token.text)


def dotted(ts,index,count):
    values=[]
    for number in range(count):
        if index>=len(ts):raise ValueError('Expected a qualified name')
        values.append(ident(ts[index]));index+=1
        if number<count-1:
            if index>=len(ts) or ts[index].text!='.':raise ValueError('Use a fully qualified catalog.schema.function name')
            index+=1
    if index<len(ts) and ts[index].text=='.':raise ValueError('Too many name components')
    return '.'.join(values),index


TYPE_NAMES={'INTEGER':('INT','INT','integer'),'INT':('INT','INT','integer'),
    'BIGINT':('LONG','BIGINT','long'),'LONG':('LONG','BIGINT','long'),
    'SMALLINT':('SHORT','SMALLINT','short'),'SHORT':('SHORT','SMALLINT','short'),
    'TINYINT':('BYTE','TINYINT','byte'),'BYTE':('BYTE','TINYINT','byte'),
    **{k:(k,k,k.lower()) for k in ('STRING','BOOLEAN','FLOAT','DOUBLE','DATE','TIMESTAMP','BINARY')}}


def data_type(ts,index):
    if index>=len(ts):raise ValueError('A scalar SQL data type is required')
    name=ts[index].text.upper();index+=1
    if name in TYPE_NAMES:return (*TYPE_NAMES[name],index)
    if name in ('DECIMAL','NUMERIC'):
        if index+4>=len(ts) or [t.text for t in ts[index:index+5:2]]!=['(',',',')']:
            raise ValueError('Use DECIMAL(precision, scale)')
        a,b=ts[index+1],ts[index+3]
        if a.kind!='number' or b.kind!='number' or not 0<=int(b.text)<=int(a.text)<=38 or int(a.text)<1:
            raise ValueError('Invalid DECIMAL precision/scale')
        text=f'DECIMAL({int(a.text)},{int(b.text)})'
        return 'DECIMAL',text,text.lower(),index+5
    raise ValueError('Supported scalar types: INT, BIGINT, SMALLINT, TINYINT, STRING, BOOLEAN, FLOAT, DOUBLE, DATE, TIMESTAMP, BINARY, DECIMAL(p,s)')


def type_text(text):
    ts=tokens(text);kind,sql,json_type,index=data_type(ts,0)
    if index!=len(ts):raise ValueError('Unsupported function data type')
    return kind,sql,json_type


def expression(body):
    statements=split_statements(body)
    if len(statements)!=1:raise ValueError('Function body must be one SQL scalar expression')
    ts=tokens(statements[0])
    if any(t.kind=='word' and t.text.upper() in ('SELECT','OVER') for t in ts):
        raise ValueError('This version supports scalar expressions, not table queries, aggregates or window functions')
    return statements[0].strip()


def parse_create(sql):
    ts=tokens(sql);i=1;replace=False;exists=False
    if not ts or not word(ts[0],'CREATE'):return None
    if i<len(ts) and word(ts[i],'OR'):
        if i+1>=len(ts) or not word(ts[i+1],'REPLACE'):return None
        replace=True;i+=2
    if i<len(ts) and word(ts[i],'TEMPORARY'):return None
    if i>=len(ts) or not word(ts[i],'FUNCTION'):return None
    i+=1
    if i<len(ts) and word(ts[i],'IF'):
        if i+2>=len(ts) or not word(ts[i+1],'NOT') or not word(ts[i+2],'EXISTS'):raise ValueError('Expected IF NOT EXISTS')
        exists=True;i+=3
    if replace and exists:raise ValueError('OR REPLACE cannot be combined with IF NOT EXISTS')
    full,i=dotted(ts,i,3);cat,sch,name=full.split('.')
    if i>=len(ts) or ts[i].text!='(':raise ValueError('Use CREATE FUNCTION c.s.f(parameters) RETURNS type RETURN expression')
    i+=1;params=[]
    while i<len(ts) and ts[i].text!=')':
        pname=ident(ts[i]);i+=1;kind,sql_type,json_type,i=data_type(ts,i)
        p={'name':pname,'type_name':kind,'type_text':sql_type,'type_json':json.dumps({'name':pname,'type':json_type,'nullable':True,'metadata':{}}),
           'position':len(params),'parameter_mode':'IN','parameter_type':'PARAM'}
        if kind=='DECIMAL':
            a,b=map(int,re.findall(r'\d+',sql_type));p.update(type_precision=a,type_scale=b)
        params.append(p)
        if i<len(ts) and ts[i].text==',':i+=1
        elif i>=len(ts) or ts[i].text!=')':raise ValueError('Parameter DEFAULT/COMMENT and complex types are not supported in SQL DDL yet')
        if i<len(ts) and ts[i].text==')' and ts[i-1].text==',':raise ValueError('Trailing parameter comma')
    if i>=len(ts):raise ValueError('Unclosed function parameters')
    i+=1
    if i>=len(ts) or not word(ts[i],'RETURNS'):raise ValueError('Explicit RETURNS scalar_type is required')
    kind,return_type,_,i=data_type(ts,i+1)
    comment='';deterministic=False;seen=set()
    while i<len(ts) and not word(ts[i],'RETURN'):
        key='DETERMINISTIC' if word(ts[i],'NOT') else ts[i].text.upper()
        if key in seen:raise ValueError('Duplicate function characteristic')
        seen.add(key)
        if word(ts[i],'LANGUAGE') and i+1<len(ts) and word(ts[i+1],'SQL'):i+=2
        elif word(ts[i],'COMMENT') and i+1<len(ts) and ts[i+1].kind=='string' and ts[i+1].text.startswith("'"):
            comment=ts[i+1].text[1:-1].replace("''", "'");i+=2
        elif word(ts[i],'DETERMINISTIC'):deterministic=True;i+=1
        elif word(ts[i],'NOT') and i+1<len(ts) and word(ts[i+1],'DETERMINISTIC'):i+=2
        else:raise ValueError('Supported characteristics: LANGUAGE SQL, COMMENT, [NOT] DETERMINISTIC')
    if i>=len(ts):raise ValueError('RETURN expression is required')
    body=expression(sql[ts[i].end:])
    value={'name':name,'catalog_name':cat,'schema_name':sch,'input_params':{'parameters':params},
        'data_type':kind,'full_data_type':return_type,'routine_body':'SQL','routine_definition':body,
        'parameter_style':'S','is_deterministic':deterministic,'sql_data_access':'CONTAINS_SQL',
        'is_null_call':True,'security_type':'DEFINER','specific_name':name,'comment':comment}
    return validate_function(value),replace,exists


class SQLFunctions:
    def __init__(self,execute,tabulate,request=uc,replace=None):
        self.native=execute;self.tabulate=tabulate;self.request=request;self.replace=replace
        self.loaded={};self.loading=[]

    def get(self,name,missing=False):
        try:return self.request('GET','functions/'+quote(name,safe=''))
        except HTTPError as error:
            if error.code==404:
                if missing:return None
                raise ValueError('UC function not found: '+name) from error
            raise

    def bind(self,name,record=None):
        if name in self.loaded:return self.loaded[name]
        if name in self.loading:raise ValueError('Cyclic UC function dependency: '+' -> '.join([*self.loading,name]))
        if len(self.loading)>=16 or len(self.loaded)>=100:raise ValueError('Function dependency limit exceeded')
        value=record if record is not None else self.get(name)
        if value.get('routine_body')!='SQL':raise ValueError('Only SQL scalar UC functions can run here; Python/external definitions need a separate runtime')
        self.loading.append(name)
        try:
            alias='_lh_uc_'+hashlib.sha256(name.encode()).hexdigest()[:24]
            params=[]
            for p in value.get('input_params',{}).get('parameters',[]):
                if p.get('parameter_default') is not None:raise ValueError('Function parameter defaults are not supported by this SQL adapter yet')
                params.append('`'+identifier(p['name'])+'` '+type_text(p['type_text'])[1])
            if value.get('return_params'):raise ValueError('Table-valued functions are not supported')
            body=self.rewrite(expression(value['routine_definition']))
            characteristic=' DETERMINISTIC' if value.get('is_deterministic') else ' NOT DETERMINISTIC'
            ddl=f'CREATE OR REPLACE TEMPORARY FUNCTION `{alias}` ('+', '.join(params)+') RETURNS '+type_text(value['full_data_type'])[1]+characteristic+' RETURN '+body
            self.native(ddl)
            self.loaded[name]=alias
            return alias
        finally:self.loading.pop()

    def rewrite(self,sql):
        ts=tokens(sql);edits=[];i=0
        while i+5<len(ts):
            candidate=ts[i:i+6]
            if (all(candidate[j].kind in ('word','identifier') for j in (0,2,4)) and
                candidate[1].text=='.' and candidate[3].text=='.' and candidate[5].text=='(' and
                (i==0 or ts[i-1].text!='.')):
                # DDL/INSERT column lists also look like c.s.name(...), but name
                # is a table/view target, not a function call.
                previous=i-1
                if previous>=2 and all(word(ts[previous-2+j],v) for j,v in enumerate(('IF','NOT','EXISTS'))):previous-=3
                if previous>=0 and ts[previous].kind=='word' and ts[previous].text.upper() in ('TABLE','VIEW','INTO','OVERWRITE','REFERENCES'):
                    i+=5;continue
                name,_=dotted(ts,i,3);alias=self.bind(name)
                edits.append((ts[i].start,ts[i+4].end,'`'+alias+'`'));i+=5
            else:i+=1
        for start,end,value in reversed(edits):sql=sql[:start]+value+sql[end:]
        return sql

    def run(self,sql,final=None):
        result=None
        for statement in split_statements(sql):
            self.loaded={};self.loading=[]
            parsed=parse_create(statement)
            if parsed is not None:
                value,replace,exists=parsed;name='.'.join(value[k] for k in ('catalog_name','schema_name','name'))
                old=self.get(name,missing=True)
                if old is not None and exists:
                    result=self.tabulate(['message'],[['UC function already exists: '+name]]);continue
                if old is not None and not replace:raise ValueError('UC function already exists: '+name+'; use CREATE OR REPLACE FUNCTION')
                self.request('GET','schemas/'+value['catalog_name']+'.'+value['schema_name'])
                self.bind(name,value)  # Spark validates the real typed expression before persistence.
                if old is not None:
                    if not self.replace:raise ValueError('Function replacement requires the registry control endpoint')
                    self.replace(value,old)
                else:self.request('POST','functions',{'function_info':value})
                result=self.tabulate(['message'],[['Registered UC function: '+name]]);continue
            ts=tokens(statement)
            if len(ts)>1 and word(ts[0],'DROP') and word(ts[1],'FUNCTION'):
                i=2;missing=False
                if i+1<len(ts) and word(ts[i],'IF') and word(ts[i+1],'EXISTS'):i+=2;missing=True
                if i+4>=len(ts) or ts[i+1].text!='.' or ts[i+3].text!='.':
                    result=(final or self.native)(statement);continue
                name,i=dotted(ts,i,3)
                if i!=len(ts):raise ValueError('Unexpected DROP FUNCTION suffix')
                value=self.get(name,missing=missing)
                if value is not None:self.request('DELETE','functions/'+quote(name,safe=''))
                result=self.tabulate(['message'],[['Dropped UC function: '+name if value is not None else 'UC function already absent: '+name]]);continue
            if len(ts)>3 and word(ts[0],'SHOW'):
                i=2 if word(ts[1],'USER') else 1
                if i+3<len(ts) and word(ts[i],'FUNCTIONS') and word(ts[i+1],'IN') and ts[i+3].text=='.':
                    namespace,end=dotted(ts,i+2,2);pattern='*'
                    if end<len(ts):
                        if end+2!=len(ts) or not word(ts[end],'LIKE') or ts[end+1].kind!='string':raise ValueError('Use SHOW FUNCTIONS IN catalog.schema [LIKE pattern]')
                        pattern=ts[end+1].text[1:-1]
                    cat,sch=namespace.split('.');params={'catalog_name':cat,'schema_name':sch};rows=[];seen=set()
                    while True:
                        page=self.request('GET','functions',params=params)
                        for f in page.get('functions',[]):
                            if fnmatch.fnmatchcase(f['name'],pattern):rows.append([namespace+'.'+f['name']])
                        token=page.get('next_page_token')
                        if not token:break
                        if token in seen:raise ValueError('Repeated functions pagination token')
                        seen.add(token);params['page_token']=token
                    result=self.tabulate(['function'],rows);continue
            if len(ts)>2 and word(ts[0],'DESCRIBE') and word(ts[1],'FUNCTION'):
                i=3 if word(ts[2],'EXTENDED') else 2
                if i+4>=len(ts) or ts[i+1].text!='.' or ts[i+3].text!='.':
                    result=(final or self.native)(statement);continue
                name,end=dotted(ts,i,3)
                if end!=len(ts):raise ValueError('Unexpected DESCRIBE FUNCTION suffix')
                f=self.get(name);rows=[['Function',name],['Returns',f.get('full_data_type','')],['Body',f.get('routine_definition','')],['Comment',f.get('comment','')]]
                rows += [['Parameter '+p['name'],p['type_text']] for p in f.get('input_params',{}).get('parameters',[])]
                result=self.tabulate(['property','value'],rows);continue
            result=(final or self.native)(self.rewrite(statement))
        return result
