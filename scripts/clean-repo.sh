#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

find "$ROOT" -type d \( -name __pycache__ -o -name .pytest_cache -o -name .mypy_cache -o -name .ruff_cache \) -prune -exec rm -rf {} +
find "$ROOT" -type f \( -name '*.pyc' -o -name '*.pyo' -o -name '*.log' -o -name '*.pid' \) -delete
if [[ -d "$ROOT/runtime-data" ]]; then
  find "$ROOT/runtime-data" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
fi

echo "Repository runtime/cache artifacts cleaned. .env was preserved and remains git-ignored."
