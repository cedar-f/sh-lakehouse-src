#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
stamp="${1:?Usage: bash scripts/restore.sh 20261117T120000Z --replace-metadata}"
[[ "${2:-}" == --replace-metadata ]] || { printf 'Restore replaces catalog and workflow metadata. Pass --replace-metadata explicitly.\n'; exit 1; }
docker compose stop notebook runner sql kestra registry catalog
docker compose up -d --wait --wait-timeout 120 postgres
docker compose -f compose.yaml -f compose.restore.yaml --profile tools run --rm --no-deps backup python3 /opt/lakehouse/backup_storage.py restore "$stamp" --replace-metadata
docker compose exec -T postgres pg_restore -U lakehouse --clean --if-exists --no-owner --exit-on-error -d unitycatalog < "backups/$stamp/unitycatalog.dump"
docker compose exec -T postgres pg_restore -U lakehouse --clean --if-exists --no-owner --exit-on-error -d kestra < "backups/$stamp/kestra.dump"
docker compose run --rm --no-deps --user root notebook chown -R 1000:1000 /workspace /var/lib/lakehouse
docker compose up -d --wait --wait-timeout 900
