# Getting Started

This guide brings up the complete OpsSwarm demonstration stack from a clean checkout and verifies that the environment is ready for an end-to-end incident run.

## Prerequisites

Required:

- Docker Engine or Docker Desktop with the Docker daemon running.
- Docker Compose v2 (`docker compose`).
- A GitHub repository and token that can create/read/update Issues in the configured repository.
- A MiniMax API key for the packaged OpenClaw agents.
- Network access to GitHub, the OpenClaw container image registry, and the configured model provider.

Recommended for Windows demonstrations:

- PowerShell 5.1 or newer.
- GitHub CLI (`gh`) only if you want `demo-e2e.ps1 -Approve` to post the approval comment automatically. Manual approval in the GitHub UI does not require `gh`.

## 1. Obtain the repository

```bash
git clone https://github.com/ZINNODNTU/OpsSwarm-IncidentLab.git
cd OpsSwarm-IncidentLab
```

If you already have the repository, run all commands below from its root directory.

## 2. Create the environment file

Linux/macOS:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Set at least:

```dotenv
GITHUB_REPO=ZINNODNTU/OpsSwarm-IncidentLab
GITHUB_TOKEN=YOUR_GITHUB_TOKEN
OPENCLAW_GATEWAY_TOKEN=YOUR_LONG_RANDOM_TOKEN
MINIMAX_API_KEY=YOUR_MINIMAX_API_KEY
```

Generate a gateway token with a cryptographically random value. For example:

```bash
openssl rand -hex 32
```

Do not commit or share the completed `.env` file.

See [Configuration](CONFIGURATION.md) for every supported environment variable.

## 3. Start on Linux

```bash
bash scripts/server-start.sh
```

The startup script:

1. Verifies Docker, Compose v2, and the Docker daemon.
2. Validates the required environment values.
3. Creates runtime-data directories.
4. Builds and starts the unified Compose stack.
5. Waits for OpenClaw, OpsSwarm, and IncidentLab health checks.
6. Runs `scripts/server-smoke.sh`.

A successful startup ends with a message indicating that the OpsSwarm server stack is ready.

## 4. Start on Windows

Use the CMD wrapper:

```bat
scripts\demo-start.cmd
```

The wrapper starts the same Docker architecture used by the Linux server path. It does not require a host-installed OpenClaw process.

The PowerShell launcher also resets the simulated services to a known-good baseline before announcing readiness.

## 5. Verify the stack

Check containers:

```bash
docker compose ps
```

Expected long-running services include:

- `openclaw`
- `opsswarm`
- `incidentlab`
- `auth`
- `order`
- `inventory`
- `payment`
- `booking-api`
- `prometheus`
- `alertmanager`

The `openclaw-init` container is expected to complete successfully and exit because it only initializes the persistent OpenClaw state volume.

Check key endpoints:

```text
IncidentLab UI/API: http://localhost:8080
OpsSwarm health:    http://localhost:8088/health
Prometheus:         http://localhost:9090
Alertmanager:       http://localhost:9093
OpenClaw:           127.0.0.1:18789
```

OpenClaw is intentionally host-loopback-only by default.

## 6. Run the competition preflight

Windows:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\competition-preflight.ps1
```

For the extended check:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\competition-preflight.ps1 -FullTests
```

The preflight checks HTTP health, healthy service baselines, GitHub integration, IncidentLab-to-OpsSwarm connectivity, OpenClaw health, role-based filesystem permissions, S1-S8 skill packaging, and a live specialist model call.

With `-FullTests`, it also runs the IncidentLab test suite and compiles the packaged OpsSwarm Python source.

## 7. Run a first incident

C03 (Bad deployment) is the recommended first scenario:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\demo-e2e.ps1 -Scenario C03
```

The expected workflow is:

```text
known-good baseline
  -> verified bad deployment
  -> OpsSwarm monitoring ingress
  -> GitHub Issue
  -> specialist investigation
  -> RCA
  -> recovery plan
  -> human approval
  -> recovery
  -> S7 + IncidentLab verification
  -> RESOLVED
```

When the run enters `WAITING_APPROVAL`, the script prints the exact GitHub command to post:

```text
/opsswarm approve <option-id>
```

For a scripted demonstration that posts the approval with GitHub CLI:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\demo-e2e.ps1 -Scenario C03 -Approve
```

See [Demo Guide](DEMO_GUIDE.md) for presentation guidance.

## 8. Reset the laboratory

The Windows startup path already performs a full service reset. You can also reset manually:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8080/api/reset
```

For a single service:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8080/api/faults/reset -ContentType application/json -Body '{"service":"payment"}'
```

Use reset for laboratory cleanup, not as a substitute for the governed recovery path during a live incident demo.

## 9. Stop the stack

Linux:

```bash
bash scripts/server-stop.sh
```

Windows:

```bat
scripts\demo-stop.cmd
```

The persistent OpenClaw state volume is preserved by default.

To remove it on Linux:

```bash
bash scripts/server-stop.sh --purge-openclaw-state
```

## 10. Server exposure

The default Compose file publishes IncidentLab, OpsSwarm, the simulator services, Prometheus, and Alertmanager on host ports. For any shared or Internet-facing server:

- Restrict access with a firewall/security group.
- Put required HTTP endpoints behind TLS and an authenticated reverse proxy.
- Do not expose the OpenClaw Gateway publicly unless you deliberately redesign and secure that boundary.
- Treat the stack as a controlled lab/demo environment rather than an unauthenticated public control plane.

See [Security](SECURITY.md).
