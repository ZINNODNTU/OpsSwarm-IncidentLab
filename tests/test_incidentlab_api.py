from fastapi.testclient import TestClient
from incidentlab.api import app

def test_health(): assert TestClient(app).get('/api/health').status_code == 200
def test_scenarios(): assert len(TestClient(app).get('/api/scenarios').json()) == 12
def test_monitoring_contract():
    event={'source':'incidentlab','event_type':'alert','event_id':'incidentlab-payment-001','timestamp':'2026-09-24T08:00:00Z','environment':'incidentlab','service':'payment','severity':'critical','alert_name':'PaymentServiceUnhealthy','status':'firing','labels':{'scenario':'C01','fault':'service_crash'},'annotations':{'summary':'Payment service is unhealthy'}}
    r=TestClient(app).post('/hooks/monitoring',json=event); assert r.status_code == 200; assert r.json()['accepted'] is True

def test_alertmanager_normalization():
    payload={'alerts':[{'status':'firing','labels':{'alertname':'DemoMartServiceUnhealthy','service':'payment','severity':'critical','scenario':'C01'},'annotations':{'summary':'Payment service is unhealthy'}}]}
    r=TestClient(app).post('/hooks/monitoring',json=payload); assert r.status_code == 200; assert r.json()['events'][0]['source']=='incidentlab'
