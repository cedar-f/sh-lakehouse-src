#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
notebook_path="${1:?Usage: bash scripts/check-notebook.sh path/under/workspace.ipynb}"
docker compose exec -T runner python3 - "$notebook_path" <<'PY'
import httpx,os,sys
with httpx.Client(timeout=900,headers={'X-Runner-Token':os.environ['RUNNER_TOKEN']}) as client:
    response=client.post('http://localhost:8765/run',json={
        'kind':'notebook','path':sys.argv[1],'parameters':{'name':'notebook-check'}})
    result=response.json()
    print(result)
    if response.is_error:
        run_id=result.get('detail',{}).get('id')
        if run_id: print(client.get('http://localhost:8765/jobs/'+run_id).json().get('log',''))
    response.raise_for_status()
PY
