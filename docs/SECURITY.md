# Security

OpsSwarm is a controlled incident-simulation and agent-recovery environment. Its design limits what investigation agents can change and requires explicit policy decisions before recovery writes.

It should still be deployed as a **trusted lab/demo control plane**, not as an unauthenticated public Internet service.

## Security goals

The packaged environment is designed to preserve these properties:

1. Investigation cannot silently modify the repository.
2. Recovery writes are isolated to a dedicated responder role.
3. Runtime recovery is tied to the exact incident run.
4. Evidence is not writable from the recovery workspace.
5. Provider/GitHub secrets are not exposed through the mounted project view.
6. OpenClaw does not receive Docker daemon control.
7. GitHub-driven privileged actions are permission-checked.
8. Incident closure requires verification.

## Secret handling

Secrets belong in the repository-root `.env` file:

- `GITHUB_TOKEN`
- `GITHUB_WEBHOOK_SECRET`
- `OPENCLAW_GATEWAY_TOKEN`
- `MINIMAX_API_KEY`

Rules:

- Never commit `.env`.
- Never copy secrets into Issues, evidence records, README files, screenshots, or demo recordings.
- Use least-privilege GitHub access.
- Rotate credentials after any suspected disclosure.
- Use a long random OpenClaw gateway token.

The OpenClaw workspace does not receive the real host `.env`: each agent's project view has `platform/openclaw/blocked.env` over-mounted at `project/.env`.

## OpenClaw network exposure

The default host mapping is loopback-only:

```text
127.0.0.1:18789
```

OpsSwarm communicates with OpenClaw inside Docker using:

```text
http://openclaw:18789
```

Do not broaden the host binding to a public interface unless you have an explicit authentication, TLS, firewall, and network-segmentation design.

## Agent filesystem permissions

| Role | Repository view | Runtime evidence |
| --- | --- | --- |
| Incident manager | Read-only | Read through allowed sources |
| Observability investigator | Read-only | Read-only observation |
| Application investigator | Read-only | Read-only |
| Infrastructure investigator | Read-only | Read-only |
| Database investigator | Read-only | Read-only |
| Recovery responder | Read/write source view | `runtime-data` read-only |
| Communications/postmortem | Read-only | Read-only |

The recovery responder is the only packaged agent with a writable project mount.

The observability investigator can perform live read-only execution/network checks needed for verification, but its source tree remains read-only.

## No Docker socket in OpenClaw

The Compose configuration does **not** mount:

```text
/var/run/docker.sock
```

into OpenClaw.

This prevents the agent runtime from gaining direct Docker daemon control, which would otherwise effectively grant broad host/container privileges.

## Run-bound recovery

The IncidentLab recovery endpoint requires a request ID containing the exact target run:

```text
incidentlab-run-...
```

Before a state write, IncidentLab checks:

- The run exists.
- The run belongs to the requested service.
- The run is currently recoverable.
- There is not a newer active run for that service.
- The patch only contains writable persisted-state keys.

A stale recovery request receives HTTP 409.

This prevents a delayed action for incident A from mutating the service during incident B.

## Recovery patch allowlist

Writable keys come from the service's declared known-good baseline.

Derived fields such as health/status are not treated as mutable recovery state. Unknown non-derived keys are rejected.

This reduces the recovery API from "write arbitrary JSON" to "repair known persisted state."

## Evidence protection

The recovery responder's project view mounts:

```text
runtime-data/
```

read-only.

The intent is to keep generated evidence separate from the agent's source-write capability, so the same role that performs a repair cannot simply rewrite the evidence trail to make verification appear successful.

## Human approval and GitHub authority

The packaged policy is:

| Operation class | Decision |
| --- | --- |
| Read | `AUTO` |
| Safe write | `HUMAN_APPROVAL` |
| Risky write | `HUMAN_APPROVAL` |
| Destructive | `DENY` |

The configured minimum permission for approval is `maintain`.

GitHub comments that trigger protected commands are checked against repository permissions before execution.

## GitHub webhook validation

`POST /webhooks/github` validates the GitHub HMAC-SHA256 signature using `GITHUB_WEBHOOK_SECRET`.

If webhooks are used:

- Configure the same secret in GitHub and `.env`.
- Use HTTPS for Internet-delivered webhooks.
- Do not disable signature checks to simplify a public deployment.

The polling fallback can be used for demos that do not expose a webhook receiver publicly.

## HTTP control-plane exposure

Important limitation: the general IncidentLab and OpsSwarm HTTP APIs are not a complete authenticated public control plane.

In particular, endpoints for fault injection, reset, evidence, monitoring ingress, run access, and recovery rely on network/deployment trust rather than a comprehensive application-level authentication scheme.

For any shared server:

- Restrict inbound ports with host/cloud firewall rules.
- Expose only the minimum required endpoints.
- Put externally needed routes behind an authenticated TLS reverse proxy.
- Limit source IPs when possible.
- Do not make `/api/recovery/*`, `/api/reset`, or `/hooks/monitoring` directly public without additional controls.
- Consider separating read-only UI routes from write/control routes.

## Simulator source reload

IncidentLab, OpsSwarm, and the simulator services use source reload mounts in the demonstration stack so an approved source repair can become active without Docker daemon access.

This is appropriate for a controlled demonstration environment. For a production-style deployment, prefer immutable images and an explicit build/deploy pipeline for source changes.

## GitHub token guidance

The GitHub token should have only the repository permissions needed by the workflow. At minimum, the workflow needs to interact with Issues and inspect user/repository permission information.

Avoid organization-wide or account-wide tokens when a repository-scoped credential can satisfy the use case.

## Provider credential guidance

`MINIMAX_API_KEY` is injected into the OpenClaw container as an environment variable. Do not expose container environment output in public logs or recordings.

If changing providers, preserve the same principle: provider credentials belong in deployment secret configuration, not tracked OpenClaw workspace files.

## Public/server deployment checklist

Before placing the stack on a server outside a single trusted workstation:

- [ ] `.env` is not committed or included in the distributable archive.
- [ ] GitHub token uses least privilege.
- [ ] A strong `OPENCLAW_GATEWAY_TOKEN` is configured.
- [ ] `GITHUB_WEBHOOK_SECRET` is configured if using webhooks.
- [ ] OpenClaw remains loopback-only on the host.
- [ ] Firewall/security groups restrict 8080, 8088, 8001-8005, 9090, and 9093 as appropriate.
- [ ] Externally required endpoints use TLS.
- [ ] Reverse-proxy authentication protects control routes.
- [ ] Simulator/service ports are not exposed publicly without a reason.
- [ ] Logs and recordings are reviewed for credentials.
- [ ] Recovery/evidence mount permissions pass `server-smoke.sh` or the competition preflight.

## Reporting a security issue

Do not publish credentials, exploit details against a live deployment, or private incident evidence in a public GitHub Issue. Use the repository owner's private security reporting channel when one is available.
