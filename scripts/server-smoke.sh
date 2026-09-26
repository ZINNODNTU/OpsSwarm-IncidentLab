#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

docker compose exec -T openclaw curl -fsS http://127.0.0.1:18789/healthz >/dev/null
docker compose exec -T opsswarm python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8088/health', timeout=3)" >/dev/null
docker compose exec -T incidentlab python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=3)" >/dev/null

docker compose exec -T openclaw sh -lc 'test -r /opt/opsswarm/workspaces/opsswarm-application-investigator/project/incidentlab/api.py'
docker compose exec -T openclaw sh -lc 'test ! -w /opt/opsswarm/workspaces/opsswarm-application-investigator/project/incidentlab/api.py'
docker compose exec -T openclaw sh -lc 'test -w /opt/opsswarm/workspaces/opsswarm-recovery-responder/project/incidentlab/api.py'
docker compose exec -T openclaw sh -lc 'grep -q "Intentionally blank" /opt/opsswarm/workspaces/opsswarm-recovery-responder/project/.env'
docker compose exec -T openclaw sh -lc 'test ! -w /opt/opsswarm/workspaces/opsswarm-recovery-responder/project/runtime-data'

echo "SMOKE PASS: gateway/API health, read-only investigators, writable recovery workspace, masked secrets and protected runtime evidence."
