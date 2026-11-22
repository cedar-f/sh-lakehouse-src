#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ "$#" -gt 1 ] || { [ "$#" -eq 1 ] && [ "$1" != --reset-metadata ]; }; then
  printf 'Usage: bash scripts/rebuild.sh [--reset-metadata]\n'
  exit 2
fi
if [ ! -f .env ]; then
  printf 'Copy/configure .env before rebuilding.\n'
  exit 1
fi
docker compose config --quiet
if [ "${1:-}" = --reset-metadata ]; then
  # Validate credentials/layout before removing any existing local metadata.
  docker compose build bootstrap
  docker compose run --rm --no-deps bootstrap python3 -c \
    'import os; from platform_bootstrap import storage,ensure_layout; print(ensure_layout(storage(),os.environ["R2_BUCKET"]))'
  python3 scripts/reset_metadata.py --confirm-reset-metadata
fi
bash scripts/init.sh
bash scripts/start.sh
