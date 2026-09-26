import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
import incidentlab.api as incident_api
from incidentlab.api import app, _sanitize_recovery_patch, _select_recovery_run

def test_health(): assert TestClient(app).get('/api/health').status_code == 200
def test_scenarios(): assert len(TestClient(app).get('/api/scenarios').json()) == 12
def test_monitoring_contract():
    event={'source':'incidentlab','event_type':'alert','event_id':'incidentlab-payment-001','timestamp':'2026-09-24T08:00:00Z','environment':'incidentlab','service':'payment','severity':'critical','alert_name':'PaymentServiceUnhealthy','status':'firing','labels':{'scenario':'C01','fault':'service_crash'},'annotations':{'summary':'Payment service is unhealthy'}}
    r=TestClient(app).post('/hooks/monitoring',json=event); assert r.status_code == 200; assert r.json()['accepted'] is True

def test_alertmanager_normalization():
    payload={'alerts':[{'status':'firing','labels':{'alertname':'DemoMartServiceUnhealthy','service':'payment','severity':'critical','scenario':'C01'},'annotations':{'summary':'Payment service is unhealthy'}}]}
    r=TestClient(app).post('/hooks/monitoring',json=payload); assert r.status_code == 200; assert r.json()['events'][0]['source']=='incidentlab'


def test_recovery_patch_drops_derived_health_keys():
    clean, ignored, unsupported = _sanitize_recovery_patch(
        {'version':'v2.0','deployment_mismatch':False},
        {'baseline':{'version':'v2.0','crash':False}},
    )
    assert clean == {'version':'v2.0'}
    assert ignored == ['deployment_mismatch']
    assert unsupported == []


def test_recovery_patch_rejects_unknown_non_derived_keys():
    clean, ignored, unsupported = _sanitize_recovery_patch(
        {'version':'v2.0','shell_command':'rm -rf /'},
        {'baseline':{'version':'v2.0'}},
    )
    assert clean == {'version':'v2.0'}
    assert ignored == []
    assert unsupported == ['shell_command']


def test_recovery_run_binding_accepts_exact_active_run(monkeypatch):
    run={'run_id':'incidentlab-run-new2','service':'payment','state':'fault_injected','started_at':'2026-09-25T14:20:00Z'}
    monkeypatch.setattr(incident_api,'load',lambda run_id: run if run_id==run['run_id'] else None)
    monkeypatch.setattr(incident_api,'all_runs',lambda:[run])
    assert _select_recovery_run('payment','opsswarm-incidentlab-run-new2') == run
    assert _select_recovery_run('payment','web-incidentlab-run-new2-12345') == run


def test_recovery_run_binding_rejects_stale_request(monkeypatch):
    old={'run_id':'incidentlab-run-old1','service':'payment','state':'fault_injected','started_at':'2026-09-25T14:10:00Z'}
    new={'run_id':'incidentlab-run-new2','service':'payment','state':'fault_injected','started_at':'2026-09-25T14:20:00Z'}
    monkeypatch.setattr(incident_api,'load',lambda run_id: old if run_id==old['run_id'] else None)
    monkeypatch.setattr(incident_api,'all_runs',lambda:[old,new])
    with pytest.raises(HTTPException) as exc:
        _select_recovery_run('payment','opsswarm-incidentlab-run-old1')
    assert exc.value.status_code == 409
    assert 'newer active run exists' in exc.value.detail


def test_recovery_run_binding_rejects_recovered_target(monkeypatch):
    run={'run_id':'incidentlab-run-old1','service':'payment','state':'recovered','started_at':'2026-09-25T14:10:00Z'}
    monkeypatch.setattr(incident_api,'load',lambda run_id: run if run_id==run['run_id'] else None)
    monkeypatch.setattr(incident_api,'all_runs',lambda:[run])
    with pytest.raises(HTTPException) as exc:
        _select_recovery_run('payment','opsswarm-incidentlab-run-old1')
    assert exc.value.status_code == 409
    assert 'not recoverable' in exc.value.detail
