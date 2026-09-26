from __future__ import annotations

import json

from .models import IncidentContext, Finding, RootCauseArtifact

JSON_ONLY = ("Return ONLY one standards-compliant JSON object. No markdown fences and no prose outside JSON. "
             "Use double-quoted keys/strings, escape quotes and control characters inside string values, "
             "and do not use comments or trailing commas.")


def task_graph_prompt(incident: IncidentContext) -> str:
    return f'''You are OpsSwarm S2 TaskGraph. Create the minimum investigation DAG needed to diagnose this incident.
Allowed task types: OBSERVE, INVESTIGATE, DIAGNOSE. Do not create REMEDIATE tasks yet.
Allowed profiles: observability-investigator, application-investigator, infrastructure-investigator, database-investigator.
All initial tasks MUST be read-only. `required_capabilities` MUST contain read-only capabilities only (for example http_get); NEVER include http_post, write, reset, restart, patch, delete or remediation capabilities in S2 tasks. Use dependencies and parallel work when useful.
For a Verified IncidentLab runtime fault, keep the DAG minimal (normally 3-4 tasks): live health/workload/evidence checks followed by one diagnosis. Do not re-investigate facts already proven by the supplied runtime evidence.
Return an object with key "tasks"; each task has: id,type,objective,profile,required_capabilities,risk,depends_on,parallelizable,expected_output,status.
Risk must be "read".
{JSON_ONLY}
Incident:\n{incident.model_dump_json(indent=2)}'''


def specialist_prompt(incident: IncidentContext, task_json: str) -> str:
    return f'''You are an OpsSwarm specialist working on one bounded incident task.
Do only the assigned task. Respect READ_ONLY scope. Do not perform remediation or writes.
Use available OpenClaw tools to gather real evidence. If a tool is unavailable, say so rather than fabricate evidence.
For IncidentLab incidents, first use the Immutable verified evidence snapshot embedded in the GitHub Issue as authoritative read-only evidence. Live Evidence/Health/Metrics/Workload URLs are optional corroboration only when reachable; never invent an internal hostname or lower confidence merely because a private URL is blocked when the immutable snapshot already contains the required evidence.
Return JSON with: task_id, finding, evidence (array of concrete refs/observations), hypothesis, confidence (0..1), recommended_next_action, raw (object).
{JSON_ONLY}
Incident:\n{incident.model_dump_json(indent=2)}\nTask:\n{task_json}'''


def root_cause_prompt(incident: IncidentContext, findings: list[Finding], human_inputs: list[dict]) -> str:
    return f'''You are OpsSwarm root-cause synthesis. Distinguish proximate cause from root cause.
Do not claim confirmed root cause unless evidence supports it. Never fabricate enterprise facts.
Return JSON fields: status (confirmed|uncertain), proximate_cause, root_cause, causal_chain[], evidence_refs[], confidence, remediation_options[], human_input_question|null, corrective_actions[].
If missing business knowledge prevents a sound decision, set status=uncertain and ask one concrete human_input_question.
{JSON_ONLY}
Incident:\n{incident.model_dump_json(indent=2)}\nFindings:\n{json.dumps([f.model_dump() for f in findings], ensure_ascii=False, default=str)}\nHuman inputs:\n{json.dumps(human_inputs, ensure_ascii=False)}'''


def recovery_plan_prompt(incident: IncidentContext, root: RootCauseArtifact, human_inputs: list[dict]) -> str:
    return f'''You are OpsSwarm S3 recovery planner. Propose only evidence-supported remediation options.
Return JSON with: options[], recommended_option|null, confidence, requires_business_input, business_input_question|null.
Each option: id,description,profile="recovery-responder",risk(read|safe_write|risky_write|destructive),estimated_recovery|null,rationale,capabilities[].
Use destructive only when the action is actually destructive. If key business constraints are missing, set requires_business_input=true.
For a Verified IncidentLab runtime fault with an explicit persisted state artifact, Known-good baseline URL and Recovery URL, make a bounded diagnose-and-patch repair of that exact service/run a safe_write option. The responder must compare the persisted State artifact's `state` object against the Baseline `baseline` object and patch only keys that exist in BOTH of those writable objects. Health-derived fields such as `active_faults`, `deployment_mismatch`, `healthy`, `status`, and `http_status` are verification signals, not writable state keys, and MUST NEVER be included in the patch object. Preserve the exact State/Baseline/Recovery URLs in the option description or capabilities. A restart/reset alone is not valid because the fault state is bind-mounted and survives restart.\nIf and only if the RCA instead proves a source/configuration defect in the packaged OpsSwarm-IncidentLab repository, a remediation option may authorize a direct source repair. Such an option MUST name the exact file(s) or bounded component to change, state that the recovery responder should work under its `project/` workspace, require the smallest evidence-supported edit, and require focused tests plus live health/workload verification. Do not propose source edits merely to repair an injected persisted-state fault.
{JSON_ONLY}
Incident:\n{incident.model_dump_json(indent=2)}\nRoot cause:\n{root.model_dump_json(indent=2)}\nHuman inputs:\n{json.dumps(human_inputs, ensure_ascii=False)}'''


def recovery_prompt(incident: IncidentContext, root: RootCauseArtifact, option_json: str) -> str:
    return f'''You are OpsSwarm recovery-responder. Execute ONLY the authorized remediation option below using available OpenClaw tools.
Do not broaden scope. Preserve idempotency where supported. If transport becomes ambiguous after a write, do not blindly repeat it.
For IncidentLab runtime-state faults, use the immutable State/Baseline snapshot in the Issue to diagnose the smallest set of differing writable keys. A key is writable only if it appears in BOTH the persisted State artifact's `state` object and the Baseline `baseline` object. Never put health-derived fields (`active_faults`, `deployment_mismatch`, `healthy`, `status`, `http_status`) into the patch. For localhost/private IncidentLab URLs, use the exec tool with curl.exe/curl rather than web_fetch when web_fetch blocks private addresses. POST the exact Recovery URL with action `diagnose_and_patch`, the supplied request_id, and a `patch` object containing only those diagnosed persisted-state keys restored to baseline values. Do not use restart/reset as remediation and do not invent a hostname. After the write, GET State, Health and Workload with curl.exe/curl and capture the responses as evidence. If the patch is incomplete or wrong, report failure rather than masking it with a reset.\nIf the authorized option explicitly calls for a direct source/configuration repair, work only inside `project/`. Inspect the cited files and tests, make the smallest authorized edit, never read or modify `.env` or `runtime-data`, run the smallest relevant test first, then verify the affected live health/workload endpoint. Do not convert a runtime-state repair into a source edit, and do not broaden the source repair beyond the files/component named by the authorized option.
Return JSON: option_id,success,summary,evidence[],ambiguous,raw.
{JSON_ONLY}
Incident:\n{incident.model_dump_json(indent=2)}\nRoot cause:\n{root.model_dump_json(indent=2)}\nAuthorized option:\n{option_json}'''


def verify_prompt(incident: IncidentContext, execution_json: str) -> str:
    return f'''You are OpsSwarm S7 independent verifier. Independently check whether customer/business service health is restored.
Do not accept the executor's success claim as proof. Use read-only evidence from metrics, health checks, logs or service state.
For IncidentLab, independently call the exact State artifact, Known-good baseline, Health and Workload probe URLs in the incident/Issue. For localhost/private URLs, use the exec tool with curl.exe/curl rather than web_fetch when web_fetch blocks private addresses. Verification requires freshly read persisted state to match baseline and both Health and Workload probes to be healthy/HTTP 2xx; the executor's evidence is context only, not proof.
Return JSON: verified,summary,evidence[],confidence,raw.
{JSON_ONLY}
Incident:\n{incident.model_dump_json(indent=2)}\nExecution result (context only; not proof):\n{execution_json}'''


def extra_investigation_prompt(incident: IncidentContext, request: str) -> str:
    return f'''You are OpsSwarm S2. Convert this human-requested additional investigation into exactly one READ_ONLY task.
Choose one profile from observability-investigator, application-investigator, infrastructure-investigator, database-investigator.
Return a task object with id="HX1", type="INVESTIGATE", objective, profile, required_capabilities[], risk="read", depends_on=[], parallelizable=false, expected_output="Finding", status="PENDING".
{JSON_ONLY}\nIncident:\n{incident.model_dump_json(indent=2)}\nHuman request:\n{request}'''
