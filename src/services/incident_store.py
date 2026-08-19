"""Incident persistence and workflow state transitions."""

from __future__ import annotations

import json
import os
from pathlib import Path
from threading import RLock
from typing import Protocol

from src.models.incident import IncidentResponse, TimelineEvent


class IncidentNotFoundError(LookupError):
    """Raised when an incident id is not present in the store."""


class IncidentRepository(Protocol):
    def save(self, incident: IncidentResponse) -> IncidentResponse: ...
    def get(self, incident_id: str) -> IncidentResponse: ...
    def list(self, limit: int = 50) -> list[IncidentResponse]: ...
    def decide(self, incident_id: str, decision: str, comment: str) -> IncidentResponse: ...
    def execute(self, incident_id: str, detail: str = "") -> IncidentResponse: ...
    def verify(self, incident_id: str, passed: bool, notes: str) -> IncidentResponse: ...


def _apply_decision(incident: IncidentResponse, decision: str, comment: str) -> IncidentResponse:
    if incident.analysis is None or not hasattr(incident.analysis, "timeline"):
        raise ValueError("Incident has no actionable analysis")
    if not incident.analysis.requires_human_approval:
        raise ValueError("Human approval is not required for this incident")
    if incident.approval_status != "pending":
        raise ValueError(f"Incident approval is already {incident.approval_status}")

    updated = incident.model_copy(deep=True)
    updated.approval_status = "approved" if decision == "approve" else "rejected"
    analysis = updated.analysis
    if decision == "reject":
        analysis.remediation_status = "blocked"
        detail = "Human approval rejected; remediation remains blocked."
        timeline_status = "blocked"
    else:
        detail = "Human approval recorded; remediation is authorized but has not executed yet."
        timeline_status = "pending"
    if comment:
        detail = f"{detail} Comment: {comment}"
    analysis.execution_notes = f"{analysis.execution_notes} {detail}".strip()
    analysis.timeline = [
        *analysis.timeline,
        TimelineEvent(stage="remediate", status=timeline_status, detail=detail),
    ]
    return updated


def _apply_execution(incident: IncidentResponse, detail: str = "") -> IncidentResponse:
    if incident.analysis is None or not hasattr(incident.analysis, "timeline"):
        raise ValueError("Incident has no actionable analysis")
    if incident.analysis.requires_human_approval and incident.approval_status != "approved":
        raise ValueError("Human approval is required before execution")
    if not incident.analysis.requires_human_approval and incident.approval_status not in {"not_required", "approved"}:
        raise ValueError("Incident is not eligible for execution")
    if incident.analysis.remediation_status == "executed":
        raise ValueError("Remediation has already been executed")
    if incident.analysis.remediation_status == "blocked":
        raise ValueError("Safety policy blocked this remediation")

    updated = incident.model_copy(deep=True)
    analysis = updated.analysis
    analysis.remediation_status = "executed"
    execution_detail = detail or "Safe demo remediation executed locally; no production infrastructure was mutated."
    analysis.execution_notes = f"{analysis.execution_notes} {execution_detail}".strip()
    analysis.timeline = [
        *analysis.timeline,
        TimelineEvent(stage="remediate", status="completed", detail=execution_detail),
    ]
    return updated


def _apply_verification(incident: IncidentResponse, passed: bool, notes: str) -> IncidentResponse:
    if incident.analysis is None or not hasattr(incident.analysis, "timeline"):
        raise ValueError("Incident has no verification state")
    if incident.analysis.remediation_status != "executed":
        raise ValueError("Remediation must be executed before verification")
    if incident.analysis.verification_status != "pending":
        raise ValueError("Incident verification is already complete")

    updated = incident.model_copy(deep=True)
    analysis = updated.analysis
    analysis.verification_status = "passed" if passed else "failed"
    analysis.verification_result = notes or (
        "Local health checks passed." if passed else "Local health checks failed."
    )
    updated.status = "resolved" if passed else "remediation_failed"
    detail = f"Verification {'passed' if passed else 'failed'}: {analysis.verification_result}"
    analysis.execution_notes = f"{analysis.execution_notes} {detail}".strip()
    analysis.timeline = [
        *analysis.timeline,
        TimelineEvent(stage="verify", status="completed", detail=detail),
    ]
    return updated


class IncidentStore:
    def __init__(self) -> None:
        self._items: dict[str, IncidentResponse] = {}
        self._lock = RLock()

    def save(self, incident: IncidentResponse) -> IncidentResponse:
        with self._lock:
            stored = incident.model_copy(deep=True)
            self._items[stored.incident_id] = stored
            return stored.model_copy(deep=True)

    def get(self, incident_id: str) -> IncidentResponse:
        with self._lock:
            try:
                return self._items[incident_id].model_copy(deep=True)
            except KeyError as exc:
                raise IncidentNotFoundError(incident_id) from exc

    def list(self, limit: int = 50) -> list[IncidentResponse]:
        bounded_limit = max(1, min(limit, 100))
        with self._lock:
            items = sorted(self._items.values(), key=lambda item: item.created_at, reverse=True)
            return [item.model_copy(deep=True) for item in items[:bounded_limit]]

    def decide(self, incident_id: str, decision: str, comment: str) -> IncidentResponse:
        with self._lock:
            incident = self._items.get(incident_id)
            if incident is None:
                raise IncidentNotFoundError(incident_id)
            updated = _apply_decision(incident, decision, comment)
            self._items[incident_id] = updated
            return updated.model_copy(deep=True)

    def execute(self, incident_id: str, detail: str = "") -> IncidentResponse:
        with self._lock:
            incident = self._items.get(incident_id)
            if incident is None:
                raise IncidentNotFoundError(incident_id)
            updated = _apply_execution(incident, detail)
            self._items[incident_id] = updated
            return updated.model_copy(deep=True)

    def verify(self, incident_id: str, passed: bool, notes: str) -> IncidentResponse:
        with self._lock:
            incident = self._items.get(incident_id)
            if incident is None:
                raise IncidentNotFoundError(incident_id)
            updated = _apply_verification(incident, passed, notes)
            self._items[incident_id] = updated
            return updated.model_copy(deep=True)


class FirestoreIncidentStore:
    """Firestore-backed implementation selected explicitly in cloud mode."""

    def __init__(self, collection: str = "incidents") -> None:
        try:
            from google.cloud import firestore
        except ImportError as exc:
            raise RuntimeError(
                "Firestore backend requires google-cloud-firestore to be installed"
            ) from exc
        self._client = firestore.Client(
            project=os.getenv("GOOGLE_CLOUD_PROJECT") or None,
            database=os.getenv("FIRESTORE_DATABASE", "(default)"),
        )
        self._collection = self._client.collection(collection)

    def save(self, incident: IncidentResponse) -> IncidentResponse:
        self._collection.document(incident.incident_id).set(incident.model_dump(mode="json"))
        return incident.model_copy(deep=True)

    def get(self, incident_id: str) -> IncidentResponse:
        snapshot = self._collection.document(incident_id).get()
        if not snapshot.exists:
            raise IncidentNotFoundError(incident_id)
        return IncidentResponse.model_validate(snapshot.to_dict())

    def list(self, limit: int = 50) -> list[IncidentResponse]:
        bounded_limit = max(1, min(limit, 100))
        snapshots = self._collection.order_by("created_at", direction="DESCENDING").limit(bounded_limit).stream()
        return [IncidentResponse.model_validate(snapshot.to_dict()) for snapshot in snapshots]

    def decide(self, incident_id: str, decision: str, comment: str) -> IncidentResponse:
        updated = _apply_decision(self.get(incident_id), decision, comment)
        return self.save(updated)

    def execute(self, incident_id: str, detail: str = "") -> IncidentResponse:
        updated = _apply_execution(self.get(incident_id), detail)
        return self.save(updated)

    def verify(self, incident_id: str, passed: bool, notes: str) -> IncidentResponse:
        updated = _apply_verification(self.get(incident_id), passed, notes)
        return self.save(updated)


class JsonIncidentStore:
    """Small persistent local store for offline development and restarts."""

    def __init__(self, path: str = ".local-data/incidents.json") -> None:
        self._path = Path(path)
        self._lock = RLock()
        self._items: dict[str, IncidentResponse] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            self._items = {
                incident_id: IncidentResponse.model_validate(value)
                for incident_id, value in raw.items()
            }
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise RuntimeError(f"Cannot load incident store: {self._path}") from exc

    def _flush(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(".tmp")
        payload = {
            incident_id: incident.model_dump(mode="json")
            for incident_id, incident in self._items.items()
        }
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self._path)

    def save(self, incident: IncidentResponse) -> IncidentResponse:
        with self._lock:
            stored = incident.model_copy(deep=True)
            self._items[stored.incident_id] = stored
            self._flush()
            return stored.model_copy(deep=True)

    def get(self, incident_id: str) -> IncidentResponse:
        with self._lock:
            incident = self._items.get(incident_id)
            if incident is None:
                raise IncidentNotFoundError(incident_id)
            return incident.model_copy(deep=True)

    def list(self, limit: int = 50) -> list[IncidentResponse]:
        bounded_limit = max(1, min(limit, 100))
        with self._lock:
            items = sorted(self._items.values(), key=lambda item: item.created_at, reverse=True)
            return [item.model_copy(deep=True) for item in items[:bounded_limit]]

    def decide(self, incident_id: str, decision: str, comment: str) -> IncidentResponse:
        with self._lock:
            updated = _apply_decision(self.get(incident_id), decision, comment)
            self._items[incident_id] = updated
            self._flush()
            return updated.model_copy(deep=True)

    def execute(self, incident_id: str, detail: str = "") -> IncidentResponse:
        with self._lock:
            updated = _apply_execution(self.get(incident_id), detail)
            self._items[incident_id] = updated
            self._flush()
            return updated.model_copy(deep=True)

    def verify(self, incident_id: str, passed: bool, notes: str) -> IncidentResponse:
        with self._lock:
            updated = _apply_verification(self.get(incident_id), passed, notes)
            self._items[incident_id] = updated
            self._flush()
            return updated.model_copy(deep=True)


def build_incident_store() -> IncidentRepository:
    backend = os.getenv("SENTINELOPS_STORE", "memory").strip().lower()
    if backend == "memory":
        return IncidentStore()
    if backend == "file":
        return JsonIncidentStore(os.getenv("SENTINELOPS_DATA_FILE", ".local-data/incidents.json"))
    if backend == "firestore":
        return FirestoreIncidentStore()
    raise RuntimeError("SENTINELOPS_STORE must be 'memory', 'file', or 'firestore'")
