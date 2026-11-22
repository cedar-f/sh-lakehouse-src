#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose ps
docker compose exec -T runner python3 /opt/lakehouse/smoke_test.py
