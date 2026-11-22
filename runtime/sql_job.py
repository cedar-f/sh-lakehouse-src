import json,sys
from pathlib import Path
from runner import sql_query
Path(sys.argv[2]).write_text(json.dumps(sql_query(Path(sys.argv[1]).read_text()),default=str))
