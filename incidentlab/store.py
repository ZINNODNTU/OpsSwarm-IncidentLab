import json, os, uuid
from pathlib import Path
from .models import utc_now

ROOT = Path(os.getenv("INCIDENTLAB_DATA_DIR", "runtime-data/incidentlab"))
RUNS = ROOT / "runs"
RUNS.mkdir(parents=True, exist_ok=True)

def new_run(scenario_id: str, service: str, fault: str) -> dict:
    run = {"run_id": f"incidentlab-run-{uuid.uuid4().hex[:12]}", "scenario_id": scenario_id, "service": service, "fault": fault, "started_at": utc_now(), "state": "fault_injected", "timeline": [], "recovery_events": []}
    save(run)
    return run

def load(run_id: str) -> dict | None:
    p = RUNS / f"{run_id}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

def save(run: dict) -> None:
    (RUNS / f"{run['run_id']}.json").write_text(json.dumps(run, indent=2), encoding="utf-8")

def all_runs() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(RUNS.glob("*.json"))]
