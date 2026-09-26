# Demo Guide

This guide describes the recommended end-to-end OpsSwarm demonstration using **C03 — Bad deployment**.

C03 is a useful presentation scenario because the baseline and faulty service versions are easy to observe, the fault persists until repaired, and the recovery path demonstrates the human approval gate before verification.

## Demo objective

Show that OpsSwarm can move from a proven runtime failure to a governed, evidence-backed recovery:

```text
verified fault
  -> GitHub Issue
  -> S1/S2/S4 specialist investigation
  -> evidence aggregation + RCA
  -> S3 recovery plan
  -> human policy gate
  -> authorized recovery
  -> S7 independent verification
  -> postmortem + Issue closure
```

The packaged demo uses sequential specialist dispatch (`max_parallel_investigators: 1`) for deterministic behavior.

## 1. Prepare the environment

Start the stack:

```bat
scripts\demo-start.cmd
```

Run the preflight:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\competition-preflight.ps1
```

For the strongest pre-demo validation:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\competition-preflight.ps1 -FullTests
```

Do not begin the presentation until the preflight reports `PREFLIGHT PASS`.

## 2. Establish the healthy baseline

Open:

```text
http://localhost:8080
```

Show that the simulator services are healthy before fault injection.

For C03, the target is `payment`, whose known-good version is `v2.0`.

Useful API checks:

```text
GET http://localhost:8080/api/services/payment/health
GET http://localhost:8080/api/services/payment/state
GET http://localhost:8080/api/services/payment/baseline
```

## 3. Start C03

Run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\demo-e2e.ps1 -Scenario C03
```

The script asks IncidentLab to inject:

```text
service: payment
fault:   bad_deployment
value:   v2.1
```

IncidentLab captures a healthy baseline first, mutates the persisted state, and verifies that the fault has a real runtime effect. If fault verification does not pass, the run is rejected and the GitHub incident path does not proceed.

## 4. Show the GitHub system of record

After verification, the script prints:

- IncidentLab `run_id`.
- GitHub Issue number.
- GitHub Issue URL.

Open the Issue and show the incident context. The Issue becomes the human-visible system of record for investigation state, decisions, approval, and final resolution.

OpsSwarm also tracks the active run at:

```text
GET http://localhost:8088/runs/<issue-number>
```

## 5. Explain the investigation phase

The expected logical skill flow is:

| Skill | Role in the demo |
| --- | --- |
| S1 Intent Guard | Normalizes the incident and guards the execution intent |
| S2 Task Graph | Builds the investigation work graph |
| S4 Role Dispatch | Routes investigation work to the specialist roles |
| S5 Collaboration/Execution | Coordinates task execution and evidence exchange |
| S6 Resilience Guard | Applies resilience/failure-handling safeguards |
| S3 Horizon Plan | Produces the bounded recovery plan from the RCA |
| S7 Observe/Verify | Independently checks the post-recovery system |
| S8 Orchestration Hub | Coordinates the broader lifecycle |

Specialist findings are aggregated before root-cause analysis and recovery planning.

During the demo, emphasize that investigator workspaces are read-only. Investigation cannot silently modify the project.

## 6. Demonstrate the human gate

With the packaged policy, safe and risky writes require human approval.

When the run reaches `WAITING_APPROVAL`, the script prints a command similar to:

```text
/opsswarm approve <option-id>
```

Post exactly that command as a GitHub Issue comment using an account with the required repository permission.

This checkpoint demonstrates that analysis may be autonomous while a write remains human-governed.

### Optional automated demo approval

If GitHub CLI is authenticated and you want the script to post the approval comment:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\demo-e2e.ps1 -Scenario C03 -Approve
```

This automates the presentation action, not the policy decision model: the run still passes through `WAITING_APPROVAL`.

## 7. Show recovery

For C03, the recovery responder should compare the current payment state with the known-good baseline and restore the diagnosed bad persisted key.

The runtime recovery endpoint requires a request tied to the exact IncidentLab run. A stale request for an older payment incident is rejected.

Relevant evidence:

```text
GET /api/evidence/<run_id>
GET /api/services/payment/health
GET /api/services/payment/metrics
GET /api/services/payment/probe
GET /api/services/payment/state
GET /api/services/payment/baseline
```

## 8. Show independent verification

After recovery, do not stop at "the write succeeded."

Show that OpsSwarm enters verification and that IncidentLab re-checks:

- Service health.
- HTTP success.
- A real workload probe.
- Persisted state restoration.
- The C03-specific version restoration check.

For C03, payment should return to `v2.0`.

## 9. Final success criteria

A successful demo should end with:

```text
OpsSwarm state: RESOLVED
GitHub Issue state: CLOSED
Recovery: success
S7 verified: true
IncidentLab verification: PASS
```

If verification fails, the correct behavior is not to claim success; the incident should remain unresolved/open for further action.

## 10. Suggested presentation sequence

A concise live sequence is:

1. **Architecture (20-30s):** IncidentLab -> OpsSwarm -> GitHub -> OpenClaw -> governed recovery.
2. **Skills (about 30s):** explain the main purpose of S1, S2, S3, S4, S7 and S8.
3. **Healthy baseline:** show the services.
4. **Inject C03:** show the payment version/runtime fault.
5. **GitHub Issue:** show automatic creation and incident context.
6. **Investigation/RCA:** show run state and specialist findings.
7. **Human decision:** post the approval command.
8. **Recovery:** show the payment state restored.
9. **Verification:** show S7/IncidentLab PASS.
10. **Closure:** show GitHub Issue closed with the final record.

## 11. Reset between demonstrations

Before another scenario, restore the lab:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8080/api/reset
```

Then confirm all services are healthy:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/api/services
```

This avoids carrying persisted state from one scenario into another.

## 12. Other scenarios

See [Scenario Catalog](SCENARIOS.md) for C01-C12. C12 is particularly useful when demonstrating that OpsSwarm should not accept a recovery-looking transition without independent verification.
