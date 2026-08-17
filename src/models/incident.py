from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

Severity = Literal["low", "medium", "high", "critical"]


class IncidentCreate(BaseModel):
    service: str = Field(min_length=1)
    severity: Severity
    summary: str = Field(min_length=1)


class IncidentResponse(BaseModel):
    incident_id: str
    status: Literal["accepted"] = "accepted"
    service: str
    severity: Severity
    summary: str
    created_at: datetime

    @classmethod
    def accepted(cls, payload: IncidentCreate) -> "IncidentResponse":
        return cls(
            incident_id=f"inc_{uuid4().hex[:12]}",
            service=payload.service,
            severity=payload.severity,
            summary=payload.summary,
            created_at=datetime.now(timezone.utc),
        )
