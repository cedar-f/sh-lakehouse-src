#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
name="${1:?Usage: bash scripts/hub-user.sh username}"
[[ "$name" =~ ^[a-z][a-z0-9_]{0,30}$ ]] || { printf 'Invalid username\n'; exit 1; }
docker compose -f compose.yaml -f compose.hub.yaml exec --user root notebook bash -c '
  id "$1" >/dev/null 2>&1 || useradd -m -s /bin/bash -g 1000 "$1"
  mkdir -p "/home/$1/.ipython/profile_default/startup"
  cp /opt/lakehouse/startup.py "/home/$1/.ipython/profile_default/startup/00-lakehouse.py"
  chown -R "$1":1000 "/home/$1"
  chmod -R g+rwX /workspace
  passwd "$1"
  python3 -c '\''import json,pwd,spwd,sys,pathlib; n=sys.argv[1]; p=pathlib.Path("/srv/jupyterhub/users"); p.mkdir(exist_ok=True); f=p/(n+".json"); f.write_text(json.dumps({"name":n,"uid":pwd.getpwnam(n).pw_uid,"hash":spwd.getspnam(n).sp_pwdp})); f.chmod(0o600)'\'' "$1"
' bash "$name"
