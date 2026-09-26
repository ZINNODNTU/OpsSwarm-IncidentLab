import asyncio
import json
import os
import re
import httpx
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from .models import FaultInjectRequest, RecoveryRequest, MonitoringEvent, utc_now
from .scenarios import scenarios, get
from .simulator import get_health, get_metrics, get_state_artifact, get_baseline, probe_workload, inject, reset, apply_patch
from .store import new_run, load, save, all_runs
from .evidence import add_snapshot

app=FastAPI(title="OpsSwarm-IncidentLab",version="1.0.0")

GITHUB_API="https://api.github.com"
GITHUB_REPO=os.getenv("GITHUB_REPO","ZINNODNTU/OpsSwarm-IncidentLab")
GITHUB_TOKEN=os.getenv("GITHUB_TOKEN","").strip()
INCIDENTLAB_PUBLIC_URL=os.getenv("INCIDENTLAB_PUBLIC_URL","http://127.0.0.1:8080").rstrip("/")
INCIDENTLAB_FALLBACK_URL=os.getenv("INCIDENTLAB_FALLBACK_URL","http://incidentlab:8080").rstrip("/")
OPSSWARM_URL=os.getenv("OPSSWARM_URL","http://host.docker.internal:8088").rstrip("/")

DERIVED_RECOVERY_KEYS={
    "deployment_mismatch",
    "healthy",
    "status",
    "http_status",
    "active_faults",
    "service",
    "persisted",
    "artifact_path",
}


def _sanitize_recovery_patch(requested_patch:dict, baseline_payload:dict):
    """Keep only persisted state keys; health/derived flags are verification-only."""
    baseline_state=(baseline_payload or {}).get("baseline") or {}
    allowed=set(baseline_state)
    clean={k:v for k,v in (requested_patch or {}).items() if k in allowed}
    ignored=sorted(k for k in (requested_patch or {}) if k not in allowed and k in DERIVED_RECOVERY_KEYS)
    unsupported=sorted(k for k in (requested_patch or {}) if k not in allowed and k not in DERIVED_RECOVERY_KEYS)
    return clean, ignored, unsupported


RECOVERABLE_RUN_STATES={"fault_injected","recovering","verification_failed"}

def _select_recovery_run(service:str, request_id:str):
    """Bind every recovery write to the exact IncidentLab run named by request_id."""
    match=re.search(r"incidentlab-run-[A-Za-z0-9]+", request_id or "")
    if not match:
        raise HTTPException(400,"request_id must include the target incidentlab run id")
    target_run_id=match.group(0)
    target=load(target_run_id)
    if not target:
        raise HTTPException(404,f"target run not found: {target_run_id}")
    if target.get("service") != service:
        raise HTTPException(409,"recovery request service does not match target run")
    if target.get("state") not in RECOVERABLE_RUN_STATES:
        raise HTTPException(409,f"target run is not recoverable: {target.get('state')}")

    active=[r for r in all_runs() if r.get("service")==service and r.get("state") in RECOVERABLE_RUN_STATES]
    active.sort(key=lambda r:r.get("started_at", ""), reverse=True)
    if active and active[0].get("run_id") != target_run_id:
        raise HTTPException(409,f"stale recovery request; newer active run exists: {active[0].get('run_id')}")
    return target


def _baseline_snapshot(run):
    for item in run.get("timeline", []):
        if item.get("event") == "baseline":
            return item
    return {}


def _verify_recovery(run, health, metrics, workload=None, artifact=None):
    baseline=_baseline_snapshot(run)
    base_health=baseline.get("health") or {}
    base_metrics=baseline.get("metrics") or {}
    fault=run.get("fault")
    checks={
        "service_healthy": bool(health.get("healthy")),
        "health_http_2xx": int(health.get("http_status", 500)) < 400,
    }
    if workload is not None:
        checks["workload_http_2xx"]=bool(workload.get("ok")) and int(workload.get("http_status") or 500) < 400
    baseline_artifact=baseline.get("artifact") or {}
    if artifact is not None and baseline_artifact:
        checks["persisted_artifact_restored"]=artifact.get("state")==baseline_artifact.get("state")
    if fault=="bad_deployment":
        checks["version_restored"]=health.get("version")==base_health.get("version")
    elif fault=="error_rate":
        checks["error_rate_restored"]=float(metrics.get("error_rate", 1.0)) <= float(base_metrics.get("error_rate", 0.002)) + 1e-9
    elif fault=="latency_ms":
        checks["latency_restored"]=int(metrics.get("latency_ms", 10**9)) <= int(base_metrics.get("latency_ms", 180))
    elif fault=="cpu_percent":
        checks["cpu_restored"]=int(metrics.get("cpu_percent", 100)) <= int(base_metrics.get("cpu_percent", 15))
    elif fault=="memory_percent":
        checks["memory_restored"]=int(metrics.get("memory_percent", 100)) <= int(base_metrics.get("memory_percent", 25))
    elif fault=="db_down":
        checks["database_restored"]=not bool(metrics.get("db_down", True))
    elif fault=="db_pool_exhausted":
        checks["db_pool_restored"]=not bool(metrics.get("db_pool_exhausted", True))
    elif fault=="external_timeout":
        checks["gateway_restored"]=not bool(metrics.get("external_timeout", True))
    elif fault=="telemetry_missing":
        checks["telemetry_restored"]=bool(metrics.get("telemetry_present"))
    return {
        "status":"PASS" if all(checks.values()) else "FAIL",
        "checks":checks,
        "verified_at":utc_now(),
    }


def _verify_fault_effect(fault, value, health, metrics, workload):
    if fault == "duplicate_alerts":
        return {"status":"PASS","mode":"monitoring_only","checks":{"monitoring_contract":True},"verified_at":utc_now()}

    health_degraded=not bool(health.get("healthy", True))
    checks={"health_degraded":health_degraded}
    if fault == "latency_ms":
        target=min(float(value or 1000), 5000.0)
        checks["real_workload_latency"] = float(workload.get("elapsed_ms") or 0) >= max(500.0, target * 0.70)
    elif fault == "telemetry_missing":
        checks["telemetry_missing"] = metrics.get("telemetry_present") is False
    else:
        status=workload.get("http_status")
        checks["real_workload_failure"] = (status is not None and int(status) >= 500) or not bool(workload.get("reachable", True))
    return {"status":"PASS" if all(checks.values()) else "FAIL","mode":"runtime","checks":checks,"health":health,"metrics":metrics,"workload":workload,"verified_at":utc_now()}


async def create_github_issue(run_id, scenario_id, service, fault, duration_seconds, metadata=None):
    if not GITHUB_TOKEN:
        return {"enabled":False,"status":"NOT_CONFIGURED"}
    issue_payload={"run_id":run_id,"scenario_id":scenario_id,"service":service,"fault":fault,"duration_seconds":duration_seconds,"created_at":utc_now(),"metadata":metadata or {}}
    runtime_candidates=list(dict.fromkeys([INCIDENTLAB_PUBLIC_URL,INCIDENTLAB_FALLBACK_URL]))
    body=(
        "## Incident\n\n"
        "### Service\n"
        f"{service}\n\n"
        "### Symptoms\n"
        f"Verified IncidentLab runtime fault: {fault} ({scenario_id}). Health/workload effect was proven before Issue creation.\n\n"
        "### Customer impact\n"
        f"Synthetic IncidentLab workload for {service} is degraded or failing until recovery is verified.\n\n"
        "### Environment\n"
        "incidentlab\n\n"
        "### Verified runtime fault\n"
        f"- **Run:** `{run_id}`\n"
        f"- **Scenario:** `{scenario_id}`\n"
        f"- **Service:** `{service}`\n"
        f"- **Fault:** `{fault}`\n"
        "- **Fault effect:** verified before this Issue was created\n\n"
        "### Live investigation / recovery contract\n"
        f"- Evidence: `{INCIDENTLAB_PUBLIC_URL}/api/evidence/{run_id}`\n"
        f"- Health: `{INCIDENTLAB_PUBLIC_URL}/api/services/{service}/health`\n"
        f"- Metrics: `{INCIDENTLAB_PUBLIC_URL}/api/services/{service}/metrics`\n"
        f"- Workload probe: `{INCIDENTLAB_PUBLIC_URL}/api/services/{service}/probe`\n"
        f"- Persisted state artifact: `{INCIDENTLAB_PUBLIC_URL}/api/services/{service}/state`\n"
        f"- Known-good baseline: `{INCIDENTLAB_PUBLIC_URL}/api/services/{service}/baseline`\n"
        f"- Host evidence file: `runtime-data/service-state/{service}/state.json` (bind-mounted into the service container)\n"
        f"- Recovery: `POST {INCIDENTLAB_PUBLIC_URL}/api/recovery/{service}` with JSON `{{\"action\":\"diagnose_and_patch\",\"request_id\":\"opsswarm-{run_id}\",\"patch\":{{...only diagnosed keys...}}}}`\n"
        "- Recovery does NOT auto-reset. The agent must compare state vs baseline and patch the actual bad key(s). A restart alone must not clear the fault.\n"
        f"- Runtime URL fallbacks: `{runtime_candidates}`\n\n"
        "### Machine-readable incident payload\n```json\n"
        + json.dumps(issue_payload,indent=2,ensure_ascii=False)
        + "\n```"
    )
    headers={"Accept":"application/vnd.github+json","Authorization":f"Bearer {GITHUB_TOKEN}","X-GitHub-Api-Version":"2022-11-28","User-Agent":"OpsSwarm-IncidentLab"}
    async with httpx.AsyncClient(timeout=10) as client:
        r=await client.post(f"{GITHUB_API}/repos/{GITHUB_REPO}/issues",headers=headers,json={"title":f"[IncidentLab] {service}: {fault} ({scenario_id})","body":body,"labels":["opsswarm","incident","incidentlab"]})
    if r.status_code>=300: raise RuntimeError(f"GitHub issue creation failed: HTTP {r.status_code}: {r.text[:1000]}")
    d=r.json()
    return {"enabled":True,"status":"CREATED","issue_number":d.get("number"),"issue_url":d.get("html_url")}


async def dispatch_to_opsswarm(run_id, scenario_id, service, fault, duration_seconds, fault_verification, metadata=None):
    """Send a verified live fault into OpsSwarm so Issue creation and OpenClaw processing start together."""
    recovery_url=f"{INCIDENTLAB_PUBLIC_URL}/api/recovery/{service}"
    request_id=f"opsswarm-{run_id}"
    stored_run=load(run_id) or {}
    baseline=_baseline_snapshot(stored_run)
    fault_snapshot={}
    for item in reversed(stored_run.get("timeline", [])):
        if item.get("event") == "fault_effect_verified":
            fault_snapshot=item
            break
    immutable_evidence={
        "run_id":run_id,
        "scenario_id":scenario_id,
        "service":service,
        "fault":fault,
        "baseline":{
            "health":baseline.get("health"),
            "metrics":baseline.get("metrics"),
            "workload":baseline.get("workload"),
            "artifact":baseline.get("artifact"),
        },
        "fault":{
            "health":fault_snapshot.get("health") or fault_verification.get("health"),
            "metrics":fault_snapshot.get("metrics") or fault_verification.get("metrics"),
            "workload":fault_snapshot.get("workload") or fault_verification.get("workload"),
            "artifact":fault_snapshot.get("artifact"),
            "verification":fault_verification,
        },
    }
    evidence_json=json.dumps(immutable_evidence,indent=2,ensure_ascii=False)
    details=(
        "## Verified IncidentLab runtime fault\n\n"
        f"- **Run:** `{run_id}`\n"
        f"- **Scenario:** `{scenario_id}`\n"
        f"- **Service:** `{service}`\n"
        f"- **Fault:** `{fault}`\n"
        "- **Fault effect:** verified against the live service before orchestration\n\n"
        "### Immutable verified evidence snapshot\n"
        "This JSON was captured by IncidentLab before OpsSwarm/OpenClaw investigation began. Use it as authoritative read-only evidence if live private URLs are unreachable.\n\n"
        "```json\n" + evidence_json + "\n```\n\n"
        "### Live investigation / recovery contract\n"
        f"- Evidence: `{INCIDENTLAB_PUBLIC_URL}/api/evidence/{run_id}`\n"
        f"- Health: `{INCIDENTLAB_PUBLIC_URL}/api/services/{service}/health`\n"
        f"- Metrics: `{INCIDENTLAB_PUBLIC_URL}/api/services/{service}/metrics`\n"
        f"- Workload probe: `{INCIDENTLAB_PUBLIC_URL}/api/services/{service}/probe`\n"
        f"- Persisted state artifact: `{INCIDENTLAB_PUBLIC_URL}/api/services/{service}/state`\n"
        f"- Known-good baseline: `{INCIDENTLAB_PUBLIC_URL}/api/services/{service}/baseline`\n"
        f"- Host evidence file: `runtime-data/service-state/{service}/state.json` (bind-mounted into the service container)\n"
        f"- Recovery URL: `{recovery_url}`\n"
        f"- Recovery body template: `{{\"action\":\"diagnose_and_patch\",\"request_id\":\"{request_id}\",\"patch\":{{...only diagnosed keys...}}}}`\n"
        "- The recovery endpoint does NOT auto-reset. Compare live state to baseline, patch only the diagnosed bad key(s), then verify state + health + workload.\n"
    )
    payload={
        "title":f"[IncidentLab] {service}: {fault} ({scenario_id})",
        "service":service,
        "symptom":f"Verified IncidentLab runtime fault {fault} in run {run_id}",
        "customer_impact":"Synthetic lab workload is failing; bounded recovery for this isolated run is explicitly authorized.",
        "environment":"incidentlab",
        "observed_since":utc_now(),
        "severity_label":"sev:2",
        "details_markdown":details,
        "incidentlab":{
            "run_id":run_id,
            "scenario_id":scenario_id,
            "service":service,
            "fault":fault,
            "duration_seconds":duration_seconds,
            "fault_verification":fault_verification,
            "metadata":metadata or {},
        },
    }
    async with httpx.AsyncClient(timeout=10) as client:
        r=await client.post(f"{OPSSWARM_URL}/hooks/monitoring",json=payload)
    if r.status_code>=300:
        raise RuntimeError(f"OpsSwarm monitoring ingress failed: HTTP {r.status_code}: {r.text[:1000]}")
    d=r.json()
    number=d.get("issue_number")
    return {
        "enabled":True,
        "status":"ACCEPTED",
        "url":OPSSWARM_URL,
        "issue_number":number,
        "issue_url":f"https://github.com/{GITHUB_REPO}/issues/{number}" if number else None,
        "accepted":bool(d.get("accepted")),
    }


@app.get("/api/health")
def health(): return {"ok":True,"service":"incidentlab","role":"fault-simulation-observability","timestamp":utc_now()}

@app.get("/api/scenarios")
def list_scenarios(): return scenarios()

@app.get("/api/scenarios/{scenario_id}")
def scenario(scenario_id:str):
    item=get(scenario_id)
    if not item: raise HTTPException(404,"scenario not found")
    return item

@app.get("/api/services")
async def services():
    result=[]
    for name in ["auth","order","inventory","payment","booking-api"]:
        try: result.append(await get_health(name))
        except Exception as exc: result.append({"service":name,"healthy":False,"status":"UNREACHABLE","error":type(exc).__name__})
    return result

@app.get("/api/services/{service}/health")
async def service_health(service:str):
    try: return await get_health(service)
    except Exception as exc: raise HTTPException(503,f"service unavailable: {exc}")

@app.get("/api/services/{service}/metrics")
async def service_metrics(service:str):
    try: return await get_metrics(service)
    except Exception as exc: raise HTTPException(503,f"metrics unavailable: {exc}")

@app.get("/api/services/{service}/probe")
async def service_probe(service:str):
    return await probe_workload(service)


@app.get("/api/services/{service}/state")
async def service_state(service:str):
    try: return await get_state_artifact(service)
    except Exception as exc: raise HTTPException(503,f"state artifact unavailable: {exc}")


@app.get("/api/services/{service}/baseline")
async def service_baseline(service:str):
    try: return await get_baseline(service)
    except Exception as exc: raise HTTPException(503,f"baseline unavailable: {exc}")


@app.get("/api/faults")
def faults(): return {"supported":["service_crash","crash","error_rate","bad_deployment","db_down","db_pool_exhausted","latency_ms","cpu_percent","memory_percent","external_timeout","telemetry_missing","duplicate_alerts"]}

@app.get("/api/integrations/github")
def github_status():
    return {"enabled":bool(GITHUB_TOKEN),"repo":GITHUB_REPO,"issue_creation":"ready" if GITHUB_TOKEN else "not_configured"}


@app.get("/api/integrations/opsswarm")
async def opsswarm_status():
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r=await client.get(f"{OPSSWARM_URL}/health")
        data=r.json() if r.headers.get("content-type","").startswith("application/json") else {}
        return {"enabled":r.status_code<400 and bool(data.get("ok",True)),"url":OPSSWARM_URL,"http_status":r.status_code,"health":data}
    except Exception as exc:
        return {"enabled":False,"url":OPSSWARM_URL,"error":f"{type(exc).__name__}: {exc}"}

@app.post("/api/faults/inject")
async def fault_inject(req:FaultInjectRequest):
    sc=get(req.scenario_id)
    if not sc: raise HTTPException(404,"scenario not found")
    if sc.get("service")!=req.service or sc.get("fault")!=req.fault: raise HTTPException(400,"request does not match scenario contract")

    run=new_run(req.scenario_id,req.service,req.fault)
    baseline_artifact={}
    try:
        # Every experiment must begin from the service's declared known-good
        # baseline. Persisted fault state can survive container restarts, so
        # repair stale state before capturing the before-snapshot.
        declared=await get_baseline(req.service)
        current_health=await get_health(req.service)
        current_artifact=await get_state_artifact(req.service)
        expected_state=(declared or {}).get("baseline") or {}
        current_state=(current_artifact or {}).get("state") or {}
        if (not bool(current_health.get("healthy"))) or (expected_state and current_state != expected_state):
            await reset(req.service)
            add_snapshot(run["run_id"],event="pre_injection_baseline_repaired",previous_health=current_health,previous_artifact=current_artifact)

        baseline_health=await get_health(req.service)
        baseline_metrics=await get_metrics(req.service)
        baseline_workload=await probe_workload(req.service)
        baseline_artifact=await get_state_artifact(req.service)
        if not bool(baseline_health.get("healthy")):
            raise RuntimeError("service is not healthy after baseline repair")
        if expected_state and baseline_artifact.get("state") != expected_state:
            raise RuntimeError("persisted state does not match declared baseline after repair")
        add_snapshot(run["run_id"],health=baseline_health,metrics=baseline_metrics,workload=baseline_workload,artifact=baseline_artifact,event="baseline")
    except Exception as exc:
        add_snapshot(run["run_id"],event="baseline_capture_failed",error=str(exc))
        run=load(run["run_id"]) or run
        run["state"]="baseline_failed"
        run["error"]=str(exc)
        save(run)
        raise HTTPException(502,f"could not establish known-good baseline: {exc}")

    try:
        await inject(req.service,req.fault,sc.get("value",True))
    except Exception as exc:
        run=load(run["run_id"]) or run
        run["state"]="injection_failed"
        run["error"]=str(exc)
        save(run)
        raise HTTPException(502,f"fault injection failed: {exc}")

    run=load(run["run_id"]) or run
    run["state"]="fault_injected"
    run["injected_at"]=utc_now()
    run["auto_reset"]=req.auto_reset
    run["duration_seconds"]=req.duration_seconds
    save(run)

    fault_verification={"status":"FAIL","mode":"runtime","checks":{},"verified_at":utc_now()}
    try:
        fault_health=await get_health(req.service)
        fault_metrics=await get_metrics(req.service)
        fault_workload=await probe_workload(req.service)
        fault_artifact=await get_state_artifact(req.service)
        fault_verification=_verify_fault_effect(req.fault,sc.get("value",True),fault_health,fault_metrics,fault_workload)
        if req.fault != "duplicate_alerts":
            fault_verification.setdefault("checks",{})["persisted_artifact_mutated"]=fault_artifact.get("state") != baseline_artifact.get("state")
            fault_verification["status"]="PASS" if all(fault_verification["checks"].values()) else "FAIL"
        add_snapshot(run["run_id"],health=fault_health,metrics=fault_metrics,workload=fault_workload,artifact=fault_artifact,event="fault_effect_verified" if fault_verification["status"]=="PASS" else "fault_effect_failed",fault_verification=fault_verification)
    except Exception as exc:
        fault_verification={"status":"FAIL","mode":"runtime","checks":{},"error":str(exc),"verified_at":utc_now()}
        add_snapshot(run["run_id"],event="fault_snapshot_failed",error=str(exc),fault_verification=fault_verification)

    run=load(run["run_id"]) or run
    run["fault_verification"]=fault_verification
    save(run)
    if fault_verification.get("status") != "PASS":
        try: await reset(req.service)
        except Exception: pass
        run=load(run["run_id"]) or run
        run["state"]="injection_failed"
        run["error"]="fault command was accepted but no real runtime effect was verified"
        save(run)
        raise HTTPException(502,"fault injection was not verified against live service runtime; GitHub Issue was not created")

    if req.auto_reset:
        asyncio.create_task(_auto_reset(req.service,run["run_id"],req.duration_seconds))

    github={"enabled":False,"status":"NOT_ATTEMPTED"}
    opsswarm={"enabled":False,"status":"NOT_ATTEMPTED","url":OPSSWARM_URL}
    try:
        opsswarm=await dispatch_to_opsswarm(
            run["run_id"],
            req.scenario_id,
            req.service,
            req.fault,
            req.duration_seconds,
            fault_verification,
            {
                **req.metadata,
                "auto_reset":req.auto_reset,
                "evidence_file":run.get("evidence_file"),
                "runtime_url":INCIDENTLAB_PUBLIC_URL,
            },
        )
        github={
            "enabled":True,
            "status":"CREATED_BY_OPSSWARM" if opsswarm.get("issue_number") else "ACCEPTED_BY_OPSSWARM",
            "issue_number":opsswarm.get("issue_number"),
            "issue_url":opsswarm.get("issue_url"),
        }
    except Exception as exc:
        opsswarm={"enabled":False,"status":"UNAVAILABLE","url":OPSSWARM_URL,"error":str(exc)}
        try:
            github=await create_github_issue(
                run["run_id"],
                req.scenario_id,
                req.service,
                req.fault,
                req.duration_seconds,
                {
                    **req.metadata,
                    "auto_reset":req.auto_reset,
                    "evidence_file":run.get("evidence_file"),
                    "fault_verification":fault_verification,
                    "runtime_url":INCIDENTLAB_PUBLIC_URL,
                    "orchestration_fallback_reason":str(exc),
                },
            )
        except Exception as github_exc:
            github={"enabled":bool(GITHUB_TOKEN),"status":"FAILED","error":str(github_exc)}
    run=load(run["run_id"]) or run
    run["github"]=github
    run["opsswarm"]=opsswarm
    save(run)
    return {
        "accepted":True,
        "run_id":run["run_id"],
        "scenario_id":req.scenario_id,
        "service":req.service,
        "fault":req.fault,
        "state":"fault_injected",
        "auto_reset":req.auto_reset,
        "evidence_file":run.get("evidence_file"),
        "fault_verification":fault_verification,
        "opsswarm":opsswarm,
        "github":github,
    }

async def _auto_reset(service,run_id,seconds):
    await asyncio.sleep(seconds)
    try:
        await reset(service)
        health=await get_health(service)
        metrics=await get_metrics(service)
        workload=await probe_workload(service)
        artifact=await get_state_artifact(service)
    except Exception:
        return
    run=load(run_id)
    if run:
        verification=_verify_recovery(run,health,metrics,workload,artifact)
        run["state"]="auto_recovered" if verification["status"]=="PASS" else "verification_failed"
        run["recovered_at"]=utc_now()
        run["verification"]=verification
        run.setdefault("recovery_events",[]).append({"timestamp":utc_now(),"request_id":"auto-reset","action":"auto_reset"})
        save(run)
        add_snapshot(run_id,health=health,metrics=metrics,workload=workload,artifact=artifact,event="auto_recovered",verification=verification)

@app.post("/api/faults/reset")
async def fault_reset(req:dict):
    service=req.get("service")
    if not service: raise HTTPException(400,"service is required")
    try: result=await reset(service)
    except Exception as exc: raise HTTPException(502,str(exc))
    return {"accepted":True,"service":service,"state":"reset","result":result}

@app.post("/api/recovery/{service}")
async def recovery(service:str,req:RecoveryRequest):
    if req.action != "diagnose_and_patch":
        raise HTTPException(400,"recovery requires action=diagnose_and_patch; restart/reset is not accepted as a fix")
    if not req.patch:
        raise HTTPException(400,"patch is required; diagnose the persisted state against baseline first")
    run=_select_recovery_run(service,req.request_id)
    run_id=run["run_id"]
    try:
        baseline_payload=await get_baseline(service)
        patch,ignored_derived_keys,unsupported_keys=_sanitize_recovery_patch(req.patch,baseline_payload)
        if unsupported_keys:
            raise HTTPException(400,f"unsupported recovery patch keys: {unsupported_keys}")
        if not patch:
            raise HTTPException(400,"patch contains no writable persisted-state keys")
        patch_result=await apply_patch(service,patch)
        health=await get_health(service)
        metrics=await get_metrics(service)
        workload=await probe_workload(service)
        artifact=await get_state_artifact(service)
    except HTTPException:
        raise
    except httpx.HTTPStatusError as exc:
        status=exc.response.status_code
        detail=exc.response.text[:1000] or str(exc)
        raise HTTPException(status if 400 <= status < 500 else 502,detail) from exc
    except Exception as exc:
        raise HTTPException(502,str(exc))

    verification=_verify_recovery(run,health,metrics,workload,artifact)
    run["state"]="recovered" if verification["status"]=="PASS" else "verification_failed"
    run["recovered_at"]=utc_now()
    run["verification"]=verification
    run.setdefault("recovery_events",[]).append({"timestamp":utc_now(),"request_id":req.request_id,"action":req.action,"requested_patch":req.patch,"patch":patch,"ignored_derived_keys":ignored_derived_keys})
    save(run)
    add_snapshot(run["run_id"],health=health,metrics=metrics,workload=workload,artifact=artifact,event="recovered",verification=verification)
    return {
        "accepted":True,
        "request_id":req.request_id,
        "run_id":run_id,
        "service":service,
        "action":req.action,
        "requested_patch":req.patch,
        "patch":patch,
        "ignored_derived_keys":ignored_derived_keys,
        "patch_result":patch_result,
        "state":"recovered" if verification.get("status")=="PASS" else "verification_failed",
        "verification":verification,
    }

@app.get("/api/evidence")
def evidence(): return all_runs()

@app.get("/api/evidence/{run_id}")
def evidence_run(run_id:str):
    run=load(run_id)
    if not run: raise HTTPException(404,"run not found")
    return run

@app.post("/api/reset")
async def reset_all():
    out=[]
    for service in ["auth","order","inventory","payment","booking-api"]:
        try:
            result=await reset(service)
            health=await get_health(service)
            metrics=await get_metrics(service)
            workload=await probe_workload(service)
            artifact=await get_state_artifact(service)
            candidates=[r for r in all_runs() if r.get("service")==service and r.get("state") in {"fault_injected","recovering","verification_failed"}]
            candidates.sort(key=lambda r:r.get("started_at",""),reverse=True)
            verification=None
            run_id=None
            if candidates:
                run=candidates[0]
                run_id=run["run_id"]
                verification=_verify_recovery(run,health,metrics,workload,artifact)
                run["state"]="recovered" if verification["status"]=="PASS" else "verification_failed"
                run["recovered_at"]=utc_now()
                run["verification"]=verification
                run.setdefault("recovery_events",[]).append({"timestamp":utc_now(),"request_id":"reset-all","action":"reset_all"})
                save(run)
                add_snapshot(run["run_id"],health=health,metrics=metrics,workload=workload,artifact=artifact,event="recovered",verification=verification)
            out.append({"service":service,"result":result,"run_id":run_id,"verification":verification})
        except Exception as exc:
            out.append({"service":service,"error":str(exc)})
    return {"accepted":True,"state":"clean","services":out}

@app.post("/hooks/monitoring")
def monitoring(payload:dict):
    if "alerts" in payload:
        events=[]
        for alert in payload.get("alerts",[]):
            labels=alert.get("labels",{}); annotations=alert.get("annotations",{})
            events.append({"source":"incidentlab","event_type":"alert","event_id":f"alertmanager-{labels.get('alertname','unknown')}-{labels.get('service','unknown')}","timestamp":utc_now(),"environment":"incidentlab","service":labels.get("service","unknown"),"severity":labels.get("severity","warning"),"alert_name":labels.get("alertname","UnknownAlert"),"status":alert.get("status","firing"),"labels":labels,"annotations":annotations})
        return {"accepted":True,"source":"incidentlab","event_type":"alert","events":events}
    event=MonitoringEvent.model_validate(payload)
    return {"accepted":True,"source":"incidentlab","event_id":event.event_id,"event_type":event.event_type,"service":event.service,"status":event.status}

WEB_DIR = Path(__file__).parent / "web"
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
