from .models import utc_now
from .store import load, save

def add_snapshot(run_id, **snapshot):
    run = load(run_id)
    if not run: return None
    run.setdefault("timeline", []).append({"timestamp": utc_now(), **snapshot})
    run["service_state"] = snapshot.get("health")
    run["metrics_snapshot"] = snapshot.get("metrics")
    run["fault_state"] = {"fault": run["fault"], "state": run["state"]}
    save(run); return run
