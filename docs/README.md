# OpsSwarm Documentation

This directory is the canonical documentation set for the OpsSwarm IncidentLab repository.

## Recommended reading order

1. [Getting Started](GETTING_STARTED.md) — configure and start the unified Docker stack.
2. [Architecture](ARCHITECTURE.md) — understand the incident lifecycle, component boundaries, agent permissions, and evidence flow.
3. [Configuration](CONFIGURATION.md) — review secrets, ports, polling, OpenClaw, GitHub, and provider settings.
4. [Demo Guide](DEMO_GUIDE.md) — run the recommended end-to-end C03 demonstration.
5. [Scenario Catalog](SCENARIOS.md) — choose from C01-C12.
6. [API Reference](API_REFERENCE.md) — inspect IncidentLab and OpsSwarm endpoints.
7. [Security](SECURITY.md) — understand the trust model and recovery controls.
8. [Troubleshooting](TROUBLESHOOTING.md) — diagnose common setup and runtime problems.

## Documentation map

| Document | Audience | Focus |
| --- | --- | --- |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Developers, reviewers | System design, control flow, state and trust boundaries |
| [GETTING_STARTED.md](GETTING_STARTED.md) | Operators, evaluators | First deployment and health validation |
| [CONFIGURATION.md](CONFIGURATION.md) | Operators | Environment variables and runtime tuning |
| [DEMO_GUIDE.md](DEMO_GUIDE.md) | Presenters, judges | Competition/demo workflow and expected checkpoints |
| [SCENARIOS.md](SCENARIOS.md) | Testers | Fault catalog and expected outcomes |
| [API_REFERENCE.md](API_REFERENCE.md) | Integrators | HTTP surfaces and representative payloads |
| [SECURITY.md](SECURITY.md) | Security reviewers | Secret handling, agent permissions and recovery controls |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Operators | Failure diagnosis and recovery steps |

## Source-of-truth files

Documentation should remain consistent with these runtime sources:

- `docker-compose.yml` — services, ports, mounts, network boundaries and health checks.
- `.env.example` — supported user-facing environment configuration.
- `MANIFEST.json` — packaged agents, skills, version and upstream synchronization metadata.
- `experiments/scenarios.yaml` — C01-C12 scenario definitions.
- `platform/opsswarm/config/incidentlab-demo.yaml` — policy profile, GitHub labels, thresholds and OpenClaw role mapping.
- `platform/openclaw/openclaw.json` — agent model, workspace paths and tool restrictions.
- `incidentlab/api.py` — IncidentLab API, evidence and recovery enforcement.
- `platform/opsswarm/opsswarm/api.py` — orchestration, GitHub webhook and monitoring ingress endpoints.

## Documentation conventions

- The visible product name is **OpsSwarm**.
- **IncidentLab** refers to the fault-injection and evidence subsystem.
- **OpenClaw** and **GitHub** are runtime integrations, not product branding.
- Commands are written from the repository root unless stated otherwise.
- `localhost` examples are host-side examples; container-to-container communication uses Compose service DNS names.
- Generated `runtime-data/` content is evidence/runtime state, not source documentation.
