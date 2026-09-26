#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker is required." >&2
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "ERROR: Docker Compose v2 is required." >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "ERROR: Docker daemon is not reachable." >&2
  exit 1
fi
if [[ ! -f .env ]]; then
  echo "ERROR: .env is missing. Copy .env.example to .env and fill the required secrets." >&2
  exit 1
fi

require_env() {
  local key="$1"
  local value
  value="$(grep -E "^[[:space:]]*${key}=" .env | tail -n 1 | cut -d= -f2- | tr -d '\r' || true)"
  if [[ -z "$value" ]]; then
    echo "ERROR: ${key} is empty in .env" >&2
    exit 1
  fi
}

require_env GITHUB_TOKEN
require_env OPENCLAW_GATEWAY_TOKEN
require_env MINIMAX_API_KEY

mkdir -p runtime-data/opsswarm runtime-data/incidentlab runtime-data/service-state/{auth,order,inventory,payment,booking-api}

docker compose up -d --build

echo "Waiting for OpenClaw, OpsSwarm and IncidentLab health checks..."
deadline=$((SECONDS + 180))
for service in openclaw opsswarm incidentlab; do
  while true; do
    cid="$(docker compose ps -q "$service")"
    if [[ -n "$cid" ]]; then
      status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$cid" 2>/dev/null || true)"
      if [[ "$status" == "healthy" || "$status" == "running" ]]; then
        break
      fi
      if [[ "$status" == "unhealthy" || "$status" == "exited" || "$status" == "dead" ]]; then
        echo "ERROR: $service entered state $status" >&2
        docker compose logs --tail=120 "$service" >&2 || true
        exit 1
      fi
    fi
    if (( SECONDS >= deadline )); then
      echo "ERROR: timed out waiting for $service" >&2
      docker compose logs --tail=120 "$service" >&2 || true
      exit 1
    fi
    sleep 2
  done
done

"$(dirname "$0")/server-smoke.sh"

echo
echo "OpsSwarm server stack is ready."
echo "IncidentLab UI: http://127.0.0.1:${INCIDENTLAB_PORT:-8080}/"
echo "OpsSwarm API:   http://127.0.0.1:${OPSSWARM_PORT:-8088}/health"
echo "OpenClaw host port is loopback-only by default."
