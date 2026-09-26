#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ "${1:-}" == "--purge-openclaw-state" ]]; then
  docker compose down --remove-orphans --volumes
else
  docker compose down --remove-orphans
fi
