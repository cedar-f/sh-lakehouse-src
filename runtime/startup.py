from IPython import get_ipython
from IPython.display import display
from spark_session import create_spark, refresh_catalogs as _refresh_catalogs
from runtime_outputs import set_output
spark = create_spark()
get_ipython().user_ns.update(spark=spark, refresh_catalogs=lambda: _refresh_catalogs(spark))
def sql_cell(line,cell):
    _refresh_catalogs(spark)
    frame=spark.sql(cell)
    get_ipython().user_ns['_last_sql_df']=frame
    if frame.columns: display(frame.limit(1000).toPandas())
get_ipython().register_magic_function(sql_cell,'cell','sql')
print('Spark + Delta + catalog ready. Use %%sql; display limited to 1000 rows.')
