from __future__ import annotations

import re

from .models import Task, RecoveryPlan, ExecutionResult, VerificationResult
from .output_normalizer import (
    normalize_execution_result,
    normalize_finding,
    normalize_recovery_plan,
    normalize_root_cause,
    normalize_verification_result,
)
from .prompts import *


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
    data = await oc.run_json(agent, f"{run_id}-rca", root_cause_prompt(incident, findings, human_inputs))
    return RootCauseArtifact.model_validate(normalize_root_cause(data))


async def make_recovery_plan(oc, agent, run_id, incident, root, human_inputs) -> RecoveryPlan:
    data = await oc.run_json(agent, f"{run_id}-plan", recovery_plan_prompt(incident, root, human_inputs))
    return RecoveryPlan.model_validate(normalize_recovery_plan(data))


async def execute_recovery(oc, agent, run_id, incident, root, option) -> ExecutionResult:
    data = await oc.run_json(agent, f"{run_id}-recover", recovery_prompt(incident, root, option.model_dump_json()))
    return ExecutionResult.model_validate(normalize_execution_result(data))


async def verify_recovery(oc, agent, run_id, incident, execution) -> VerificationResult:
    data = await oc.run_json(agent, f"{run_id}-verify", verify_prompt(incident, execution.model_dump_json()))
    return VerificationResult.model_validate(normalize_verification_result(data))


async def make_extra_task(oc, agent, run_id, incident, request) -> Task:
    return Task.model_validate(
        await oc.run_json(agent, f"{run_id}-extra", extra_investigation_prompt(incident, request)))
