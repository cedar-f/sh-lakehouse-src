"""Notebook helper: set_output('count', 3), then use outputs.task.count."""
import json,os
from pathlib import Path
from run_store import atomic_json,read_json
def set_output(name,value):
    if not isinstance(name,str) or not name or name.startswith('_'):raise ValueError('Output name must be a nonempty public string')
    if not os.getenv('LAKEHOUSE_RUN_DIR'):raise RuntimeError('set_output is available in background notebook/workflow runs. Start this notebook from the Notebook or Workflows panel.')
    path=Path(os.environ['LAKEHOUSE_RUN_DIR'])/'outputs.json';data=read_json(path);data[name]=value
    if len(json.dumps(data,ensure_ascii=False,allow_nan=False).encode())>1024*1024:raise ValueError('Task outputs exceed 1 MiB; return table or artifact paths instead')
    atomic_json(path,data)
