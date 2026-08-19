"""Normalized events exchanged between SentinelOps Nodes and the Control Plane."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from src.models.evidence import EvidenceItem


EventSource = Literal["log_file", "healthcheck", "process", "metric", "manual", "pubsub", "cloud_logging", "unknown"]
EventKind = Literal["incident", "recovery"]


class NormalizedEvent(BaseModel):
    """A detector output, intentionally independent from any AI provider."""

    event_id: str = Field(default_factory=lambda: f"node_evt_{uuid4().hex[:12]}")
    kind: EventKind = "incident"
    node_id: str = Field(min_length=1, max_length=120)
    hostname: str = Field(default="", max_length=255)
    service: str = Field(min_length=1, max_length=200)
    severity: Literal["low", "medium", "high", "critical"]
    source: EventSource
    trigger: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=10_000)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    evidence: list[EvidenceItem | str] = Field(default_factory=list, max_length=20)
    metadata: dict[str, Any] = Field(default_factory=dict)


class NodeHeartbeat(BaseModel):
    """Heartbeat payload sent by a local SentinelOps Node."""

    node_id: str = Field(min_length=1, max_length=120)
    hostname: str = Field(default="", max_length=255)
    platform: str = Field(default="unknown", max_length=80)
    version: str = Field(default="0.1.0", max_length=40)
    services: list[str] = Field(default_factory=list, max_length=100)


class NodeRecord(NodeHeartbeat):
    """Control Plane view of a Node and its last heartbeat."""

    status: Literal["online", "offline"] = "offline"
    last_seen: datetime | None = None
    active_incidents: int = 0


class EventIngestionResponse(BaseModel):
    """Result of accepting a normalized event."""

    accepted: bool = True
    event_id: str
    kind: EventKind
    incident: Any | None = None
