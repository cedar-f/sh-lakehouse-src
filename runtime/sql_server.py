import os
from pathlib import Path
from service_readiness import spark_conf_when_catalog_ready
conf = spark_conf_when_catalog_ready()
from spark_dependencies import prepare
prepare(conf)
args = [str(Path(os.environ['SPARK_HOME'])/'bin/spark-submit'),
        '--class','org.apache.spark.sql.hive.thriftserver.HiveThriftServer2',
        '--driver-memory', conf['spark.driver.memory']]
for key,value in conf.items(): args += ['--conf',key+'='+value]
args += ['--conf','spark.sql.hive.thriftServer.singleSession=false',
         '--conf','spark.hadoop.hive.server2.authentication=NOSASL',
         '--conf','spark.hadoop.hive.server2.thrift.bind.host=0.0.0.0',
         '--conf','spark.hadoop.hive.server2.thrift.port=10000']
args += [str(next((Path(os.environ['SPARK_HOME'])/'jars').glob('spark-hive-thriftserver_*.jar')))]
os.execv(args[0],args)
