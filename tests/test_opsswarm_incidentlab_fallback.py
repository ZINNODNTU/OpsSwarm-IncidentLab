from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "platform" / "opsswarm"))

from opsswarm.models import Finding, IncidentContext, Risk
from opsswarm.skill_logic import make_recovery_plan, synthesize_root_cause


class BrokenOpenClaw:
    async def run_json(self, *args, **kwargs):
        raise ValueError("malformed RCA output")


def incident() -> IncidentContext:
    return IncidentContext(
        issue_number=120,
        title="[IncidentLab] payment: bad_deployment (C03)",
        body=(
            "## Incident\n\n"
            "### Service\n"
            "payment\n\n"
            "### Environment\n"
            "incidentlab\n\n"
            "## Verified IncidentLab runtime fault\n"
            "- **Run:** `incidentlab-run-abc123`\n"
        ),
        service="payment",
        environment="incidentlab",
        symptoms=["Verified bad deployment"],
        customer_impact="Synthetic lab workload failing",
    )


def findings() -> list[Finding]:
    return [
        Finding(
            task_id="IL-APP",
            finding="payment v2.1 differs from known-good v2.0",
            evidence=["state.version=v2.1", "baseline.version=v2.0"],
            hypothesis="A bad deployment changed the payment version from v2.0 to v2.1.",
            confidence=0.98,
            recommended_next_action="Restore only the version key to the baseline value.",
        ),
        Finding(
            task_id="IL-OBS",
            finding="payment is DEGRADED and workload returns HTTP 500",
            evidence=["health=DEGRADED", "workload_http=500"],
            hypothesis="The deployment regression is causing the runtime failure.",
            confidence=0.95,
            recommended_next_action="Verify health and workload after bounded recovery.",
        ),
    ]


@pytest.mark.asyncio
async def test_incidentlab_rca_uses_evidence_fallback_when_model_output_fails():
    root = await synthesize_root_cause(
        BrokenOpenClaw(),
        "opsswarm-incident-manager",
        "RUN-GH-120-demo",
        incident(),
        findings(),
        [],
    )

    assert root.status == "confirmed"
    assert root.confidence >= 0.98
    assert "v2.1" in root.root_cause
    assert "state.version=v2.1" in root.evidence_refs


@pytest.mark.asyncio
async def test_incidentlab_plan_fallback_is_single_bounded_safe_write():
    plan = await make_recovery_plan(
        BrokenOpenClaw(),
        "opsswarm-incident-manager",
        "RUN-GH-120-demo",
        incident(),
        await synthesize_root_cause(
            BrokenOpenClaw(),
            "opsswarm-incident-manager",
            "RUN-GH-120-demo",
            incident(),
            findings(),
            [],
        ),
        [],
    )

    assert len(plan.options) == 1
    assert plan.recommended_option == "IL-RESTORE-BASELINE"
    assert plan.options[0].risk == Risk.SAFE_WRITE
    assert "incidentlab-run-abc123" in plan.options[0].description
    assert "diagnose_and_patch" in plan.options[0].description
