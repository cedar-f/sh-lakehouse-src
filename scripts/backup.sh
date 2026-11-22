#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Pause writers for a consistent migration snapshot, then resume even on failure.
docker compose stop notebook runner sql kestra registry catalog
trap 'docker compose up -d --no-build --wait --wait-timeout 900' EXIT
stamp=$(date -u +%Y%m%dT%H%M%SZ)
umask 077
mkdir -p "backups/$stamp"
docker compose exec -T postgres pg_dump -U lakehouse -Fc unitycatalog > "backups/$stamp/unitycatalog.dump"
docker compose exec -T postgres pg_dump -U lakehouse -Fc kestra > "backups/$stamp/kestra.dump"
docker compose --profile tools run --rm --no-deps backup python3 /opt/lakehouse/backup_storage.py create "$stamp"
