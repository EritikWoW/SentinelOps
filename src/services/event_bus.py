"""Event publication with an observable local bus and a Pub/Sub adapter."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Callable, Protocol
from uuid import uuid4

from pydantic import BaseModel, ValidationError


logger = logging.getLogger(__name__)


class EventRecord(BaseModel):
    event_id: str
    event_type: str
    occurred_at: datetime
    payload: dict[str, Any]
    replayed_from: str | None = None
    attempt: int = 1


class EventPublisher(Protocol):
    def publish(self, event_type: str, payload: dict[str, Any]) -> EventRecord: ...
    def recent(self, limit: int = 50) -> list[EventRecord]: ...
    def replay(self, event_id: str) -> EventRecord: ...


class EventConsumer(Protocol):
    """Inbound event contract, intentionally separate from publishing."""

    def start(self, handler: Callable[[dict[str, Any]], None]) -> None: ...
    def stop(self) -> None: ...


class InMemoryEventConsumer:
    """Test/local consumer that can receive one event at a time."""

    def __init__(self) -> None:
        self._handler: Callable[[dict[str, Any]], None] | None = None

    def start(self, handler: Callable[[dict[str, Any]], None]) -> None:
        self._handler = handler

    def submit(self, payload: dict[str, Any]) -> None:
        if self._handler is not None:
            self._handler(payload)

    def stop(self) -> None:
        self._handler = None


class InMemoryEventPublisher:
    """Thread-safe local event log used by default during development."""

    def __init__(self, max_events: int = 500) -> None:
        self._max_events = max_events
        self._events: list[EventRecord] = []
        self._lock = RLock()

    def publish(self, event_type: str, payload: dict[str, Any]) -> EventRecord:
        event = EventRecord(
            event_id=f"evt_{uuid4().hex[:12]}",
            event_type=event_type,
            occurred_at=datetime.now(timezone.utc),
            payload=payload,
        )
        with self._lock:
            self._events.append(event)
            del self._events[:-self._max_events]
        return event.model_copy(deep=True)

    def recent(self, limit: int = 50) -> list[EventRecord]:
        bounded_limit = max(1, min(limit, self._max_events))
        with self._lock:
            return [event.model_copy(deep=True) for event in self._events[-bounded_limit:]][::-1]

    def replay(self, event_id: str) -> EventRecord:
        with self._lock:
            original = next((event for event in self._events if event.event_id == event_id), None)
        if original is None:
            raise ValueError(f"Event not found: {event_id}")
        replayed = self.publish(original.event_type, original.payload)
        replayed.replayed_from = original.event_id
        replayed.attempt = original.attempt + 1
        with self._lock:
            self._events[-1] = replayed
        return replayed.model_copy(deep=True)


class NullEventPublisher:
    def publish(self, event_type: str, payload: dict[str, Any]) -> EventRecord:
        return EventRecord(
            event_id=f"evt_{uuid4().hex[:12]}",
            event_type=event_type,
            occurred_at=datetime.now(timezone.utc),
            payload=payload,
        )

    def recent(self, limit: int = 50) -> list[EventRecord]:
        return []

    def replay(self, event_id: str) -> EventRecord:
        raise ValueError("Event replay is unavailable")


class PubSubEventPublisher:
    def __init__(self) -> None:
        try:
            from google.cloud import pubsub_v1
        except ImportError as exc:
            raise RuntimeError("Pub/Sub requires google-cloud-pubsub to be installed") from exc
        project = os.getenv("GOOGLE_CLOUD_PROJECT")
        topic = os.getenv("PUBSUB_INTERNAL_TOPIC", "sentinelops-internal-events")
        if not project:
            raise RuntimeError("GOOGLE_CLOUD_PROJECT is required for Pub/Sub")
        self._publisher = pubsub_v1.PublisherClient()
        self._topic_path = self._publisher.topic_path(project, topic)

    def publish(self, event_type: str, payload: dict[str, Any]) -> EventRecord:
        event = EventRecord(
            event_id=f"evt_{uuid4().hex[:12]}",
            event_type=event_type,
            occurred_at=datetime.now(timezone.utc),
            payload=payload,
        )
        future = self._publisher.publish(
            self._topic_path,
            json.dumps(event.model_dump(mode="json"), ensure_ascii=False).encode("utf-8"),
            event_type=event_type,
        )
        future.result(timeout=10)
        return event

    def recent(self, limit: int = 50) -> list[EventRecord]:
        return []

    def replay(self, event_id: str) -> EventRecord:
        raise ValueError("Event replay requires a local event history")


class PubSubEventConsumer:
    """Consume detector events from the dedicated inbound subscription."""

    def __init__(self) -> None:
        try:
            from google.cloud import pubsub_v1
        except ImportError as exc:
            raise RuntimeError("Pub/Sub requires google-cloud-pubsub to be installed") from exc
        project = os.getenv("GOOGLE_CLOUD_PROJECT")
        subscription = os.getenv("PUBSUB_SUBSCRIPTION")
        dead_letter_topic = os.getenv("PUBSUB_DEAD_LETTER_TOPIC", "sentinelops-dead-letter-events")
        if not project or not subscription:
            raise RuntimeError("GOOGLE_CLOUD_PROJECT and PUBSUB_SUBSCRIPTION are required for inbound Pub/Sub")
        self._subscriber = pubsub_v1.SubscriberClient()
        self._subscription_path = self._subscriber.subscription_path(project, subscription)
        self._dead_letter_publisher = pubsub_v1.PublisherClient()
        self._dead_letter_topic_path = self._dead_letter_publisher.topic_path(project, dead_letter_topic)
        self._streaming_future = None

    def _publish_dead_letter(self, message: Any, exc: Exception) -> None:
        """Persist a permanently invalid inbound message before acknowledging it."""

        original_message_id = getattr(message, "message_id", "unknown")
        raw_data = message.data.decode("utf-8", errors="replace")
        dead_letter = {
            "original_message_id": original_message_id,
            "subscription": self._subscription_path,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "raw_data": raw_data,
            "quarantined_at": datetime.now(timezone.utc).isoformat(),
        }
        future = self._dead_letter_publisher.publish(
            self._dead_letter_topic_path,
            json.dumps(dead_letter, ensure_ascii=False).encode("utf-8"),
            event_type="dead_letter",
            original_message_id=original_message_id,
        )
        future.result(timeout=10)

    def _handle_permanent_failure(self, message: Any, exc: Exception) -> None:
        """Quarantine malformed input once; retry only if the quarantine publish fails."""

        context = {
            "pubsub_message_id": getattr(message, "message_id", "unknown"),
            "pubsub_subscription": self._subscription_path,
            "pubsub_dead_letter_topic": self._dead_letter_topic_path,
        }
        logger.exception(
            "Rejected permanently invalid inbound Pub/Sub event; quarantining message",
            extra=context,
            exc_info=exc,
        )
        try:
            self._publish_dead_letter(message, exc)
        except Exception:
            logger.exception(
                "Failed to publish invalid Pub/Sub event to dead-letter topic; original message will be retried",
                extra=context,
            )
            message.nack()
            return
        logger.warning(
            "Quarantined invalid inbound Pub/Sub event; acknowledging original message",
            extra=context,
        )
        message.ack()

    def _process_message(self, handler: Callable[[dict[str, Any]], None], message: Any) -> None:
        """Decode one Pub/Sub message, retrying only failures that can recover."""

        try:
            raw_payload = json.loads(message.data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._handle_permanent_failure(message, exc)
            return

        try:
            handler(raw_payload)
        except ValidationError as exc:
            self._handle_permanent_failure(message, exc)
            return
        except Exception:
            logger.exception(
                "Failed to process inbound Pub/Sub event; transient failure will be retried",
                extra={
                    "pubsub_message_id": getattr(message, "message_id", "unknown"),
                    "pubsub_subscription": self._subscription_path,
                },
            )
            message.nack()
            return

        message.ack()

    def start(self, handler: Callable[[dict[str, Any]], None]) -> None:
        import threading

        def callback(message: Any) -> None:
            self._process_message(handler, message)

        self._streaming_future = self._subscriber.subscribe(self._subscription_path, callback)
        threading.Thread(target=self._streaming_future.result, daemon=True).start()

    def stop(self) -> None:
        if self._streaming_future is not None:
            self._streaming_future.cancel()
            self._streaming_future = None


class FirestoreEventPublisher:
    """Persist event history while delegating outbound delivery to a publisher."""

    def __init__(self, delegate: EventPublisher) -> None:
        try:
            from google.cloud import firestore
        except ImportError as exc:
            raise RuntimeError("Firestore backend requires google-cloud-firestore to be installed") from exc
        self._delegate = delegate
        self._collection = firestore.Client(
            project=os.getenv("GOOGLE_CLOUD_PROJECT") or None,
            database=os.getenv("FIRESTORE_DATABASE", "(default)"),
        ).collection("events")

    def publish(self, event_type: str, payload: dict[str, Any]) -> EventRecord:
        event = self._delegate.publish(event_type, payload)
        self._collection.document(event.event_id).set(event.model_dump(mode="json"))
        return event

    def recent(self, limit: int = 50) -> list[EventRecord]:
        bounded = max(1, min(limit, 500))
        snapshots = self._collection.order_by("occurred_at", direction="DESCENDING").limit(bounded).stream()
        return [EventRecord.model_validate(snapshot.to_dict()) for snapshot in snapshots]

    def replay(self, event_id: str) -> EventRecord:
        snapshot = self._collection.document(event_id).get()
        if not snapshot.exists:
            raise ValueError(f"Event not found: {event_id}")
        original = EventRecord.model_validate(snapshot.to_dict())
        replayed = self._delegate.publish(original.event_type, original.payload)
        replayed.replayed_from = original.event_id
        replayed.attempt = original.attempt + 1
        self._collection.document(replayed.event_id).set(replayed.model_dump(mode="json"))
        return replayed


def build_event_publisher() -> EventPublisher:
    publisher: EventPublisher
    if os.getenv("PUBSUB_ENABLED", "false").strip().lower() == "true":
        publisher = PubSubEventPublisher()
    else:
        publisher = InMemoryEventPublisher()
    if os.getenv("SENTINELOPS_STORE", "memory").strip().lower() == "firestore":
        return FirestoreEventPublisher(publisher)
    return publisher


def build_event_consumer() -> EventConsumer:
    if os.getenv("PUBSUB_ENABLED", "false").strip().lower() == "true" and os.getenv("PUBSUB_SUBSCRIPTION"):
        return PubSubEventConsumer()
    return InMemoryEventConsumer()
