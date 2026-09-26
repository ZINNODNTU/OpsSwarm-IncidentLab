# API Reference

The stack exposes two primary HTTP APIs:

- **IncidentLab:** `http://localhost:8080`
- **OpsSwarm:** `http://localhost:8088`

Host ports are configurable in `.env`. Inside Docker Compose, services use the container DNS names and fixed container ports.

## IncidentLab API

### Endpoint summary

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | IncidentLab health |
| GET | `/api/scenarios` | List C01-C12 |
| GET | `/api/scenarios/{scenario_id}` | Get one scenario |
| GET | `/api/services` | Health summary for all simulator services |
| GET | `/api/services/{service}/health` | Live service health |
| GET | `/api/services/{service}/metrics` | Service metrics/state-derived measurements |
| GET | `/api/services/{service}/probe` | Real workload probe |
| GET | `/api/services/{service}/state` | Persisted state artifact |
| GET | `/api/services/{service}/baseline` | Declared known-good baseline |
| GET | `/api/faults` | Supported fault names |
| GET | `/api/integrations/github` | GitHub configuration/readiness |
| GET | `/api/integrations/opsswarm` | IncidentLab-to-OpsSwarm connectivity |
| POST | `/api/faults/inject` | Inject and verify a scenario fault |
| POST | `/api/faults/reset` | Reset one simulator service |
| POST | `/api/recovery/{service}` | Apply a run-bound diagnosed state patch |
| GET | `/api/evidence` | List IncidentLab runs/evidence |
| GET | `/api/evidence/{run_id}` | Read one run |
| POST | `/api/reset` | Reset all simulator services |
| POST | `/hooks/monitoring` | Normalize a monitoring/Alertmanager payload |

The web UI is mounted at `/`.

### GET /api/health

Representative response:

```json
{
  "ok": true,
  "service": "incidentlab",
  "role": "fault-simulation-observability",
  "timestamp": "2026-09-26T00:00:00Z"
}
```

### POST /api/faults/inject

Request model:

- `scenario_id`: required.
- `service`: required.
- `fault`: required.
- `duration_seconds`: integer, 1-86400, default 30.
- `auto_reset`: boolean, default false.
- `metadata`: arbitrary metadata object.

Example:

```json
{
  "scenario_id": "C03",
  "service": "payment",
  "fault": "bad_deployment",
  "duration_seconds": 900,
  "auto_reset": false,
  "metadata": {
    "demo": "competition-e2e"
  }
}
```

Important behavior:

1. IncidentLab restores stale service state to the declared baseline if necessary.
2. It captures baseline health, metrics, workload, and persisted state.
3. It injects the configured scenario fault.
4. It proves the live fault effect.
5. Only then does it dispatch the incident to OpsSwarm.
6. If OpsSwarm is unavailable, the implementation can attempt direct GitHub Issue creation as a fallback.
7. If the fault cannot be proven, IncidentLab resets the service and returns an error rather than creating a normal verified incident.

### POST /api/recovery/{service}

Recovery is intentionally not a generic reset endpoint.

Request:

```json
{
  "action": "diagnose_and_patch",
  "request_id": "opsswarm-incidentlab-run-abc123",
  "patch": {
    "version": "v2.0"
  }
}
```

Rules:

- `action` must be `diagnose_and_patch`.
- `request_id` must include the exact target `incidentlab-run-...` identifier.
- The target run must exist and match the service.
- The run must be in a recoverable state.
- If a newer active run exists for the same service, the older request is rejected with HTTP 409.
- Patch keys must be writable persisted-state keys from the declared baseline.
- Derived health/status fields are ignored or rejected as non-writable state.
- Unknown non-derived keys are rejected with HTTP 400.
- The response includes the applied patch and a verification result.

This protects the lab from a recovery generated for one incident being applied to another incident.

### POST /api/faults/reset

Example:

```json
{
  "service": "payment"
}
```

This is an administrative lab-reset operation. It should not be presented as the governed agent recovery path.

### POST /api/reset

Resets all simulator services and updates the latest active run per service with resulting verification data when applicable.

Useful before demonstrations and between scenarios.

### GET /api/evidence/{run_id}

Returns the stored IncidentLab run, including the evidence timeline, fault verification, integration linkage, recovery events, and verification result.

### POST /hooks/monitoring

IncidentLab accepts:

1. A normalized `MonitoringEvent`.
2. A native Alertmanager payload containing an `alerts` array.

Normalized example:

```json
{
  "source": "incidentlab",
  "event_type": "alert",
  "event_id": "incidentlab-payment-001",
  "timestamp": "2026-09-26T00:00:00Z",
  "environment": "incidentlab",
  "service": "payment",
  "severity": "critical",
  "alert_name": "PaymentServiceUnhealthy",
  "status": "firing",
  "labels": {
    "scenario": "C01",
    "fault": "service_crash"
  },
  "annotations": {
    "summary": "Payment service is unhealthy"
  }
}
```

This IncidentLab endpoint normalizes monitoring payloads. The main verified fault path sends its richer incident payload to the OpsSwarm monitoring ingress.

## OpsSwarm API

### Endpoint summary

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | OpsSwarm service health |
| GET | `/runs` | List in-memory/current run models |
| GET | `/runs/{issue_number}` | Get the run associated with a GitHub Issue |
| GET | `/runs/{issue_number}/evidence` | Read OpsSwarm evidence for a run |
| GET | `/runs/{issue_number}/checkpoint` | Read latest checkpoint |
| POST | `/runs/{issue_number}/resume` | Resume from the latest checkpoint metadata |
| POST | `/internal/issues/{issue_number}/start` | Start processing an eligible open Issue |
| POST | `/webhooks/github` | Receive signed GitHub Issue/comment webhooks |
| POST | `/hooks/monitoring` | Create a GitHub incident from monitoring ingress and start processing |

### POST /hooks/monitoring

The verified IncidentLab path sends a payload containing incident title, service, symptom, customer impact, environment, evidence details, and recovery context.

OpsSwarm:

1. Builds the GitHub Issue.
2. Applies configured base/severity labels.
3. Creates the Issue.
4. Starts the incident workflow in the background.
5. Returns the created Issue number.

Representative response:

```json
{
  "accepted": true,
  "issue_number": 123
}
```

### POST /webhooks/github

GitHub webhook deliveries are signature-validated against `GITHUB_WEBHOOK_SECRET`.

Handled events include:

- `issues.opened`
- `issue_comment.created`

Issue comments are used for human commands such as:

```text
/opsswarm approve <option-id>
```

OpsSwarm also checks the actor's repository permission before accepting protected commands.

### POST /internal/issues/{issue_number}/start

Starts an open Issue only when it has the configured required label. In the packaged demo, that label is:

```text
incidentlab
```

Duplicate starts for an already tracked Issue are treated idempotently.

## HTTP authentication boundary

The GitHub webhook endpoint has HMAC signature validation. The general IncidentLab and OpsSwarm HTTP endpoints do not implement a complete public-facing authentication layer in this demo stack.

Therefore:

- Keep them on a trusted host/network for local demos.
- Use firewall rules or security groups.
- Put any intentionally remote control surface behind an authenticated TLS reverse proxy.
- Do not expose the recovery endpoint directly to untrusted clients.

See [Security](SECURITY.md).
