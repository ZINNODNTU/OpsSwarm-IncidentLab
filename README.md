# OpsSwarm-IncidentLab

Stateful fault-injection and observability laboratory for testing incident-management systems such as OpsSwarm-Enterprise.

## Boundary

IncidentLab is the simulation layer. Enterprise is the orchestration layer.

Enterprise -> IncidentLab API -> Fault Injection -> Simulated Services -> Prometheus -> Alertmanager -> /hooks/monitoring -> Enterprise

IncidentLab contains no embedded OpsSwarm runtime, OpenClaw runtime, Enterprise skills/policy, GitHub orchestration, RCA engine, approval engine, or agent dispatch.

## Runtime

- auth, order, inventory, payment, booking-api simulators
- scenario catalog C01-C12
- fault injection and reset/recovery APIs
- Prometheus and Alertmanager
- normalized monitoring contract
- simulator-only evidence and timeline state

## API

GET /api/health
GET /api/scenarios
GET /api/scenarios/{scenario_id}
GET /api/services
GET /api/services/{service}/health
GET /api/services/{service}/metrics
GET /api/faults
POST /api/faults/inject
POST /api/faults/reset
POST /api/recovery/{service}
GET /api/evidence
GET /api/evidence/{run_id}
POST /api/reset
POST /hooks/monitoring

Fault injection is deterministic and never calls Enterprise or OpenClaw.

## Docker

The compose runtime contains only IncidentLab, simulator services, Prometheus, and Alertmanager. No GitHub/OpenClaw/Enterprise credentials are required.

## C01 E2E

1. baseline health
2. inject payment service_crash
3. verify payment unhealthy
4. verify metrics changed
5. verify Prometheus sees the failure
6. verify Alertmanager receives the alert
7. verify /hooks/monitoring contract
8. call recovery API
9. verify payment healthy
10. collect evidence
11. reset scenario
12. verify clean state

PASS is reported only when commands/tests actually succeed.
