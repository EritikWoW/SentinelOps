from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from src.models.evidence import EvidenceItem

Severity = Literal["low", "medium", "high", "critical"]
ExecutionMode = Literal["demo", "gemini"]
RemediationStatus = Literal["planned", "simulated", "executed", "blocked"]
ApprovalStatus = Literal["not_required", "pending", "approved", "rejected"]
VerificationStatus = Literal["pending", "passed", "failed"]


class TimelineEvent(BaseModel):
    stage: Literal["detect", "investigate", "decide", "remediate", "verify", "report"]
    status: Literal["completed", "pending", "blocked"]
    detail: str


class IncidentCreate(BaseModel):
    service: str = Field(min_length=1)
    severity: Severity
    summary: str = Field(min_length=1)
    source: str = Field(default="manual", max_length=120)
    node_id: str | None = Field(default=None, max_length=120)
    trigger: str | None = Field(default=None, max_length=120)
    evidence: list[EvidenceItem | str] = Field(default_factory=list, max_length=20)


class ApprovalRequest(BaseModel):
    decision: Literal["approve", "reject"]
    comment: str = Field(default="", max_length=1000)


class ExecutionRequest(BaseModel):
    confirm: bool = False


class VerificationRequest(BaseModel):
    passed: bool
    notes: str = Field(default="", max_length=1000)


class HealthVerificationRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2000)
    timeout_seconds: float = Field(default=3.0, gt=0, le=30)
    expected_status: int = Field(default=200, ge=100, le=599)


class IncidentAnalysis(BaseModel):
    root_cause_hypothesis: str
    evidence: list[EvidenceItem | str]
    remediation_action: str
    risk_level: Literal["low", "medium", "high", "critical"]
    requires_human_approval: bool
    verification_plan: list[str]
    incident_summary: str
    remediation_status: RemediationStatus = "planned"
    execution_notes: str = ""
    verification_status: VerificationStatus = "pending"
    verification_result: str = ""
    timeline: list[TimelineEvent] = Field(default_factory=list)


class IncidentResponse(BaseModel):
    incident_id: str
    status: Literal["accepted", "analyzed", "resolved", "remediation_failed"] = "accepted"
    service: str
    severity: Severity
    summary: str
    created_at: datetime
    analysis: IncidentAnalysis | dict[str, Any] | None = None
    execution_mode: ExecutionMode = "gemini"
    approval_status: ApprovalStatus = "not_required"
    source: str = "manual"
    node_id: str | None = None
    trigger: str | None = None
    evidence: list[EvidenceItem | str] = Field(default_factory=list)

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
        execution_mode: ExecutionMode = "gemini",
    ) -> "IncidentResponse":
        return cls(
            incident_id=f"inc_{uuid4().hex[:12]}",
            status="analyzed",
            service=payload.service,
            severity=payload.severity,
            summary=payload.summary,
            created_at=datetime.now(timezone.utc),
            analysis=analysis,
            execution_mode=execution_mode,
            source=payload.source,
            node_id=payload.node_id,
            trigger=payload.trigger,
            evidence=payload.evidence,
        )
