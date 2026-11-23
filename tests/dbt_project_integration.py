"""Real dbt/Delta/Spark Thrift, isolated local catalog; no .env, UC or R2.

Host: python tests/dbt_project_integration.py
LAKEHOUSE_DBT_TEST_IMAGE selects the runtime image. Downloads Delta Maven jars.
The container and its scratch filesystem are removed on completion.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import uuid


def inside():
    import pyspark
    import yaml
    from pyhive import hive
    from dbt_project import project_destination, ensure_schema_macro
    root = Path('/tmp/dbt-fixture')
    root.mkdir()
    jars = []
    for artifact in ('delta-spark_4.0_2.13', 'delta-storage'):
        jar = root / (artifact + '.jar')
        urllib.request.urlretrieve(f'https://repo.maven.apache.org/maven2/io/delta/{artifact}/4.3.1/{artifact}-4.3.1.jar', jar)
        jars.append(str(jar))
    spark_home = Path(pyspark.__file__).parent
    command = [str(spark_home / 'bin/spark-submit'), '--master', 'local[2]', '--driver-memory', '1g',
        '--class', 'org.apache.spark.sql.hive.thriftserver.HiveThriftServer2', '--jars', ','.join(jars)]
    conf = {'spark.sql.extensions': 'io.delta.sql.DeltaSparkSessionExtension',
            'spark.driver.extraClassPath': ':'.join(jars),
            'spark.sql.catalog.spark_catalog': 'org.apache.spark.sql.delta.catalog.DeltaCatalog',
            'spark.sql.warehouse.dir': (root/'warehouse').as_uri(), 'spark.ui.enabled': 'false',
            'spark.sql.shuffle.partitions': '2', 'spark.sql.hive.thriftServer.singleSession': 'false',
            'spark.hadoop.hive.server2.authentication': 'NOSASL',
            'spark.hadoop.hive.server2.thrift.bind.host': '127.0.0.1',
            'spark.hadoop.javax.jdo.option.ConnectionURL': 'jdbc:derby:'+str(root/'metastore')+';create=true'}
    for key, value in conf.items():
        command += ['--conf', key+'='+value]
    command += [str(next((spark_home/'jars').glob('spark-hive-thriftserver_*.jar')))]
    log = (root/'spark.log').open('w')
    process = subprocess.Popen(command, cwd=root, stdout=log, stderr=subprocess.STDOUT)
    try:
        for _ in range(120):
            if process.poll() is not None:
                raise RuntimeError((root/'spark.log').read_text()[-8000:])
            try:
                connection = hive.connect(host='127.0.0.1', port=10000, username='fixture', auth='NOSASL')
                break
            except Exception:
                time.sleep(1)
        else:
            raise TimeoutError((root/'spark.log').read_text()[-8000:])
        cursor = connection.cursor()
        for sql in ('CREATE SCHEMA raw', 'CREATE SCHEMA a',
                    'CREATE TABLE raw.orders USING DELTA AS SELECT 1 AS order_id, 101 AS customer_id, 100 AS amount UNION ALL SELECT 2, 101, 50'):
            cursor.execute(sql)
        project = root/'project'
        (project/'models/staging').mkdir(parents=True)
        (project/'models/marts').mkdir()
        (project/'seeds').mkdir()
        (project/'seeds/lookup.csv').write_text('id,name\n1,example\n')
        data = {'name': 'fixture', 'version': '1.0.0', 'config-version': 2, 'profile': 'lakehouse',
                'vars': {'lakehouse_catalog': 'spark_catalog'},
                'models': {'fixture': {'+materialized': 'table', '+file_format': 'delta',
                                      'staging': {'+schema': 'a'}, 'marts': {'+schema': 'b'}}},
                'seeds': {'fixture': {'+schema': 'a', '+file_format': 'delta'}}}
        (project/'dbt_project.yml').write_text(yaml.safe_dump(data))
        (project/'models/sources.yml').write_text('version: 2\nsources:\n  - name: landing\n    schema: raw\n    tables:\n      - name: orders\n')
        (project/'models/staging/stg_orders.sql').write_text("select * from {{ source('landing', 'orders') }}")
        (project/'models/marts/fct_orders.sql').write_text("select customer_id, sum(amount) as total_amount from {{ ref('stg_orders') }} group by customer_id")
        (project/'models/tests.yml').write_text('version: 2\nmodels:\n  - name: fct_orders\n    columns:\n      - name: customer_id\n        data_tests: [not_null, unique]\n')
        destination = project_destination(project, {}, {})
        ensure_schema_macro(project)
        for index, cmd in enumerate(('debug', 'seed', 'build', 'test', 'docs')):
            run = root/('run-'+str(index));run.mkdir()
            profile = {'lakehouse': {'target': 'dev', 'outputs': {'dev': {'type': 'spark', 'method': 'thrift',
                'host': '127.0.0.1', 'port': 10000, 'auth': 'NOSASL', 'user': 'fixture', 'schema': 'a',
                'threads': 1, 'server_side_parameters': {'set:hivevar:spark.sql.defaultCatalog': 'spark_catalog'}}}}}
            (run/'profiles.yml').write_text(yaml.safe_dump(profile))
            spec = {'command': cmd, 'destination': destination, 'run_dir': str(run), 'project_dir': str(project),
                    'select': '+fct_orders' if cmd == 'build' else '', 'parameters': {}}
            (run/'dbt-job.json').write_text(json.dumps(spec))
            env = {**os.environ, 'DBT_TARGET_PATH': str(run/'target'), 'DBT_LOG_PATH': str(run/'logs'), 'DBT_SEND_ANONYMOUS_USAGE_STATS': 'false'}
            result = subprocess.run([sys.executable, '/opt/lakehouse/dbt_job.py', str(run/'dbt-job.json')],
                                    env=env, cwd=project, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
            if result.returncode:
                raise AssertionError(result.stdout[-14000:])
            print('PASS real dbt '+cmd, flush=True)
            if cmd == 'docs':
                catalog = json.loads((run/'target/catalog.json').read_text())
                assert {n['metadata']['schema'] for n in catalog['nodes'].values()} == {'a', 'b'}
                assert catalog['sources'] and (run/'target/index.html').is_file()
        cursor.execute('SELECT total_amount FROM b.fct_orders')
        assert cursor.fetchall() == [(150,)]
        cursor.execute('SHOW TABLES IN default')
        assert not cursor.fetchall()
        # A missing-schema model must fail at parse time, never execute SQL.
        (project/'models/missing_schema.sql').write_text('select 999 as id')
        env['DBT_TARGET_PATH'] = str(root/'invalid-target')
        result = subprocess.run([sys.executable, '/opt/lakehouse/dbt_job.py', str(run/'dbt-job.json')],
                                env=env, cwd=project, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
        assert result.returncode and 'Declare +schema' in result.stdout, result.stdout[-5000:]
        cursor.execute('SHOW TABLES IN default')
        assert not cursor.fetchall()
        print('PASS source raw.orders -> a.stg_orders -> b.fct_orders, 2 tests, Docs across schemas, missing-schema rejection', flush=True)
        connection.close()
    finally:
        process.terminate()
        try:process.wait(timeout=20)
        except subprocess.TimeoutExpired:process.kill();process.wait()
        log.close()


def main():
    name = 'dbt-project-check-'+uuid.uuid4().hex[:10]
    image = os.getenv('LAKEHOUSE_DBT_TEST_IMAGE', 'r2-lakehouse-v3-runtime:local')
    source = Path(__file__).resolve().parents[1]
    try:
        subprocess.run(['docker', 'run', '--name', name, '--user', 'root', '--memory', '4g',
                        '-e', 'SPARK_LOCAL_IP=127.0.0.1', '-e', 'PYTHONPATH=/opt/lakehouse',
                        '-v', str(source/'runtime')+':/opt/lakehouse:ro',
                        '-v', str(Path(__file__).resolve())+':/tmp/check.py:ro',
                        image, 'python3', '/tmp/check.py', '--inside'], check=True)
    finally:
        subprocess.run(['docker', 'rm', '-f', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == '__main__':
    inside() if '--inside' in sys.argv else main()
