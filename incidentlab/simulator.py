import os, time, httpx

DEFAULT_PORTS={"auth":8001,"order":8002,"inventory":8003,"payment":8004,"booking-api":8005}


def base_url(service):
    env=os.getenv(f"{service.upper().replace('-', '_')}_URL")
    return env.rstrip("/") if env else f"http://127.0.0.1:{DEFAULT_PORTS.get(service,8000)}"


async def get_health(service):
    async with httpx.AsyncClient(timeout=5) as c:
        r=await c.get(base_url(service)+"/health")
        data=r.json()
        data["http_status"]=r.status_code
        return data


async def get_metrics(service):
    async with httpx.AsyncClient(timeout=5) as c:
        r=await c.get(base_url(service)+"/metrics-json")
        r.raise_for_status()
        return r.json()


async def get_state_artifact(service):
    async with httpx.AsyncClient(timeout=5) as c:
        r=await c.get(base_url(service)+"/admin/state")
        r.raise_for_status()
        return r.json()


async def get_baseline(service):
    async with httpx.AsyncClient(timeout=5) as c:
        r=await c.get(base_url(service)+"/admin/baseline")
        r.raise_for_status()
        return r.json()


async def probe_workload(service):
    started=time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r=await c.get(base_url(service)+"/workload")
        elapsed_ms=round((time.perf_counter()-started)*1000,1)
        try:
            body=r.json()
        except Exception:
            body={"text":r.text[:500]}
        return {"service":service,"reachable":True,"ok":r.status_code < 400,"http_status":r.status_code,"elapsed_ms":elapsed_ms,"body":body}
    except Exception as exc:
        return {"service":service,"reachable":False,"ok":False,"http_status":None,"elapsed_ms":round((time.perf_counter()-started)*1000,1),"error":f"{type(exc).__name__}: {exc}"}


async def inject(service,fault,value):
    async with httpx.AsyncClient(timeout=5) as c:
        actual="crash" if fault=="service_crash" else fault
        if fault=="bad_deployment":
            r=await c.post(base_url(service)+"/admin/version",json={"version":str(value)})
        elif fault=="duplicate_alerts":
            return {"service":service,"state":"duplicate-alert simulation","accepted":True}
        else:
            r=await c.post(base_url(service)+"/admin/fault",json={"fault":actual,"enabled":True,"value":value})
        r.raise_for_status()
        return r.json()


async def repair(service):
    """Repair the persisted state artifact, not just transient process memory."""
    async with httpx.AsyncClient(timeout=5) as c:
        r=await c.post(base_url(service)+"/admin/repair")
        r.raise_for_status()
        return r.json()


async def apply_patch(service, patch):
    async with httpx.AsyncClient(timeout=5) as c:
        r=await c.post(base_url(service)+"/admin/patch",json={"patch":patch})
        r.raise_for_status()
        return r.json()


async def reset(service):
    """Backward-compatible lab reset; also repairs the persisted state file."""
    return await repair(service)
