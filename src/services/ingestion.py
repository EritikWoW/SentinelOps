"""Translate normalized detector events into the existing incident contract."""

from __future__ import annotations

from src.models.events import NormalizedEvent
from src.models.incident import IncidentCreate


def incident_from_event(event: NormalizedEvent) -> IncidentCreate:
    """Create a backward-compatible incident request from a detector event."""

    return IncidentCreate(
        service=event.service,
        severity=event.severity,
        summary=event.message,
        source=event.source,
        node_id=event.node_id,
        trigger=event.trigger,
        evidence=event.evidence,
    )
