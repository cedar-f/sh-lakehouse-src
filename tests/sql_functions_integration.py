"""Actual UC/Postgres + Spark notebook/Thrift/workflow, file-backed fake R2.

Host: python tests/sql_functions_integration.py
LAKEHOUSE_FUNCTION_TEST_IMAGE and LAKEHOUSE_CATALOG_TEST_IMAGE select images.
No .env, production volumes or live R2 are accessed. Temporary containers removed.
"""
import json
from decimal import Decimal
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid


def registry():
    import hashlib,io
    from botocore.exceptions import ClientError
    from catalog_registry import Registry
    import registry_service
    class Store:
        path=Path('/fixture/current.json')
        def get_object(self,**kwargs):
            if not self.path.exists():raise ClientError({'Error':{'Code':'NoSuchKey'}},'GetObject')
            value=self.path.read_bytes();return {'Body':io.BytesIO(value),'ETag':hashlib.sha256(value).hexdigest()}
        def put_object(self,**kwargs):
            old=self.get_object()['ETag'] if self.path.exists() else None
            if kwargs.get('IfNoneMatch')=='*' and old or kwargs.get('IfMatch',old)!=old:
                raise ClientError({'Error':{'Code':'PreconditionFailed'}},'PutObject')
            self.path.write_bytes(kwargs['Body']);return {'ETag':self.get_object()['ETag']}
    registry_service.Registry=lambda:Registry(Store(),bucket='fixture',state=Path('/tmp/function-registry.json'))
    import uvicorn
    uvicorn.run(registry_service.app,host='127.0.0.1',port=8080,log_level='warning')


def stage(phase):
    import pyspark
    import httpx
    from config import uc
    from fastapi.testclient import TestClient
    root=Path('/tmp/function-fixture');root.mkdir()
    reg_log=(root/'registry.log').open('w')
    reg=subprocess.Popen([sys.executable,__file__,'registry'],stdout=reg_log,stderr=subprocess.STDOUT)
    server=None;connection=None
    try:
        for _ in range(90):
            try:urllib.request.urlopen('http://127.0.0.1:8080/health',timeout=2);break
            except Exception:time.sleep(1)
        else:raise RuntimeError((root/'registry.log').read_text())
        if phase=='create':
            uc('POST','catalogs',{'name':'tools'});uc('POST','schemas',{'catalog_name':'tools','name':'calc'})
        jars=[]
        for artifact in ('delta-spark_4.2_2.13','delta-storage'):
            jar=root/(artifact+'.jar')
            urllib.request.urlretrieve(f'https://repo.maven.apache.org/maven2/io/delta/{artifact}/4.4.1/{artifact}-4.4.1.jar',jar);jars.append(str(jar))
        home=Path(pyspark.__file__).parent
        command=[str(home/'bin/spark-submit'),'--master','local[2]','--driver-memory','1g','--class',
                 'org.apache.spark.sql.hive.thriftserver.HiveThriftServer2']
        conf={'spark.driver.extraClassPath':str(home/'jars'/'*')+':'+':'.join(jars)+':/fixture/ivy/jars/*','spark.jars.ivy':'/fixture/ivy','spark.sql.extensions':'io.delta.sql.DeltaSparkSessionExtension',
              'spark.sql.catalog.tools':'io.unitycatalog.spark.UCSingleCatalog',
              'spark.sql.catalog.tools.uri':'http://127.0.0.1:8080','spark.sql.catalog.tools.auth.type':'static','spark.sql.catalog.tools.auth.token':'not-used',
              'spark.sql.catalog.spark_catalog':'org.apache.spark.sql.delta.catalog.DeltaCatalog','spark.ui.enabled':'false',
              'spark.sql.legacy.parameterSubstitution.constantsOnly':'true',
              'spark.sql.warehouse.dir':(root/'warehouse').as_uri(),'spark.sql.hive.thriftServer.singleSession':'false',
              'spark.hadoop.hive.server2.authentication':'NOSASL','spark.hadoop.hive.server2.thrift.bind.host':'127.0.0.1',
              'spark.hadoop.javax.jdo.option.ConnectionURL':'jdbc:derby:'+str(root/'metastore')+';create=true'}
        from spark_dependencies import prepare
        conf.update({'spark.jars':','.join(jars),'spark.jars.packages':'io.unitycatalog:unitycatalog-spark_4.2_2.13:0.7.0,software.amazon.awssdk:auth:2.54.18,software.amazon.awssdk:sts:2.54.18'})
        prepare(conf)
        for k,v in conf.items():command+=['--conf',k+'='+v]
        command+=[str(next((home/'jars').glob('spark-hive-thriftserver_*.jar')))]
        def start_sql():
            log=(root/'sql.log').open('w');process=subprocess.Popen(command,cwd=root,stdout=log,stderr=subprocess.STDOUT)
            from pyhive import hive
            for _ in range(300):
                if process.poll() is not None:raise RuntimeError((root/'sql.log').read_text()[-5000:])
                try:c=hive.connect(host='127.0.0.1',port=10000,auth='NOSASL');c.close();return process
                except Exception:time.sleep(1)
            raise TimeoutError('SQL fixture failed to start')
        server=start_sql()
        import runner
        from workflow_runtime import execute_workflow
        from function_sql_adapters import install
        runner.spark_conf=lambda:{}
        client=TestClient(runner.app);headers={'X-Runner-Token':'fixture-token'}
        def sql(query):
            response=client.post('/sql',json={'sql':query},headers=headers)
            assert response.status_code==200,response.text
            return response.json()
        if phase=='create':
            created=client.post('/views',json={'name':'tools.calc.z_base_view','sql':'SELECT 40 AS value','comment':"Finance's view"},headers=headers)
            assert created.status_code==200,created.text
            assert created.json()['view_definition'] and created.json()['table_type']=='VIEW'
            assert created.json()['comment']=="Finance's view",created.json()
            sql('CREATE VIEW tools.calc.a_dependent_view AS SELECT value + 2 AS answer FROM tools.calc.z_base_view')
            assert sql('SELECT * FROM tools.calc.a_dependent_view')['rows']==[[42]]
            sql('CREATE VIEW tools.calc.dropped_view AS SELECT 0 AS value')
            dropped=client.post('/views/delete',json={'names':['tools.calc.dropped_view'],'confirmed_names':['tools.calc.dropped_view'],'confirmation':'DELETE'},headers=headers)
            assert dropped.status_code==200 and dropped.json()['deleted']==1,dropped.text
            print('PASS native UC views via runner API and SQL, dependent view, metadata/comment, DROP VIEW',flush=True)
            sql("CREATE FUNCTION tools.calc.add_one(value INT) RETURNS INT COMMENT 'Persisted SQL' RETURN value + 1")
            assert sql('SELECT tools.calc.add_one(10) AS result')['rows']==[[11]]
            sql('CREATE OR REPLACE FUNCTION tools.calc.add_one(value INT) RETURNS INT RETURN value + 2')
            assert sql('SELECT tools.calc.add_one(10) AS result')['rows']==[[12]]
            sql('CREATE FUNCTION tools.calc.twice(value INT) RETURNS INT RETURN tools.calc.add_one(value) * 2')
            assert sql('SELECT tools.calc.twice(10) AS result')['rows']==[[24]]
            sql('CREATE TABLE IF NOT EXISTS spark_catalog.default.function_target(value INT) USING DELTA')
            sql('INSERT INTO spark_catalog.default.function_target(value) SELECT tools.calc.twice(10)')
            assert sql('SELECT value FROM spark_catalog.default.function_target')['rows']==[[24]]
            sql('CREATE FUNCTION tools.calc.day_of(v DATE) RETURNS INT DETERMINISTIC RETURN extract(DAY FROM v)')
            assert sql("SELECT tools.calc.day_of(DATE '2026-11-23')")['rows']==[[23]]
            sql('CREATE FUNCTION tools.calc.net_amount(v DECIMAL(18,2), d DECIMAL(18,2)) RETURNS DECIMAL(18,2) RETURN v - coalesce(d, 0)')
            assert Decimal(str(sql('SELECT tools.calc.net_amount(100.00, 15.00)')['rows'][0][0]))==Decimal('85.00')
            assert sql('SHOW FUNCTIONS IN tools.calc')['rows']
            response=client.post('/sql',json={'sql':'CREATE FUNCTION tools.calc.bad(x INT) RETURNS INT RETURN missing_column'},headers=headers)
            assert response.status_code==400
            assert not any(f['name']=='bad' for f in uc('GET','functions',params={'catalog_name':'tools','schema_name':'calc'})['functions'])
            flow={'id':'sql_function_flow','nodes':[
                {'id':'define','kind':'sql','sql':'CREATE FUNCTION tools.calc.triple(x INT) RETURNS INT RETURN x * 3'},
                {'id':'read','kind':'sql','sql':'SELECT tools.calc.triple(7) AS result','dependsOn':['define']}]}
            result=execute_workflow(flow,'sql-function-fixture',{},runner.execute)
            assert result['status']=='SUCCESS',result
            assert result['outputs']['read']['rows']==[[21]]
            print('PASS SQL editor API + workflow SQL tasks, CREATE/SELECT/REPLACE/dependencies/validation',flush=True)
            import spark_session
            # Replace only environment-specific Spark configuration; run the
            # production create_spark() factory and startup/SQL magic unchanged.
            notebook_conf={**conf,'spark.master':'local[1]','spark.driver.memory':'768m','spark.jars':','.join(jars),
                'spark.jars.packages':'io.unitycatalog:unitycatalog-spark_4.2_2.13:0.7.0,software.amazon.awssdk:auth:2.54.18,software.amazon.awssdk:sts:2.54.18'}
            fixture_config="import spark_session\nspark_session.spark_conf=lambda:"+repr(notebook_conf)+"\n"+"""spark_session.settings=lambda:{'driver_memory':'768m','default_schema':'default'}
spark_session.refresh_catalogs=lambda _:[]
"""
            exec(fixture_config)
            from IPython.core.interactiveshell import InteractiveShell
            shell=InteractiveShell.instance()
            assert shell.run_cell(Path('/project/runtime/startup.py').read_text()).error_in_exec is None
            notebook=shell.user_ns['spark']
            assert shell.run_cell('%%sql\nCREATE FUNCTION tools.calc.notebook_fn(v INT) RETURNS INT RETURN v + 5').error_in_exec is None
            assert shell.run_cell('%%sql\nSELECT tools.calc.notebook_fn(5) AS result').error_in_exec is None
            assert shell.user_ns['_last_sql_df'].collect()[0][0]==10
            assert notebook.sql('SELECT tools.calc.add_one(:x) AS result',args={'x':8}).collect()[0][0]==10
            assert notebook.sql('SELECT tools.calc.add_one(?) AS result',args=[8]).first()[0]==10
            assert sql('SELECT tools.calc.notebook_fn(10) AS result')['rows']==[[15]]
            assert shell.run_cell('%%sql\nCREATE VIEW tools.calc.notebook_view AS SELECT answer FROM tools.calc.a_dependent_view').error_in_exec is None
            assert notebook.sql('SELECT * FROM tools.calc.notebook_view').first()[0]==42
            assert sql('SELECT * FROM tools.calc.notebook_view')['rows']==[[42]]
            notebook.stop()
            print('PASS notebook %%sql and spark.sql(parameter args), shared UC function callable from SQL editor',flush=True)
            ipython=Path('/tmp/function-ipython/profile_default/startup');ipython.mkdir(parents=True)
            (ipython/'00-lakehouse.py').write_text(fixture_config+"exec(compile(open('/opt/lakehouse/startup.py').read(), 'startup.py', 'exec'))\n")
            os.environ['IPYTHONDIR']=str(ipython.parents[1])
            import nbformat
            path=Path(os.environ['WORKSPACE_ROOT'])/'function.ipynb'
            nbformat.write(nbformat.v4.new_notebook(cells=[
                nbformat.v4.new_code_cell('%%sql\nCREATE FUNCTION tools.calc.workflow_fn(v INT) RETURNS INT RETURN v + 7'),
                nbformat.v4.new_code_cell('%%sql\nCREATE VIEW tools.calc.workflow_view AS SELECT * FROM tools.calc.notebook_view'),
                nbformat.v4.new_code_cell("set_output('view_result', spark.sql('SELECT * FROM tools.calc.workflow_view').first()[0])"),
                nbformat.v4.new_code_cell("set_output('result', spark.sql('SELECT tools.calc.workflow_fn(3)').first()[0])")]),path)
            result=execute_workflow({'id':'notebook_function_flow','nodes':[{'id':'notebook','kind':'notebook','path':'function.ipynb'}]},
                'notebook-function-fixture',{},runner.execute)
            assert result['status']=='SUCCESS' and result['outputs']['notebook']['result']==10,result
            assert result['outputs']['notebook']['view_result']==42,result
            print('PASS workflow notebook kernel: automatic startup, CREATE FUNCTION, SELECT and captured output',flush=True)
            server.terminate();server.wait(timeout=25);server=start_sql()
            assert sql('SELECT tools.calc.twice(10) AS result')['rows']==[[24]]
            sql('DROP FUNCTION tools.calc.triple')
            response=client.post('/sql',json={'sql':'SELECT tools.calc.triple(7)'},headers=headers)
            assert response.status_code==400 and 'not found' in response.text
            print('PASS fresh SQL service reload, DROP FUNCTION and no stale managed-name calls',flush=True)
        else:
            assert sql('SELECT * FROM tools.calc.a_dependent_view')['rows']==[[42]]
            assert sql('SELECT * FROM tools.calc.workflow_view')['rows']==[[42]]
            assert uc('GET','tables/tools.calc.z_base_view')['comment']=="Finance's view"
            assert not any(t['name']=='dropped_view' for t in uc('GET','tables',params={'catalog_name':'tools','schema_name':'calc'})['tables'])
            print('PASS native SQL view replay in dependency order from R2 registry v3',flush=True)
            assert sql('SELECT tools.calc.twice(10) AS result')['rows']==[[24]]
            assert sql('SELECT tools.calc.notebook_fn(5) AS result')['rows']==[[10]]
            assert sql('SELECT tools.calc.workflow_fn(3)')['rows']==[[10]]
            assert Decimal(str(sql('SELECT tools.calc.net_amount(100.00, 15.00)')['rows'][0][0]))==Decimal('85.00')
            assert not any(f['name']=='triple' for f in uc('GET','functions',params={'catalog_name':'tools','schema_name':'calc'})['functions'])
            print('PASS UC/Postgres reset -> R2 definition replay -> fresh Spark execution, deleted function remains absent',flush=True)
        assert json.loads(Path('/fixture/current.json').read_text())['functions']
    except Exception:
        print('REGISTRY LOG:',(root/'registry.log').read_text()[-12000:],flush=True)
        if (root/'sql.log').exists():
            text=(root/'sql.log').read_text()
            print('SQL START:',text[:10000],flush=True)
            print('SQL CAUSES:','\n'.join(line for line in text.splitlines() if 'Caused by:' in line or 'ClassNotFoundException' in line or 'NoClassDefFound' in line),flush=True)
        print('SQL LOG:',(root/'sql.log').read_text()[-4000:] if (root/'sql.log').exists() else '',flush=True)
        raise
    finally:
        if server:
            server.terminate()
            try:server.wait(timeout=25)
            except subprocess.TimeoutExpired:server.kill();server.wait()
        reg.terminate();reg.wait(timeout=15);reg_log.close()


def main():
    root=Path(__file__).resolve().parents[1];tag='sql-function-'+uuid.uuid4().hex[:10]
    pg=tag+'-pg';cat=tag+'-uc'
    image=os.getenv('LAKEHOUSE_FUNCTION_TEST_IMAGE','r2-lakehouse-v3-runtime:local')
    catalog=os.getenv('LAKEHOUSE_CATALOG_TEST_IMAGE','r2-lakehouse-v3-catalog:local')
    def docker(*args):return subprocess.check_output(['docker',*args],text=True).strip()
    try:
        docker('network','create',tag)
        docker('run','-d','--name',pg,'--network',tag,'-e','POSTGRES_USER=lakehouse','-e','POSTGRES_PASSWORD=fixture',
               '-e','POSTGRES_DB=unitycatalog','postgres:16.6')
        for _ in range(60):
            if subprocess.run(['docker','exec',pg,'pg_isready','-U','lakehouse'],capture_output=True).returncode==0:break
            time.sleep(1)
        def start_catalog():
            docker('run','-d','--name',cat,'--network',tag,'--network-alias','catalog',
                   '--add-host','postgres:'+docker('inspect',pg,'--format','{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'),
                   '-e','POSTGRES_PASSWORD=fixture','-e','R2_BUCKET=fixture','-e','R2_ACCESS_KEY_ID=fixture',
                   '-e','R2_SECRET_ACCESS_KEY=fixture',catalog)
            for _ in range(90):
                if subprocess.run(['docker','exec',cat,'wget','-q','-O','-',
                    'http://127.0.0.1:8080/api/2.1/unity-catalog/catalogs'],capture_output=True).returncode==0:return
                time.sleep(1)
            raise TimeoutError('UC failed to start')
        start_catalog()
        with tempfile.TemporaryDirectory(prefix='sql-function-registry-') as folder:
            for phase in ('create','restore'):
                if phase=='restore':
                    docker('rm','-f',cat)
                    docker('exec',pg,'psql','-U','lakehouse','-d','postgres','-c','DROP DATABASE unitycatalog WITH (FORCE)')
                    docker('exec',pg,'psql','-U','lakehouse','-d','postgres','-c','CREATE DATABASE unitycatalog')
                    start_catalog()
                worker=tag+'-'+phase
                try:
                    subprocess.run(['docker','run','--name',worker,'--network',tag,'--user','root','--memory','6g',
                        '-v',str(root)+':/project:ro','-v',folder+':/fixture','-e','PYTHONPATH=/project/runtime',
                        '-e','UC_URL=http://127.0.0.1:8080','-e','UC_UPSTREAM_URL=http://catalog:8080',
                        '-e','RUNNER_TOKEN=fixture-token','-e','R2_BUCKET=fixture','-e','R2_ACCOUNT_ID=fixture',
                        '-e','R2_ACCESS_KEY_ID=fixture','-e','R2_SECRET_ACCESS_KEY=fixture',
                        '-e','DEFAULT_CATALOG=spark_catalog','-e','DEFAULT_SCHEMA=default','-e','SQL_HOST=127.0.0.1',
                        '-e','SPARK_LOCAL_IP=127.0.0.1','-e','WORKSPACE_ROOT=/tmp/workspace','-e','RUNTIME_ROOT=/tmp/runtime',
                        '-e','RUNS_ROOT=/tmp/runs',image,'python3','/project/tests/sql_functions_integration.py','stage',phase],check=True)
                finally:subprocess.run(['docker','rm','-fv',worker],capture_output=True)
    finally:
        for name in (cat,pg):subprocess.run(['docker','rm','-fv',name],capture_output=True)
        subprocess.run(['docker','network','rm',tag],capture_output=True)


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='registry':registry()
    elif len(sys.argv)>1 and sys.argv[1]=='stage':stage(sys.argv[2])
    else:main()
