"""In-memory Node heartbeat registry for the local Control Plane."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from threading import RLock

from src.models.events import NodeHeartbeat, NodeRecord


class NodeRegistry:
    """Track Node liveness without coupling the coordinator to platform code."""

    def __init__(self, stale_after_seconds: int = 90) -> None:
        self._stale_after = timedelta(seconds=stale_after_seconds)
        self._items: dict[str, NodeRecord] = {}
        self._lock = RLock()

    def heartbeat(self, payload: NodeHeartbeat) -> NodeRecord:
        now = datetime.now(timezone.utc)
        with self._lock:
            current = self._items.get(payload.node_id)
            record = NodeRecord(
                **payload.model_dump(),
                status="online",
                last_seen=now,
                active_incidents=current.active_incidents if current else 0,
            )
            self._items[payload.node_id] = record
            return record.model_copy(deep=True)

    def list(self) -> list[NodeRecord]:
        with self._lock:
            return [self._with_status(item) for item in self._items.values()]

    def get(self, node_id: str) -> NodeRecord | None:
        with self._lock:
            item = self._items.get(node_id)
            return self._with_status(item) if item else None

    def record_incident(self, node_id: str) -> NodeRecord | None:
        """Increment the active incident counter for a known Node."""

        with self._lock:
            item = self._items.get(node_id)
            if item is None:
                return None
            item.active_incidents += 1
            return self._with_status(item)

    def record_resolution(self, node_id: str) -> NodeRecord | None:
        """Remove one resolved incident without allowing negative counts."""

        with self._lock:
            item = self._items.get(node_id)
            if item is None:
                return None
            item.active_incidents = max(0, item.active_incidents - 1)
            return self._with_status(item)

    def _with_status(self, item: NodeRecord) -> NodeRecord:
        if item.last_seen is None:
            return item.model_copy(deep=True)
        age = datetime.now(timezone.utc) - item.last_seen
        updated = item.model_copy(deep=True)
        updated.status = "online" if age <= self._stale_after else "offline"
        return updated


class FirestoreNodeRegistry(NodeRegistry):
    """Firestore-backed Node registry selected explicitly in cloud mode."""

    def __init__(self, stale_after_seconds: int = 90) -> None:
        super().__init__(stale_after_seconds)
        try:
            from google.cloud import firestore
        except ImportError as exc:
            raise RuntimeError("Firestore backend requires google-cloud-firestore to be installed") from exc
        self._collection = firestore.Client(
            project=os.getenv("GOOGLE_CLOUD_PROJECT") or None,
            database=os.getenv("FIRESTORE_DATABASE", "(default)"),
        ).collection("nodes")

    def heartbeat(self, payload: NodeHeartbeat) -> NodeRecord:
        record = super().heartbeat(payload)
        self._persist(record)
        return record

    def record_incident(self, node_id: str) -> NodeRecord | None:
        record = super().record_incident(node_id)
        if record is not None:
            self._persist(record)
        return record

    def record_resolution(self, node_id: str) -> NodeRecord | None:
        record = super().record_resolution(node_id)
        if record is not None:
            self._persist(record)
        return record

    def _persist(self, record: NodeRecord) -> None:
        self._collection.document(record.node_id).set(record.model_dump(mode="json"))

    def list(self) -> list[NodeRecord]:
        return [self._with_status(NodeRecord.model_validate(snapshot.to_dict())) for snapshot in self._collection.stream()]

    def get(self, node_id: str) -> NodeRecord | None:
        snapshot = self._collection.document(node_id).get()
        return self._with_status(NodeRecord.model_validate(snapshot.to_dict())) if snapshot.exists else None


def build_node_registry() -> NodeRegistry:
    if os.getenv("SENTINELOPS_STORE", "memory").strip().lower() == "firestore":
        return FirestoreNodeRegistry()
    return NodeRegistry()
