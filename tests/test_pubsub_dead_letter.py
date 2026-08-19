import json

from pydantic import BaseModel, Field

from src.services.event_bus import PubSubEventConsumer


class FakeFuture:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    def result(self, timeout: int | None = None) -> None:
        if self.error is not None:
            raise self.error


class FakePublisher:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[str, bytes, dict[str, str]]] = []

    def publish(self, topic: str, data: bytes, **attrs: str) -> FakeFuture:
        self.calls.append((topic, data, attrs))
        return FakeFuture(self.error)


class FakeMessage:
    def __init__(self, data: bytes, message_id: str = "msg-test") -> None:
        self.data = data
        self.message_id = message_id
        self.acked = 0
        self.nacked = 0

    def ack(self) -> None:
        self.acked += 1

    def nack(self) -> None:
        self.nacked += 1


def build_consumer(publisher: FakePublisher | None = None) -> PubSubEventConsumer:
    consumer = object.__new__(PubSubEventConsumer)
    consumer._subscription_path = "projects/test/subscriptions/sentinelops-incoming-sub"
    consumer._dead_letter_topic_path = "projects/test/topics/sentinelops-dead-letter-events"
    consumer._dead_letter_publisher = publisher or FakePublisher()
    consumer._streaming_future = None
    return consumer


def test_valid_pubsub_message_is_acknowledged() -> None:
    consumer = build_consumer()
    message = FakeMessage(b'{"service":"demo-api"}')
    received: list[dict[str, object]] = []

    consumer._process_message(received.append, message)

    assert received == [{"service": "demo-api"}]
    assert message.acked == 1
    assert message.nacked == 0
    assert consumer._dead_letter_publisher.calls == []


def test_invalid_json_is_quarantined_and_acknowledged() -> None:
    publisher = FakePublisher()
    consumer = build_consumer(publisher)
    message = FakeMessage(b'{"service":', message_id="bad-json")

    consumer._process_message(lambda payload: None, message)

    assert message.acked == 1
    assert message.nacked == 0
    assert len(publisher.calls) == 1
    topic, data, attrs = publisher.calls[0]
    assert topic.endswith("sentinelops-dead-letter-events")
    body = json.loads(data.decode("utf-8"))
    assert body["original_message_id"] == "bad-json"
    assert body["error_type"] == "JSONDecodeError"
    assert attrs["event_type"] == "dead_letter"


def test_schema_validation_error_is_quarantined_and_acknowledged() -> None:
    class RequiredPayload(BaseModel):
        node_id: str = Field(min_length=1)

    publisher = FakePublisher()
    consumer = build_consumer(publisher)
    message = FakeMessage(b'{"service":"demo-api"}', message_id="bad-schema")

    consumer._process_message(RequiredPayload.model_validate, message)

    assert message.acked == 1
    assert message.nacked == 0
    assert len(publisher.calls) == 1
    body = json.loads(publisher.calls[0][1].decode("utf-8"))
    assert body["original_message_id"] == "bad-schema"
    assert body["error_type"] == "ValidationError"


def test_transient_handler_failure_is_retried_without_dead_letter() -> None:
    publisher = FakePublisher()
    consumer = build_consumer(publisher)
    message = FakeMessage(b'{"service":"demo-api"}', message_id="transient")

    def fail_transiently(payload: dict[str, object]) -> None:
        raise RuntimeError("Firestore temporarily unavailable")

    consumer._process_message(fail_transiently, message)

    assert message.acked == 0
    assert message.nacked == 1
    assert publisher.calls == []


def test_dead_letter_publish_failure_retries_original_message() -> None:
    publisher = FakePublisher(error=RuntimeError("dead-letter publish unavailable"))
    consumer = build_consumer(publisher)
    message = FakeMessage(b'{"service":', message_id="dlq-down")

    consumer._process_message(lambda payload: None, message)

    assert message.acked == 0
    assert message.nacked == 1
    assert len(publisher.calls) == 1
