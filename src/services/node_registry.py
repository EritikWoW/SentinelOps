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
        self._client = firestore.Client(
            project=os.getenv("GOOGLE_CLOUD_PROJECT") or None,
            database=os.getenv("FIRESTORE_DATABASE", "(default)"),
        )
        self._firestore = firestore
        self._collection = self._client.collection("nodes")

    def heartbeat(self, payload: NodeHeartbeat) -> NodeRecord:
        snapshot = self._collection.document(payload.node_id).get()
        previous = NodeRecord.model_validate(snapshot.to_dict()) if snapshot.exists else None
        now = datetime.now(timezone.utc)
        record = NodeRecord(
            **payload.model_dump(),
            status="online",
            last_seen=now,
            active_incidents=previous.active_incidents if previous else 0,
        )
        with self._lock:
            self._items[payload.node_id] = record
        reference = self._collection.document(payload.node_id)
        if snapshot.exists:
            reference.update({
                "hostname": record.hostname,
                "platform": record.platform,
                "services": record.services,
                "status": record.status,
                "last_seen": record.last_seen,
            })
        else:
            self._persist(record)
        return record

    def record_incident(self, node_id: str) -> NodeRecord | None:
        snapshot = self._collection.document(node_id).get()
        if not snapshot.exists:
            return None
        reference = self._collection.document(node_id)
        reference.update({"active_incidents": self._firestore.Increment(1)})
        record = NodeRecord.model_validate(reference.get().to_dict())
        with self._lock:
            self._items[node_id] = record
        return self._with_status(record)

    def record_resolution(self, node_id: str) -> NodeRecord | None:
        reference = self._collection.document(node_id)
        transaction = self._client.transaction()
        firestore = self._firestore

        @firestore.transactional
        def decrement(transaction):
            snapshot = reference.get(transaction=transaction)
            if not snapshot.exists:
                return None
            current = int(snapshot.to_dict().get("active_incidents", 0))
            transaction.update(reference, {"active_incidents": max(0, current - 1)})
            return snapshot.to_dict()

        result = decrement(transaction)
        if result is None:
            return None
        record = NodeRecord.model_validate(reference.get().to_dict())
        with self._lock:
            self._items[node_id] = record
        return self._with_status(record)

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
