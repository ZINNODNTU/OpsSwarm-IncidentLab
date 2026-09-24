from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, Field


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

class FaultInjectRequest(BaseModel):
    scenario_id: str
    service: str
    fault: str
    duration_seconds: int = Field(default=30, ge=1, le=86400)
    metadata: dict[str, Any] = Field(default_factory=dict)

class RecoveryRequest(BaseModel):
    action: str = "restart"
    request_id: str

class MonitoringEvent(BaseModel):
    source: str = "incidentlab"
    event_type: str
    event_id: str
    timestamp: str
    environment: str = "incidentlab"
    service: str
    severity: str
    alert_name: str
    status: str
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)
