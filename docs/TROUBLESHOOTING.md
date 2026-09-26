# Troubleshooting

This guide covers common setup, integration, incident, and recovery failures in the packaged OpsSwarm environment.

## Fast diagnostics

Start with:

```bash
docker compose ps
```

Then inspect the three core components:

```bash
docker compose logs --tail=120 openclaw
docker compose logs --tail=120 opsswarm
docker compose logs --tail=120 incidentlab
```

On Windows, the same Docker commands work from PowerShell or CMD.

## 1. Startup says .env is missing

Symptom:

```text
ERROR: .env is missing
```

Fix:

```bash
cp .env.example .env
```

or on PowerShell:

```powershell
Copy-Item .env.example .env
```

Then fill the required credentials.

## 2. Required environment variable is empty

The launchers require:

- `GITHUB_TOKEN`
- `OPENCLAW_GATEWAY_TOKEN`
- `MINIMAX_API_KEY`

Check the repository-root `.env` for blank values.

Do not add spaces around the variable name or move the secrets into `platform/openclaw/openclaw.json`.

## 3. OpenClaw is unhealthy

Check:

```bash
docker compose logs --tail=200 openclaw
```

Common causes:

- Invalid/missing `OPENCLAW_GATEWAY_TOKEN`.
- Invalid/missing `MINIMAX_API_KEY`.
- Image pull/build failure.
- Provider/network failure.
- Broken tracked OpenClaw configuration.

Health probe:

```bash
docker compose exec -T openclaw curl -fsS http://127.0.0.1:18789/healthz
```

If you intentionally changed `OPENCLAW_IMAGE`, verify that the configuration remains compatible with that image.

## 4. IncidentLab is healthy but OpsSwarm integration is unavailable

Check from the host:

```text
GET http://localhost:8080/api/integrations/opsswarm
GET http://localhost:8088/health
```

Then inspect:

```bash
docker compose logs --tail=200 opsswarm
docker compose logs --tail=200 incidentlab
```

Inside Compose, IncidentLab must reach:

```text
http://opsswarm:8088
```

Do not replace that internal service DNS address with `127.0.0.1`.

## 5. GitHub integration shows not_configured

Check:

```text
GET http://localhost:8080/api/integrations/github
```

Expected when configured:

```json
{
  "enabled": true,
  "repo": "ZINNODNTU/OpsSwarm-IncidentLab",
  "issue_creation": "ready"
}
```

If not ready:

1. Verify `GITHUB_TOKEN` is present.
2. Verify `GITHUB_REPO`.
3. Confirm the token can read/write Issues in that repository.
4. Check GitHub/network connectivity.
5. Review OpsSwarm/IncidentLab logs for the GitHub API response.

## 6. A fault request returns "request does not match scenario contract"

The requested `service` and `fault` must exactly match the selected scenario.

Example C03:

```json
{
  "scenario_id": "C03",
  "service": "payment",
  "fault": "bad_deployment"
}
```

Check [Scenario Catalog](SCENARIOS.md).

## 7. Fault injection returns HTTP 502 and no normal incident is created

IncidentLab requires proof that the injected command changed the live runtime.

Check:

- Target service logs.
- `/api/services/<service>/health`.
- `/api/services/<service>/metrics`.
- `/api/services/<service>/probe`.
- `/api/services/<service>/state`.

IncidentLab intentionally rejects the run when it cannot verify a real effect. This prevents a demo from showing a GitHub incident for a fault that did not actually occur.

Reset and retry only after identifying why the state/behavior did not change.

## 8. Baseline establishment fails

The service may have stale persisted state from an earlier interrupted run.

Use:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8080/api/reset
```

Then verify:

```text
GET /api/services/<service>/health
GET /api/services/<service>/state
GET /api/services/<service>/baseline
```

The current fault-injection path also attempts to repair stale state before capturing its baseline, but manual reset is useful when diagnosing environmental problems.

## 9. Run stays at WAITING_APPROVAL

This is expected for write operations in the packaged competition policy.

Find the remediation option and post the exact command printed by the demo:

```text
/opsswarm approve <option-id>
```

Check:

- The command is on the correct Issue.
- The option ID is exact.
- The commenting user has the required repository permission.
- GitHub polling is enabled or the webhook path is functioning.

Polling defaults:

```dotenv
OPSWARM_GITHUB_POLL_ENABLED=true
OPSWARM_GITHUB_POLL_SECONDS=2
```

If using the scripted approval, verify GitHub CLI is installed/authenticated.

## 10. GitHub webhook returns 401

Cause: invalid or missing webhook signature.

Verify:

- `GITHUB_WEBHOOK_SECRET` in `.env`.
- The GitHub repository webhook uses the same secret.
- The request is actually coming through GitHub's signed webhook mechanism.

Do not work around a public webhook failure by disabling signature validation.

## 11. Recovery returns HTTP 409 stale recovery request

The recovery request points to an older run while a newer active run exists for the same service.

The request ID must identify the current incident:

```text
opsswarm-incidentlab-run-<current-run>
```

Retrieve the current IncidentLab evidence/runs and use the exact run ID from the active incident. Do not reuse a recovery payload from a previous demo.

## 12. Recovery returns HTTP 400 unsupported patch keys

The recovery API only accepts persisted-state keys declared by the service baseline.

Do not attempt to patch derived fields such as:

- `healthy`
- `status`
- `http_status`
- `deployment_mismatch`
- `active_faults`

Compare:

```text
GET /api/services/<service>/state
GET /api/services/<service>/baseline
```

Then patch only the diagnosed persisted key(s).

## 13. Recovery request says action must be diagnose_and_patch

The recovery endpoint deliberately rejects "restart" or generic "reset" as a diagnosis.

Required:

```json
{
  "action": "diagnose_and_patch",
  "request_id": "opsswarm-incidentlab-run-...",
  "patch": {
    "diagnosed_key": "known_good_value"
  }
}
```

Administrative reset endpoints exist for lab cleanup, not as the normal governed agent recovery.

## 14. Investigator cannot edit a file

This is expected.

Investigation and postmortem workspaces are read-only. Only `opsswarm-recovery-responder` receives a writable source mount.

The preflight explicitly verifies this security boundary.

## 15. Recovery responder cannot edit runtime-data

This is also expected.

`runtime-data` is over-mounted read-only in the recovery project. The responder may repair authorized source/state through the designated mechanisms but cannot rewrite generated evidence directly.

## 16. Port is already in use

Change the host port in `.env`, for example:

```dotenv
INCIDENTLAB_PORT=18080
OPSSWARM_PORT=18088
```

Then restart the stack.

Remember that scripts containing hard-coded localhost demo endpoints currently expect the default 8080/8088 ports. If you change those ports, use equivalent manual commands or update your local demo tooling consistently.

## 17. Windows blocks PowerShell scripts

Use the provided CMD wrappers where available:

```bat
scripts\demo-start.cmd
scripts\demo-stop.cmd
```

Or invoke PowerShell explicitly:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\competition-preflight.ps1
```

## 18. Need a clean container rebuild

Normal rebuild:

```bash
docker compose down --remove-orphans
docker compose up -d --build
```

Do not delete the OpenClaw state volume unless you actually need to reset it.

On Linux, a full OpenClaw state purge is:

```bash
bash scripts/server-stop.sh --purge-openclaw-state
```

## 19. Preflight fails the workspace-permission check

Run:

```bash
bash scripts/server-smoke.sh
```

The expected boundaries are:

- Application investigator source: readable, not writable.
- Recovery responder source: writable.
- Recovery responder `project/.env`: masked.
- Recovery responder `project/runtime-data`: not writable.

If those checks fail, review the OpenClaw volume mounts in `docker-compose.yml` before running an agent.

## 20. Test the Python layer

Install development dependencies:

```bash
python -m pip install -r requirements-dev.txt
```

Run:

```bash
python -m pytest -q
```

Compile the packaged OpsSwarm runtime:

```bash
python -m compileall -q platform/opsswarm/opsswarm
```

## 21. Collect evidence for a failed demo

Record:

- Scenario ID.
- IncidentLab `run_id`.
- GitHub Issue number.
- Current OpsSwarm state.
- `GET /api/evidence/<run_id>`.
- `GET /runs/<issue-number>`.
- `docker compose ps`.
- Relevant `docker compose logs --tail=200 <service>`.

Do not include tokens/API keys when sharing diagnostic output.

## 22. Clean generated files before publishing

Use:

```bat
scripts\clean-repo.cmd
```

or:

```bash
bash scripts/clean-repo.sh
```

The cleanup scripts remove generated caches/logs/runtime artifacts while preserving the ignored local `.env`.
