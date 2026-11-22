#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker info >/dev/null
docker compose version
docker_root=$(docker info --format '{{.DockerRootDir}}')
available_kb=$({ df -Pk "$docker_root" 2>/dev/null || df -Pk "$(dirname "$docker_root")"; } | awk 'NR==2 {print $4}')
if [ "${available_kb:-0}" -lt 15728640 ]; then
  printf 'Docker storage needs at least 15 GiB free before the first build. Free space or move Docker data to a larger disk.\n'
  exit 1
fi
python3 - <<'PY'
from pathlib import Path
p=Path('.env')
if not p.exists(): raise SystemExit('Run bash scripts/init.sh first.')
values=dict(line.split('=',1) for line in p.read_text().splitlines() if '=' in line and not line.startswith('#'))
for name in ('R2_ACCOUNT_ID','R2_ACCESS_KEY_ID','R2_SECRET_ACCESS_KEY','R2_BUCKET'):
    if not values.get(name) or values[name]=='CHANGE_ME': raise SystemExit('Fill '+name+' in .env first.')
if '@' not in values.get('KESTRA_USER',''): raise SystemExit('KESTRA_USER must be an email address.')
PY
docker compose build
# Bind mounts may have been created by root or transferred from Windows.
docker compose run --rm --no-deps --user root notebook bash -c \
  'chown -R 1000:1000 /workspace /home/analyst/.ivy2 /home/analyst/.ssh; chmod 700 /home/analyst/.ssh'
# Re-run idempotent initialization even when the bootstrap image did not change.
docker compose up -d --force-recreate --wait --wait-timeout 900 bootstrap
docker compose up -d --wait --wait-timeout 900
printf '\nV3 started. Notebook: http://SERVER_IP:8888/lab (SSH tunnel if BIND_IP=127.0.0.1).\n'
printf 'Use JUPYTER_TOKEN in .env. Kestra uses KESTRA_USER / KESTRA_PASSWORD.\n'
