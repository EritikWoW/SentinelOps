import logging

from src.services.event_bus import PubSubEventConsumer


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
    return consumer


def test_pubsub_consumer_acks_valid_message() -> None:
    consumer = build_consumer()
    received: list[dict[str, object]] = []
    message = FakeMessage(b'{"kind":"incident","service":"demo-api"}')

    consumer._process_message(received.append, message)

    assert received == [{"kind": "incident", "service": "demo-api"}]
    assert message.acked is True
    assert message.nacked is False


def test_pubsub_consumer_logs_and_nacks_invalid_message(caplog) -> None:
    consumer = build_consumer()
    message = FakeMessage(b"not-json", message_id="bad-message-42")

    with caplog.at_level(logging.ERROR, logger="src.services.event_bus"):
        consumer._process_message(lambda payload: None, message)

    assert message.acked is False
    assert message.nacked is True
    assert "Failed to process inbound Pub/Sub event; message will be retried" in caplog.text
    record = next(record for record in caplog.records if record.levelno == logging.ERROR)
    assert record.pubsub_message_id == "bad-message-42"
    assert record.pubsub_subscription.endswith("sentinelops-incoming-sub")
