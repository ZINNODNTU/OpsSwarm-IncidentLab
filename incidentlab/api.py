import asyncio
from fastapi import FastAPI, HTTPException
from .models import FaultInjectRequest, RecoveryRequest, MonitoringEvent, utc_now
from .scenarios import scenarios, get
from .simulator import get_health, get_metrics, inject, reset
from .store import new_run, load, save, all_runs
from .evidence import add_snapshot
app=FastAPI(title="OpsSwarm-IncidentLab",version="1.0.0")
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
@app.get("/api/faults")
def faults(): return {"supported":["service_crash","crash","error_rate","bad_deployment","db_down","db_pool_exhausted","latency_ms","cpu_percent","memory_percent","external_timeout","telemetry_missing","duplicate_alerts"]}
@app.post("/api/faults/inject")
async def fault_inject(req:FaultInjectRequest):
    sc=get(req.scenario_id)
    if not sc: raise HTTPException(404,"scenario not found")
    if sc.get("service")!=req.service or sc.get("fault")!=req.fault: raise HTTPException(400,"request does not match scenario contract")
    try: await inject(req.service,req.fault,sc.get("value",True))
    except Exception as exc: raise HTTPException(502,f"fault injection failed: {exc}")
    run=new_run(req.scenario_id,req.service,req.fault)
    try: add_snapshot(run["run_id"],health=await get_health(req.service),metrics=await get_metrics(req.service),event="fault_injected")
    except Exception: pass
    asyncio.create_task(_auto_reset(req.service,run["run_id"],req.duration_seconds))
    return {"accepted":True,"run_id":run["run_id"],"scenario_id":req.scenario_id,"service":req.service,"fault":req.fault,"state":"fault_injected"}
async def _auto_reset(service,run_id,seconds):
    await asyncio.sleep(seconds)
    try: await reset(service)
    except Exception: return
    run=load(run_id)
    if run: run["state"]="auto_recovered";run["recovered_at"]=utc_now();save(run)
@app.post("/api/faults/reset")
async def fault_reset(req:dict):
    service=req.get("service")
    if not service: raise HTTPException(400,"service is required")
    try: result=await reset(service)
    except Exception as exc: raise HTTPException(502,str(exc))
    return {"accepted":True,"service":service,"state":"reset","result":result}
@app.post("/api/recovery/{service}")
async def recovery(service:str,req:RecoveryRequest):
    if req.action not in {"restart","reset"}: raise HTTPException(400,"unsupported simulation action")
    try: await reset(service);health=await get_health(service);metrics=await get_metrics(service)
    except Exception as exc: raise HTTPException(502,str(exc))
    for run in reversed(all_runs()):
        if run.get("service")==service and run.get("state")=="fault_injected":
            run["state"]="recovered";run.setdefault("recovery_events",[]).append({"timestamp":utc_now(),"request_id":req.request_id,"action":req.action});save(run);add_snapshot(run["run_id"],health=health,metrics=metrics,event="recovered");break
    return {"accepted":True,"request_id":req.request_id,"service":service,"action":req.action,"state":"recovering"}
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
        try: out.append(await reset(service))
        except Exception as exc: out.append({"service":service,"error":str(exc)})
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
