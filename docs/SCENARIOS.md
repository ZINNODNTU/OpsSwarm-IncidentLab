# Scenario Catalog

The canonical scenario definitions live in `experiments/scenarios.yaml`. IncidentLab validates the requested service and fault against that catalog before injection.

## Scenario matrix

| ID | Scenario | Service | Fault | Injected value | Expected alert | Expected state | Recovery |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C01 | Payment service crash | `payment` | `service_crash` | — | `PaymentServiceUnhealthy` | `unhealthy` | `diagnose_and_patch` |
| C02 | Payment error spike | `payment` | `error_rate` | `0.43` | `PaymentErrorRateHigh` | `degraded` | `diagnose_and_patch` |
| C03 | Bad deployment | `payment` | `bad_deployment` | `v2.1` | `PaymentDeploymentMismatch` | `degraded` | `diagnose_and_patch` |
| C04 | Database unavailable | `order` | `db_down` | `true` | `OrderDatabaseUnavailable` | `unhealthy` | `diagnose_and_patch` |
| C05 | DB connection exhaustion | `order` | `db_pool_exhausted` | `true` | `OrderDatabasePoolExhausted` | `unhealthy` | `diagnose_and_patch` |
| C06 | API latency | `auth` | `latency_ms` | `2000` | `AuthLatencyHigh` | `degraded` | `diagnose_and_patch` |
| C07 | CPU saturation | `inventory` | `cpu_percent` | `97` | `InventoryCPUSaturation` | `degraded` | `diagnose_and_patch` |
| C08 | Memory pressure | `inventory` | `memory_percent` | `95` | `InventoryMemoryPressure` | `degraded` | `diagnose_and_patch` |
| C09 | External gateway timeout | `payment` | `external_timeout` | `true` | `PaymentGatewayTimeout` | `unhealthy` | `diagnose_and_patch` |
| C10 | Duplicate monitoring alerts | `payment` | `duplicate_alerts` | `true` | `PaymentServiceUnhealthy` | `duplicate-events` | `monitoring_deduplication` |
| C11 | Missing telemetry | `payment` | `telemetry_missing` | `true` | `PaymentTelemetryMissing` | `telemetry-degraded` | `diagnose_and_patch` |
| C12 | False recovery | `payment` | `error_rate` | `0.43` | `PaymentErrorRateHigh` | `degraded` | `diagnose_and_patch` |

## Scenario behavior

### C01 — Payment service crash

Purpose: verify that the system detects and responds to an actual unhealthy payment service rather than a synthetic event with no runtime impact.

Expected recovery evidence:

- Payment health returns to healthy.
- HTTP/workload checks pass.
- Persisted service state matches the baseline.

### C02 — Payment error spike

Purpose: drive the payment error ratio above the alert threshold.

Injected value:

```text
error_rate = 0.43
```

Verification requires the error rate to return to the known-good baseline.

### C03 — Bad deployment

Purpose: simulate an unhealthy deployment version.

Injected value:

```text
payment version: v2.0 -> v2.1
```

This is the recommended general demonstration because the faulty and restored states are easy to explain visually.

Verification requires the service version to match the baseline again.

### C04 — Database unavailable

Purpose: simulate database connectivity loss for the order service.

Verification requires the database-down condition to be cleared and the order service to return healthy.

### C05 — DB connection exhaustion

Purpose: model an exhausted database connection pool.

Verification requires the pool-exhausted condition to clear and the service to recover.

### C06 — API latency

Purpose: introduce material latency into the auth service.

Injected value:

```text
latency_ms = 2000
```

IncidentLab verifies both degraded state and real workload latency rather than trusting the requested value alone.

### C07 — CPU saturation

Purpose: simulate high CPU utilization in inventory.

Injected value:

```text
cpu_percent = 97
```

Verification requires CPU to return to the baseline range.

### C08 — Memory pressure

Purpose: simulate high memory utilization in inventory.

Injected value:

```text
memory_percent = 95
```

Verification requires memory utilization to return to the baseline range.

### C09 — External gateway timeout

Purpose: simulate an upstream dependency timeout for payment.

Verification requires the timeout condition to clear and payment to be healthy.

### C10 — Duplicate monitoring alerts

Purpose: test monitoring-event deduplication behavior.

Unlike the runtime-state scenarios, C10 is monitoring-oriented. Its fault verification mode checks the monitoring contract rather than requiring a service outage.

### C11 — Missing telemetry

Purpose: remove required application telemetry while the service remains reachable.

Verification requires `telemetry_present` to return to true.

### C12 — False recovery

Purpose: demonstrate why recovery verification must be independent.

The payment error rate remains elevated after a recovery-looking transition. The system should not accept that transition as successful merely because an action completed; health/metrics verification must still pass.

## Fault injection contract

A request to `POST /api/faults/inject` must match the selected scenario's configured `service` and `fault`.

For example, C03 accepts:

```json
{
  "scenario_id": "C03",
  "service": "payment",
  "fault": "bad_deployment",
  "duration_seconds": 900,
  "auto_reset": false,
  "metadata": {
    "requested_by": "demo"
  }
}
```

A request that names C03 but substitutes another service or fault is rejected.

## Verification before orchestration

For runtime scenarios, IncidentLab captures and validates:

- Known-good baseline health.
- Baseline metrics.
- Baseline workload probe.
- Baseline persisted state.
- Post-injection health/metrics/workload.
- Persisted-state mutation.

If the requested fault is accepted by the simulator but IncidentLab cannot prove a real runtime effect, injection is treated as failed and the normal incident orchestration path does not proceed.

## Persistence

Scenario state is persisted in:

```text
runtime-data/service-state/<service>/state.json
```

This is intentional: restarting a container must not magically erase an active fault. Recovery should repair the diagnosed bad state or use an explicitly authorized source/config repair.

## Choosing a scenario

| Goal | Suggested scenario |
| --- | --- |
| General end-to-end demo | C03 |
| Service outage | C01 |
| Metrics-based degradation | C02, C06, C07, C08 |
| Database investigation | C04, C05 |
| Dependency failure | C09 |
| Monitoring deduplication | C10 |
| Telemetry failure | C11 |
| Verification / false-positive recovery | C12 |
