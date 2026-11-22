#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
python3 - <<'PY'
import pathlib,secrets,subprocess
from zoneinfo import ZoneInfo
path=pathlib.Path('.env')
if not path.exists():
    text=pathlib.Path('.env.example').read_text()
    for key in ('JUPYTER_TOKEN','RUNNER_TOKEN','POSTGRES_PASSWORD','KESTRA_PASSWORD'):
        text=text.replace(key+'=GENERATE',key+'=V3a'+secrets.token_hex(24))
    try:
        zone=subprocess.check_output(['timedatectl','show','-p','Timezone','--value'],text=True).strip()
        ZoneInfo(zone);text=text.replace('TZ=Asia/Ho_Chi_Minh','TZ='+zone)
    except Exception:pass
    path.write_text(text)
    path.chmod(0o600)
    print('Created .env. Fill the four R2_ fields using nano .env.')
else: print('.env already exists; kept existing values.')
values=dict(line.split('=',1) for line in path.read_text().splitlines() if '=' in line and not line.lstrip().startswith('#'))
workspace=pathlib.Path(values.get('WORKSPACE_DIR','./workspace').strip().strip('"').strip("'") or './workspace').resolve()
workspace.mkdir(parents=True,exist_ok=True)
(workspace/'.lakehouse').mkdir(parents=True,exist_ok=True)
print('Workspace data directory: '+str(workspace))
PY
