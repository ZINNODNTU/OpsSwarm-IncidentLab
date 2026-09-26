# Configuration

OpsSwarm is configured primarily through the repository-root `.env` file consumed by Docker Compose.

Start from the safe template:

```bash
cp .env.example .env
```

## Environment variables

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `GITHUB_REPO` | Yes for GitHub workflow | `ZINNODNTU/OpsSwarm-IncidentLab` | Repository used as the incident system of record |
| `GITHUB_TOKEN` | Yes | Empty | GitHub API token used for Issue creation, comments, labels, permissions and lifecycle operations |
| `GITHUB_WEBHOOK_SECRET` | When GitHub webhooks are enabled | Empty | Shared HMAC secret for validating `/webhooks/github` deliveries |
| `OPENCLAW_GATEWAY_TOKEN` | Yes | Empty | Authentication token between OpsSwarm and the OpenClaw Gateway |
| `OPENCLAW_GATEWAY_PORT` | No | `18789` | Host loopback port for OpenClaw |
| `OPENCLAW_IMAGE` | No | `ghcr.io/openclaw/openclaw:2026.9.6` | OpenClaw base image |
| `MINIMAX_API_KEY` | Yes for the packaged model | Empty | Provider credential used by OpenClaw agents |
| `INCIDENTLAB_AGENT_URL` | No | `http://incidentlab:8080` | IncidentLab URL embedded in agent-facing incident evidence |
| `INCIDENTLAB_FALLBACK_URL` | No | `http://incidentlab:8080` | Alternate IncidentLab URL included in incident context |
| `INCIDENTLAB_PORT` | No | `8080` | Host port for IncidentLab |
| `OPSSWARM_PORT` | No | `8088` | Host port for OpsSwarm |
| `AUTH_PORT` | No | `8001` | Host port for the auth simulator |
| `ORDER_PORT` | No | `8002` | Host port for the order simulator |
| `INVENTORY_PORT` | No | `8003` | Host port for the inventory simulator |
| `PAYMENT_PORT` | No | `8004` | Host port for the payment simulator |
| `BOOKING_API_PORT` | No | `8005` | Host port for the booking-api simulator |
| `PROMETHEUS_PORT` | No | `9090` | Host port for Prometheus |
| `ALERTMANAGER_PORT` | No | `9093` | Host port for Alertmanager |
| `OPSWARM_GITHUB_POLL_ENABLED` | No | `true` | Enables GitHub polling fallback |
| `OPSWARM_GITHUB_POLL_SECONDS` | No | `2` | Poll interval used by the packaged demo |
| `OPSWARM_OPENCLAW_TIMEOUT` | No | `600` | Maximum OpenClaw request timeout in seconds |

## Minimal configuration

```dotenv
GITHUB_REPO=ZINNODNTU/OpsSwarm-IncidentLab
GITHUB_TOKEN=github_token_here
OPENCLAW_GATEWAY_TOKEN=random_gateway_token_here
MINIMAX_API_KEY=minimax_key_here
```

The remaining values can use the defaults from `.env.example`.

## GitHub configuration

### Token

The GitHub token must be able to perform the operations required by the demo in the target repository, including reading repository metadata and reading/writing Issues and comments.

Use the least privilege supported by your GitHub token type and repository policy.

### Webhook secret

If you expose `POST /webhooks/github` to GitHub, set the same value in:

1. The repository's GitHub webhook secret.
2. `GITHUB_WEBHOOK_SECRET` in `.env`.

OpsSwarm validates GitHub webhook signatures with HMAC-SHA256.

### Polling fallback

The packaged demo enables polling by default:

```dotenv
OPSWARM_GITHUB_POLL_ENABLED=true
OPSWARM_GITHUB_POLL_SECONDS=2
```

Polling allows issue/comment processing without requiring a publicly reachable webhook endpoint. Keep the interval reasonable to avoid unnecessary API consumption.

## OpenClaw configuration

The tracked OpenClaw configuration is:

```text
platform/openclaw/openclaw.json
```

The `openclaw-init` service copies this file into the persistent OpenClaw state volume before the gateway starts.

Default agent model:

```text
minimax/MiniMax-M2.7-highspeed
```

All packaged roles share this default unless the OpenClaw configuration is intentionally changed.

### Gateway token

`OPENCLAW_GATEWAY_TOKEN` should be a long random value. OpsSwarm sends the same token when communicating with the gateway.

The host binding is loopback-only by default:

```text
127.0.0.1:18789
```

Container-to-container calls do not use host loopback; OpsSwarm calls `http://openclaw:18789`.

## IncidentLab URLs

Keep these values on Docker service DNS for the default deployment:

```dotenv
INCIDENTLAB_AGENT_URL=http://incidentlab:8080
INCIDENTLAB_FALLBACK_URL=http://incidentlab:8080
```

Do not replace them with `127.0.0.1` for container-to-container agent access. Inside the OpenClaw container, loopback refers to OpenClaw itself, not IncidentLab.

If you intentionally deploy a routable private URL, verify that OpenClaw can reach it and that it does not expose the recovery interface to untrusted clients.

## OpsSwarm policy configuration

The packaged demo policy is in:

```text
platform/opsswarm/config/incidentlab-demo.yaml
```

Important defaults:

```yaml
required_issue_label: incidentlab
root_cause_confidence_threshold: 0.80
verification_confidence_threshold: 0.85
max_parallel_investigators: 1

policy:
  read: AUTO
  safe_write: HUMAN_APPROVAL
  risky_write: HUMAN_APPROVAL
  destructive: DENY
```

The `max_parallel_investigators: 1` setting makes the packaged competition workflow deterministic by dispatching specialist investigations sequentially.

Approval requires at least the configured `maintain` repository permission.

## Port customization

Host-side ports can be changed in `.env` without changing container service ports. Example:

```dotenv
INCIDENTLAB_PORT=18080
OPSSWARM_PORT=18088
PROMETHEUS_PORT=19090
ALERTMANAGER_PORT=19093
```

After changing host ports, update any host-side commands, reverse proxy configuration, firewall rules, or demo bookmarks.

Internal Compose URLs such as `http://opsswarm:8088` and `http://incidentlab:8080` remain unchanged.

## Persistence

Runtime state is stored under:

```text
runtime-data/
├── incidentlab/
├── opsswarm/
└── service-state/
```

OpenClaw configuration/state is stored in the named Docker volume `openclaw-state`.

Stopping the stack normally preserves the OpenClaw state volume. Use the purge option only when you intentionally want a clean OpenClaw state.

## Secret-handling rules

- Never commit `.env`.
- Do not place provider or GitHub credentials in Markdown, source files, screenshots, or incident evidence.
- Rotate any secret that was exposed in terminal output, a recording, a GitHub Issue, or a commit.
- Keep OpenClaw's host gateway port loopback-only unless there is a specific secure deployment design.
- Use firewall and reverse-proxy authentication if IncidentLab or OpsSwarm is reachable beyond a trusted machine/network.
