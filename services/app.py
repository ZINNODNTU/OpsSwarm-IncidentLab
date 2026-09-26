import json
import os
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.responses import JSONResponse, Response

SERVICE = os.getenv("SERVICE_NAME", "service")
DEFAULT_VERSION = os.getenv("DEFAULT_VERSION", "v1.0")
STATE_DIR = Path(os.getenv("STATE_DIR", "/app/state"))
STATE_FILE = STATE_DIR / "state.json"
app = FastAPI(title=f"DemoMart {SERVICE}")

BASELINE_STATE = {
    "version": DEFAULT_VERSION,
    "crash": False,
    "error_rate": 0.002,
    "latency_ms": 180,
    "cpu_percent": 15,
    "memory_percent": 25,
    "db_down": False,
    "db_pool_exhausted": False,
    "external_timeout": False,
    "telemetry_missing": False,
}
state = dict(BASELINE_STATE)


class Fault(BaseModel):
    fault: str
    enabled: bool = True
    value: float | int | str | None = None


class Version(BaseModel):
    version: str


class StatePatch(BaseModel):
    patch: dict[str, object]


def _persist_state():
    """Persist the service fault configuration so faults survive container restarts."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, STATE_FILE)


def _reload_state():
    """Reload the persisted configuration before serving health/workload requests."""
    global state
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if not STATE_FILE.exists():
        state = dict(BASELINE_STATE)
        _persist_state()
        return
    try:
        loaded = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("state artifact must be a JSON object")
        state = {**BASELINE_STATE, **loaded}
        state.pop("_config_error", None)
    except Exception as exc:
        # A malformed persisted config is a real runtime fault as well.
        state = dict(BASELINE_STATE)
        state["_config_error"] = f"{type(exc).__name__}: {exc}"


def _artifact():
    return {
        "service": SERVICE,
        "artifact_path": str(STATE_FILE),
        "persisted": STATE_FILE.exists(),
        "state": dict(state),
    }


_reload_state()


def healthy():
    return not any([
        bool(state.get("_config_error")),
        state["crash"],
        state["db_down"],
        state["db_pool_exhausted"],
        state["external_timeout"],
        state["telemetry_missing"],
        float(state["error_rate"]) >= 0.30,
        int(state["latency_ms"]) >= 1000,
        int(state["cpu_percent"]) >= 90,
        int(state["memory_percent"]) >= 90,
        state["version"] != DEFAULT_VERSION,
    ])


@app.get("/health")
def health():
    _reload_state()
    payload = {
        "service": SERVICE,
        "healthy": healthy(),
        "version": state["version"],
        "status": "UP" if healthy() else "DEGRADED",
        "active_faults": {
            "config_error": state.get("_config_error"),
            "crash": state["crash"],
            "db_down": state["db_down"],
            "db_pool_exhausted": state["db_pool_exhausted"],
            "external_timeout": state["external_timeout"],
            "telemetry_missing": state["telemetry_missing"],
            "error_rate_high": float(state["error_rate"]) >= 0.30,
            "latency_high": int(state["latency_ms"]) >= 1000,
            "cpu_high": int(state["cpu_percent"]) >= 90,
            "memory_high": int(state["memory_percent"]) >= 90,
            "deployment_mismatch": state["version"] != DEFAULT_VERSION,
        },
        "state_artifact": str(STATE_FILE),
        "state_persisted": STATE_FILE.exists(),
    }
    return JSONResponse(status_code=200 if payload["healthy"] else 503, content=payload)


@app.get("/workload")
def workload():
    """Exercise a real request path so injected faults are observable beyond metadata."""
    _reload_state()
    started = time.perf_counter()

    if state.get("_config_error"):
        raise HTTPException(status_code=500, detail=f"{SERVICE}: invalid persisted service state: {state['_config_error']}")

    # C01 raises a real application exception. The control/admin endpoints stay
    # reachable so an external incident responder can repair and verify it.
    if state["crash"]:
        raise RuntimeError(f"Injected service crash in {SERVICE} workload handler")

    if state["db_down"]:
        raise HTTPException(status_code=503, detail=f"{SERVICE}: database unavailable")
    if state["db_pool_exhausted"]:
        raise HTTPException(status_code=503, detail=f"{SERVICE}: database connection pool exhausted")
    if state["external_timeout"]:
        time.sleep(2.5)
        raise HTTPException(status_code=504, detail=f"{SERVICE}: upstream gateway timeout")

    latency_ms = int(state["latency_ms"])
    if latency_ms > 180:
        # Bound the delay so a lab scenario cannot wedge the control plane.
        time.sleep(min(latency_ms, 5000) / 1000.0)

    if state["version"] != DEFAULT_VERSION:
        raise HTTPException(status_code=500, detail=f"{SERVICE}: deployment regression on {state['version']}")
    if float(state["error_rate"]) >= 0.30:
        raise HTTPException(status_code=500, detail=f"{SERVICE}: injected request failure")
    if int(state["cpu_percent"]) >= 90:
        raise HTTPException(status_code=503, detail=f"{SERVICE}: overloaded by CPU saturation")
    if int(state["memory_percent"]) >= 90:
        raise HTTPException(status_code=503, detail=f"{SERVICE}: overloaded by memory pressure")

    return {
        "service": SERVICE,
        "ok": True,
        "version": state["version"],
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        "telemetry_present": not state["telemetry_missing"],
    }


@app.get("/metrics-json")
def metrics_json():
    _reload_state()
    d = {
        "service": SERVICE,
        "version": state["version"],
        "healthy": healthy(),
        "error_rate": float(state["error_rate"]),
        "success_rate": max(0.0, 1.0 - float(state["error_rate"])),
        "latency_ms": int(state["latency_ms"]),
        "cpu_percent": int(state["cpu_percent"]),
        "memory_percent": int(state["memory_percent"]),
        "db_down": state["db_down"],
        "db_pool_exhausted": state["db_pool_exhausted"],
        "external_timeout": state["external_timeout"],
        "telemetry_present": not state["telemetry_missing"],
        "state_artifact": str(STATE_FILE),
        "state_persisted": STATE_FILE.exists(),
    }
    if state["telemetry_missing"]:
        d.pop("error_rate", None)
        d.pop("success_rate", None)
    return d


@app.get("/metrics")
def metrics():
    _reload_state()
    h = 1 if healthy() else 0
    telemetry = 0 if state["telemetry_missing"] else 1
    version = str(state["version"]).replace('"', "")
    lines = [
        "# HELP demomart_service_healthy Whether the service is healthy (1/0).",
        "# TYPE demomart_service_healthy gauge",
        f'demomart_service_healthy{{service="{SERVICE}"}} {h}',
        "# HELP demomart_telemetry_present Whether required telemetry is present (1/0).",
        "# TYPE demomart_telemetry_present gauge",
        f'demomart_telemetry_present{{service="{SERVICE}"}} {telemetry}',
        "# HELP demomart_service_info Service version information.",
        "# TYPE demomart_service_info gauge",
        f'demomart_service_info{{service="{SERVICE}",version="{version}"}} 1',
        "# HELP demomart_cpu_percent Simulated CPU saturation percentage.",
        "# TYPE demomart_cpu_percent gauge",
        f'demomart_cpu_percent{{service="{SERVICE}"}} {state["cpu_percent"]}',
        "# HELP demomart_memory_percent Simulated memory pressure percentage.",
        "# TYPE demomart_memory_percent gauge",
        f'demomart_memory_percent{{service="{SERVICE}"}} {state["memory_percent"]}',
        "# HELP demomart_latency_ms Simulated application latency in milliseconds.",
        "# TYPE demomart_latency_ms gauge",
        f'demomart_latency_ms{{service="{SERVICE}"}} {state["latency_ms"]}',
    ]
    if not state["telemetry_missing"]:
        e = float(state["error_rate"])
        s = max(0.0, 1.0 - e)
        lines += [
            "# HELP demomart_error_rate Simulated request error ratio.",
            "# TYPE demomart_error_rate gauge",
            f'demomart_error_rate{{service="{SERVICE}"}} {e}',
            "# HELP demomart_success_rate Simulated request success ratio.",
            "# TYPE demomart_success_rate gauge",
            f'demomart_success_rate{{service="{SERVICE}"}} {s}',
        ]
    return Response("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")


@app.post("/admin/fault")
def fault(req: Fault):
    _reload_state()
    if req.fault not in state:
        raise HTTPException(400, "unknown fault")
    if req.fault in {"error_rate", "latency_ms", "cpu_percent", "memory_percent"}:
        defaults = {
            "error_rate": 0.002,
            "latency_ms": 180,
            "cpu_percent": 15,
            "memory_percent": 25,
        }
        if req.enabled and req.value is None:
            raise HTTPException(400, "value is required")
        state[req.fault] = req.value if req.enabled else defaults[req.fault]
    else:
        state[req.fault] = bool(req.enabled)
    _persist_state()
    return {"service": SERVICE, "state": state, "artifact": _artifact()}


@app.post("/admin/version")
def version(req: Version):
    _reload_state()
    state["version"] = req.version
    _persist_state()
    return {"service": SERVICE, "version": state["version"], "artifact": _artifact()}


@app.get("/admin/state")
def admin_state():
    _reload_state()
    return _artifact()


@app.get("/admin/baseline")
def admin_baseline():
    return {"service": SERVICE, "baseline": dict(BASELINE_STATE)}


@app.post("/admin/patch")
def admin_patch(req: StatePatch):
    """Apply an explicit bounded config repair. The caller must diagnose the bad keys."""
    _reload_state()
    allowed = set(BASELINE_STATE)
    unknown = sorted(set(req.patch) - allowed)
    if unknown:
        raise HTTPException(400, f"unsupported state keys: {unknown}")
    if not req.patch:
        raise HTTPException(400, "patch must contain at least one state key")
    for key, value in req.patch.items():
        state[key] = value
    _persist_state()
    return {"service": SERVICE, "patch_applied": req.patch, "artifact": _artifact(), "healthy": healthy()}


@app.post("/admin/repair")
def repair():
    """Repair the persisted service configuration back to the known-good baseline."""
    global state
    state = dict(BASELINE_STATE)
    _persist_state()
    return {"service": SERVICE, "repair": "persisted-config-restored", "artifact": _artifact()}


@app.post("/admin/reset")
def reset():
    # Backward-compatible alias used by lab reset scripts.
    return repair()
