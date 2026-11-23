from config import spark_conf, all_catalogs, settings

def create_spark():
    import os
    os.environ['PYSPARK_SUBMIT_ARGS']='--driver-memory '+settings()['driver_memory']+' pyspark-shell'
    from pyspark.sql import SparkSession
    builder = SparkSession.builder.appName('Lakehouse V3')
    for key,value in spark_conf().items(): builder = builder.config(key,value)
    spark = builder.getOrCreate()
    spark.sql('USE SCHEMA `'+settings()['default_schema']+'`')
    from function_sql_adapters import install
    return install(spark)

def refresh_catalogs(spark):
    conf = spark_conf()
    for key,value in conf.items():
        if key.startswith('spark.sql.catalog.') and not key.endswith('spark_catalog'):
            spark.conf.set(key,value)
    return [c['name'] for c in all_catalogs()]
