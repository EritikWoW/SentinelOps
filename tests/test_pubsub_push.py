import base64
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

import src.services.pubsub_push as push


def envelope(payload: object, message_id: str = "msg-1") -> dict[str, object]:
    data = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    return {"message": {"messageId": message_id, "data": data}, "subscription": "projects/test/subscriptions/incoming"}


def test_decode_standard_pubsub_envelope() -> None:
    payload, message_id = push._decode_envelope(envelope({"service": "demo-api"}, "abc"))

    assert payload == {"service": "demo-api"}
    assert message_id == "abc"


def test_push_endpoint_processes_valid_event(monkeypatch) -> None:
    monkeypatch.setattr(push, "_verify_push_token", lambda authorization: None)
    received: list[dict[str, object]] = []
    app = FastAPI()
    push.register_pubsub_push(app, received.append)
    client = TestClient(app)

    response = client.post("/pubsub/events", json=envelope({"service": "demo-api"}), headers={"Authorization": "Bearer test"})

    assert response.status_code == 204
    assert received == [{"service": "demo-api"}]


def test_validation_failure_is_quarantined_and_acknowledged(monkeypatch) -> None:
    class RequiredPayload(BaseModel):
        node_id: str

    monkeypatch.setattr(push, "_verify_push_token", lambda authorization: None)
    quarantined: list[tuple[object, str, Exception]] = []
    monkeypatch.setattr(push, "_publish_dead_letter", lambda raw, message_id, exc: quarantined.append((raw, message_id, exc)))
    app = FastAPI()
    push.register_pubsub_push(app, RequiredPayload.model_validate)
    client = TestClient(app)

    response = client.post("/pubsub/events", json=envelope({"service": "demo-api"}, "bad-schema"), headers={"Authorization": "Bearer test"})

    assert response.status_code == 204
    assert quarantined[0][1] == "bad-schema"


def test_transient_failure_requests_pubsub_retry(monkeypatch) -> None:
    monkeypatch.setattr(push, "_verify_push_token", lambda authorization: None)

    def fail(_: dict[str, object]) -> None:
        raise RuntimeError("Firestore unavailable")

    app = FastAPI()
    push.register_pubsub_push(app, fail)
    client = TestClient(app)

    response = client.post("/pubsub/events", json=envelope({"service": "demo-api"}), headers={"Authorization": "Bearer test"})

    assert response.status_code == 503


def test_missing_push_auth_configuration_is_rejected(monkeypatch) -> None:
    monkeypatch.delenv("PUBSUB_PUSH_SERVICE_ACCOUNT", raising=False)
    monkeypatch.delenv("PUBSUB_PUSH_AUDIENCE", raising=False)

    try:
        push._verify_push_token("Bearer test")
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 503
    else:
        raise AssertionError("Expected authentication configuration failure")
