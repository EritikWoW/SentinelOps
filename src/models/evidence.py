"""Structured, bounded evidence carried with an incident."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


EvidenceType = Literal["log", "healthcheck", "process", "metric", "other"]


class EvidenceItem(BaseModel):
    """A single evidence item collected before AI analysis."""

    type: EvidenceType
    source: str = Field(min_length=1, max_length=500)
    timestamp: datetime | None = None
    content: str = Field(default="", max_length=10_000)
    status_code: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
