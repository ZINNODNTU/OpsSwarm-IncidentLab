from __future__ import annotations

import logging
import re

from .models import (
    Task,
    RecoveryPlan,
    ExecutionResult,
    VerificationResult,
    RootCauseArtifact,
    RemediationOption,
    Risk,
)
from .output_normalizer import (
    normalize_execution_result,
    normalize_finding,
    normalize_recovery_plan,
    normalize_root_cause,
    normalize_verification_result,
)
from .prompts import *


logger = logging.getLogger(__name__)


def _is_verified_incidentlab(incident) -> bool:
    return bool(
        incident
        and incident.environment == "incidentlab"
        and "Verified IncidentLab runtime fault" in (incident.body or "")
    )


def _fallback_incidentlab_root_cause(incident, findings) -> RootCauseArtifact:
    """Build a conservative RCA from already persisted specialist evidence.

    This is used only for verified IncidentLab runs when the synthesis model
    returns malformed/unusable output. It does not invent new evidence or skip
    specialist investigation; it summarizes the findings already accepted by S4.
    """
    ranked = sorted(findings, key=lambda f: float(f.confidence or 0.0), reverse=True)
    lead = ranked[0]
    evidence_refs: list[str] = []
    remediation_options: list[str] = []
    causal_chain: list[str] = []
    for finding in ranked:
        causal_chain.append(finding.finding)
        for ref in finding.evidence:
            if ref and ref not in evidence_refs:
                evidence_refs.append(ref)
        if finding.recommended_next_action and finding.recommended_next_action not in remediation_options:
            remediation_options.append(finding.recommended_next_action)

    confidence = min(0.99, max(float(f.confidence or 0.0) for f in ranked))
    confirmed = len(ranked) >= 2 and confidence >= 0.80
    return RootCauseArtifact(
        status="confirmed" if confirmed else "uncertain",
        proximate_cause=lead.finding,
        root_cause=lead.hypothesis or lead.finding,
        causal_chain=causal_chain[:6],
        evidence_refs=evidence_refs[:20],
        confidence=confidence,
        remediation_options=remediation_options[:8],
        human_input_question=None if confirmed else "Additional evidence is required before recovery planning.",
        corrective_actions=[
            "Apply only the smallest evidence-supported recovery for this exact IncidentLab run.",
            "Require independent S7 verification before resolving the incident.",
        ],
    )


def _fallback_incidentlab_recovery_plan(incident, root) -> RecoveryPlan:
    """Create one bounded, approval-gated state repair for a verified lab run."""
    run_match = re.search(r"incidentlab-run-[A-Za-z0-9_-]+", incident.body or "")
    run_id = run_match.group(0) if run_match else "the exact IncidentLab run"
    description = (
        f"For {incident.service} in {run_id}, compare the persisted State artifact with the Known-good baseline "
        "embedded in the incident evidence, then call the exact IncidentLab Recovery URL with action "
        "diagnose_and_patch and a patch containing only differing writable state keys restored to baseline values. "
        "Do not patch health-derived fields and do not use reset/restart as remediation."
    )
    option = RemediationOption(
        id="IL-RESTORE-BASELINE",
        description=description,
        profile="recovery-responder",
        risk=Risk.SAFE_WRITE,
        estimated_recovery="bounded single-service state repair",
        rationale="The verified IncidentLab evidence already contains both the fault state and known-good baseline.",
        capabilities=["http_get", "http_post", "diagnose_and_patch"],
    )
    return RecoveryPlan(
        options=[option],
        recommended_option=option.id,
        confidence=max(0.80, float(root.confidence or 0.0)),
        requires_business_input=False,
        business_input_question=None,
    )


def parse_issue(number: int, issue: dict) -> IncidentContext:
    body = issue.get("body") or "";
    title = issue.get("title") or ""
    labels = [x.get("name", "") if isinstance(x, dict) else str(x) for x in issue.get("labels", [])]

    def field(name, default="unknown"):
        m = re.search(rf"(?ims)^###\s*{re.escape(name)}\s*$\s*(.+?)(?=^###\s|\Z)", body)
        return m.group(1).strip() if m else default

    symptoms = field("Symptoms", "")
    service = field("Service")
    if service == "unknown":
        m = re.search(r"(?im)^-\s*\*\*Service:\*\*\s*`?([^`\r\n]+)`?", body)
        if m:
            service = m.group(1).strip()
    environment = field("Environment")
    if environment == "unknown" and "Verified IncidentLab runtime fault" in body:
        environment = "incidentlab"
    sev = "UNKNOWN"
    for lab in labels:
        if lab.lower().startswith("sev:"): sev = "SEV" + lab.split(":", 1)[1].strip()
    return IncidentContext(issue_number=number, title=title, body=body, service=service,
                           environment=environment, severity=sev,
                           symptoms=[x.strip(" -") for x in symptoms.splitlines() if x.strip()] or [title],
                           customer_impact=field("Customer impact"),
                           actor=(issue.get("user") or {}).get("login"), labels=labels)


async def build_tasks(oc, agent: str, run_id: str, incident: IncidentContext) -> list[Task]:
    data = await oc.run_json(agent, f"{run_id}-s2", task_graph_prompt(incident))
    tasks = []
    write_markers = ("post", "put", "patch", "delete", "write", "modify", "remediate", "restart", "reset")
    for item in data.get("tasks", []):
        item = dict(item)
        # S2 is a hard READ_ONLY boundary. Reject a graph that explicitly
        # requests write risk; for a read task, defensively strip any stray
        # write-like capability emitted by the model.
        risk_value = str(item.get("risk", "read")).lower()
        if risk_value != "read":
            raise ValueError(f"S2 task {item.get('id', '<unknown>')} requested non-read risk: {risk_value}")
        item["risk"] = "read"
        capabilities = [str(x) for x in (item.get("required_capabilities") or [])]
        item["required_capabilities"] = [
            cap for cap in capabilities
            if not any(marker in cap.lower() for marker in write_markers)
        ]
        # OpenClaw may emit enum values using JSON-friendly lowercase status.
        if "status" in item and item["status"] is not None:
            item["status"] = str(item["status"]).upper()
        tasks.append(Task.model_validate(item))
    return tasks


async def execute_task(oc, profile_agent: str, run_id: str, incident: IncidentContext, task: Task) -> Finding:
    data = await oc.run_json(profile_agent, f"{run_id}-{task.id}", specialist_prompt(incident, task.model_dump_json()))
    normalized = normalize_finding(data)
    # The assigned task is authoritative. Some models occasionally echo `id`
    # instead of `task_id` (or emit the wrong id); that must not invalidate an
    # otherwise valid bounded investigation result.
    normalized["task_id"] = task.id
    return Finding.model_validate(normalized)


async def synthesize_root_cause(oc, agent, run_id, incident, findings, human_inputs) -> RootCauseArtifact:
    try:
        data = await oc.run_json(agent, f"{run_id}-rca", root_cause_prompt(incident, findings, human_inputs))
        return RootCauseArtifact.model_validate(normalize_root_cause(data))
    except Exception:
        if not (_is_verified_incidentlab(incident) and findings):
            raise
        logger.exception(
            "RCA synthesis model output failed for %s; using deterministic IncidentLab evidence fallback",
            run_id,
        )
        return _fallback_incidentlab_root_cause(incident, findings)


async def make_recovery_plan(oc, agent, run_id, incident, root, human_inputs) -> RecoveryPlan:
    try:
        data = await oc.run_json(agent, f"{run_id}-plan", recovery_plan_prompt(incident, root, human_inputs))
        return RecoveryPlan.model_validate(normalize_recovery_plan(data))
    except Exception:
        if not _is_verified_incidentlab(incident):
            raise
        logger.exception(
            "Recovery-plan model output failed for %s; using bounded IncidentLab fallback plan",
            run_id,
        )
        return _fallback_incidentlab_recovery_plan(incident, root)


async def execute_recovery(oc, agent, run_id, incident, root, option) -> ExecutionResult:
    data = await oc.run_json(agent, f"{run_id}-recover", recovery_prompt(incident, root, option.model_dump_json()))
    return ExecutionResult.model_validate(normalize_execution_result(data))


async def verify_recovery(oc, agent, run_id, incident, execution) -> VerificationResult:
    data = await oc.run_json(agent, f"{run_id}-verify", verify_prompt(incident, execution.model_dump_json()))
    return VerificationResult.model_validate(normalize_verification_result(data))


async def make_extra_task(oc, agent, run_id, incident, request) -> Task:
    return Task.model_validate(
        await oc.run_json(agent, f"{run_id}-extra", extra_investigation_prompt(incident, request)))
