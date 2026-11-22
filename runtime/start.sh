#!/usr/bin/env bash
set -euo pipefail
export SPARK_HOME
SPARK_HOME=$(python3 -c 'import pyspark,os; print(os.path.dirname(pyspark.__file__))')
export PYSPARK_SUBMIT_ARGS="--driver-memory ${SPARK_DRIVER_MEMORY:-4g} pyspark-shell"
if [ "$1" = notebook ]; then
  exec jupyter lab --ip=0.0.0.0 --port=8888 --no-browser --ServerApp.root_dir=/workspace \
    --ServerApp.default_url=/lab --ServerApp.max_body_size=40000000 \
    --IdentityProvider.token="$JUPYTER_TOKEN"
fi
if [ "$1" = sql ]; then
  exec python3 /opt/lakehouse/sql_supervisor.py
fi
