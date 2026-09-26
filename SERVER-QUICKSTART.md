# OpsSwarm Server Quick Start

This package is ready for a Docker-capable Linux server.

## Requirements

- Docker Engine
- Docker Compose v2
- GitHub repository/token for the IncidentLab issue workflow
- MiniMax API key

## 1. Create server configuration

```bash
cp .env.example .env
nano .env
```

Fill at least:

```dotenv
GITHUB_REPO=ZINNODNTU/OpsSwarm-IncidentLab
GITHUB_TOKEN=...
OPENCLAW_GATEWAY_TOKEN=...
MINIMAX_API_KEY=...
```

Generate a gateway token if needed:

```bash
openssl rand -hex 32
```

Do not commit or send the completed `.env` file.

## 2. Start

```bash
bash scripts/server-start.sh
```

The launcher builds the unified Docker stack, waits for health checks, and runs the server smoke test.

## 3. Verify

```bash
docker compose ps
```

Expected core services: `openclaw`, `opsswarm`, `incidentlab`, `auth`, `order`, `inventory`, `payment`, and `booking-api`.

Default endpoints:

- IncidentLab: `http://SERVER_IP:8080`
- OpsSwarm health: `http://SERVER_IP:8088/health`
- Prometheus: `http://SERVER_IP:9090`
- Alertmanager: `http://SERVER_IP:9093`
- OpenClaw host binding: `127.0.0.1:18789` by default

## 4. Stop

```bash
bash scripts/server-stop.sh
```

To also delete the persistent OpenClaw state volume:

```bash
bash scripts/server-stop.sh --purge-openclaw-state
```

See `README.md` for architecture, recovery boundaries, Windows demo commands, and upstream skill synchronization details.
