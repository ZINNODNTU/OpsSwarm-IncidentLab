import os, httpx
DEFAULT_PORTS={"auth":8001,"order":8002,"inventory":8003,"payment":8004,"booking-api":8005}
def base_url(service):
    env=os.getenv(f"{service.upper().replace('-', '_')}_URL"); return env.rstrip("/") if env else f"http://127.0.0.1:{DEFAULT_PORTS.get(service,8000)}"
async def get_health(service):
    async with httpx.AsyncClient(timeout=5) as c:
        r=await c.get(base_url(service)+"/health"); r.raise_for_status(); return r.json()
async def get_metrics(service):
    async with httpx.AsyncClient(timeout=5) as c:
        r=await c.get(base_url(service)+"/metrics-json"); r.raise_for_status(); return r.json()
async def inject(service,fault,value):
    async with httpx.AsyncClient(timeout=5) as c:
        actual="crash" if fault=="service_crash" else fault
        if fault=="bad_deployment": r=await c.post(base_url(service)+"/admin/version",json={"version":str(value)})
        elif fault=="duplicate_alerts": return {"service":service,"state":"duplicate-alert simulation","accepted":True}
        else: r=await c.post(base_url(service)+"/admin/fault",json={"fault":actual,"enabled":True,"value":value})
        r.raise_for_status(); return r.json()
async def reset(service):
    async with httpx.AsyncClient(timeout=5) as c:
        r=await c.post(base_url(service)+"/admin/reset"); r.raise_for_status(); return r.json()
