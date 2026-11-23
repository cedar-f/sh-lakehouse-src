"""Shared notebook and private Thrift adapters for UC-backed SQL functions."""
import os
import httpx

from function_mutations import digest
from sql_functions import SQLFunctions


def replace(value,old):
    base=os.getenv('UC_URL','http://registry:8080').rstrip('/')
    with httpx.Client(timeout=120) as client:
        r=client.post(base+'/registry/functions/replace',json={'function_info':value,'expected':digest(old)},
                      headers={'X-Runner-Token':os.environ['RUNNER_TOKEN']})
        if r.is_error:
            try:message=r.json().get('detail',r.text)
            except ValueError:message=r.text[:2000]
            raise ValueError(str(message))
        return r.json()


def install(spark):
    """Wrap this notebook SparkSession only, preserving Spark's SQL argument API."""
    if hasattr(spark,'_lakehouse_original_sql'):return spark
    original=spark.sql
    spark._lakehouse_original_sql=original
    def tabulate(columns,rows):
        from pyspark.sql.types import StructType,StructField,StringType
        schema=StructType([StructField(c,StringType(),True) for c in columns])
        return spark.createDataFrame(rows,schema)
    def managed_sql(sqlQuery,args=None,**kwargs):
        engine=SQLFunctions(original,tabulate,replace=replace)
        return engine.run(sqlQuery,final=lambda text:original(text,args=args,**kwargs))
    spark.sql=managed_sql
    return spark
