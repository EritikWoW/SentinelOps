import logging

from src.services.event_bus import PubSubEventConsumer


class FakePublishFuture:
    def result(self, timeout: int | None = None) -> None:
        return None


class FakePublisher:
    def __init__(self) -> None:
        self.published: list[tuple[str, bytes, dict[str, str]]] = []

    def publish(self, topic: str, data: bytes, **attrs: str) -> FakePublishFuture:
        self.published.append((topic, data, attrs))
        return FakePublishFuture()


class FakeMessage:
    def __init__(self, data: bytes, message_id: str = "msg-1") -> None:
        self.data = data
        self.message_id = message_id
        self.acked = False
        self.nacked = False

    def ack(self) -> None:
        self.acked = True

    def nack(self) -> None:
        self.nacked = True


def build_consumer() -> PubSubEventConsumer:
    consumer = object.__new__(PubSubEventConsumer)
    consumer._subscription_path = "projects/test/subscriptions/sentinelops-incoming-sub"
    consumer._dead_letter_topic_path = "projects/test/topics/sentinelops-dead-letter-events"
    consumer._dead_letter_publisher = FakePublisher()
    return consumer


def test_pubsub_consumer_acks_valid_message() -> None:
    consumer = build_consumer()
    received: list[dict[str, object]] = []
    message = FakeMessage(b'{"kind":"incident","service":"demo-api"}')

    consumer._process_message(received.append, message)

    assert received == [{"kind": "incident", "service": "demo-api"}]
    assert message.acked is True
    assert message.nacked is False


def test_pubsub_consumer_quarantines_and_acks_invalid_message(caplog) -> None:
    consumer = build_consumer()
    message = FakeMessage(b"not-json", message_id="bad-message-42")

    with caplog.at_level(logging.WARNING, logger="src.services.event_bus"):
        consumer._process_message(lambda payload: None, message)

    assert message.acked is True
    assert message.nacked is False
    assert "Rejected permanently invalid inbound Pub/Sub event" in caplog.text
    assert "Quarantined invalid inbound Pub/Sub event" in caplog.text
    assert len(consumer._dead_letter_publisher.published) == 1

    record = next(record for record in caplog.records if record.levelno == logging.ERROR)
    assert record.pubsub_message_id == "bad-message-42"
    assert record.pubsub_subscription.endswith("sentinelops-incoming-sub")
    assert record.pubsub_dead_letter_topic.endswith("sentinelops-dead-letter-events")
