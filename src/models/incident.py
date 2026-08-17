from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

Severity = Literal["low", "medium", "high", "critical"]


class IncidentCreate(BaseModel):
    service: str = Field(min_length=1)
    severity: Severity
    summary: str = Field(min_length=1)


class IncidentAnalysis(BaseModel):
    root_cause_hypothesis: str
    evidence: list[str]
    remediation_action: str
    risk_level: Literal["low", "medium", "high", "critical"]
    requires_human_approval: bool
    verification_plan: list[str]
    incident_summary: str


class IncidentResponse(BaseModel):
    incident_id: str
    status: Literal["accepted", "analyzed"] = "accepted"
    service: str
    severity: Severity
    summary: str
    created_at: datetime
    analysis: IncidentAnalysis | dict[str, Any] | None = None

    @classmethod
    def accepted(cls, payload: IncidentCreate) -> "IncidentResponse":
        return cls(
            incident_id=f"inc_{uuid4().hex[:12]}",
            service=payload.service,
            severity=payload.severity,
            summary=payload.summary,
            created_at=datetime.now(timezone.utc),
        )

    @classmethod
    def analyzed(
        cls,
        payload: IncidentCreate,
        analysis: IncidentAnalysis | dict[str, Any],
    ) -> "IncidentResponse":
        return cls(
            incident_id=f"inc_{uuid4().hex[:12]}",
            status="analyzed",
            service=payload.service,
            severity=payload.severity,
            summary=payload.summary,
            created_at=datetime.now(timezone.utc),
            analysis=analysis,
        )
