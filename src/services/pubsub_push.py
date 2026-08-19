"""Authenticated Pub/Sub push ingress for Cloud Run."""

from __future__ import annotations

import base64
import binascii
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import FastAPI, Header, HTTPException, Response
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import id_token
from pydantic import ValidationError

logger = logging.getLogger(__name__)


def _verify_push_token(authorization: str | None) -> None:
    """Verify the OIDC token attached by an authenticated Pub/Sub push subscription."""

    expected_email = os.getenv("PUBSUB_PUSH_SERVICE_ACCOUNT", "").strip()
    audience = os.getenv("PUBSUB_PUSH_AUDIENCE", "").strip()
    if not expected_email or not audience:
        raise HTTPException(status_code=503, detail="Pub/Sub push authentication is not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Pub/Sub push bearer token")

    token = authorization.removeprefix("Bearer ").strip()
    try:
        claims = id_token.verify_oauth2_token(token, GoogleAuthRequest(), audience=audience)
    except Exception as exc:
        logger.warning("Rejected Pub/Sub push request with invalid OIDC token", exc_info=exc)
        raise HTTPException(status_code=401, detail="Invalid Pub/Sub push token") from exc

    if claims.get("email") != expected_email or claims.get("email_verified") is not True:
        raise HTTPException(status_code=403, detail="Unexpected Pub/Sub push identity")


def _decode_envelope(envelope: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Decode the standard Pub/Sub push envelope into the original JSON payload."""

    message = envelope.get("message")
    if not isinstance(message, dict):
        raise ValueError("Pub/Sub envelope is missing message")
    message_id = str(message.get("messageId") or message.get("message_id") or "unknown")
    data = message.get("data")
    if not isinstance(data, str) or not data:
        raise ValueError("Pub/Sub envelope message.data is missing")
    try:
        decoded = base64.b64decode(data, validate=True).decode("utf-8")
        payload = json.loads(decoded)
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid Pub/Sub message data: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Pub/Sub message data must decode to a JSON object")
    return payload, message_id


def _publish_dead_letter(raw_payload: object, message_id: str, exc: Exception) -> None:
    """Quarantine a permanently invalid push payload before acknowledging delivery."""

    from google.cloud import pubsub_v1

    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    topic = os.getenv("PUBSUB_DEAD_LETTER_TOPIC", "sentinelops-dead-letter-events")
    if not project:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT is required for Pub/Sub dead-letter publishing")

    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(project, topic)
    body = {
        "original_message_id": message_id,
        "subscription": os.getenv("PUBSUB_SUBSCRIPTION", "sentinelops-incoming-sub"),
        "error_type": type(exc).__name__,
        "error": str(exc),
        "raw_data": raw_payload,
        "quarantined_at": datetime.now(timezone.utc).isoformat(),
        "delivery": "push",
    }
    future = publisher.publish(
        topic_path,
        json.dumps(body, ensure_ascii=False, default=str).encode("utf-8"),
        event_type="dead_letter",
        original_message_id=message_id,
    )
    future.result(timeout=10)


def register_pubsub_push(app: FastAPI, handler: Callable[[dict[str, object]], None]) -> None:
    """Register the authenticated HTTP ingress used by the Pub/Sub push subscription."""

    @app.post("/pubsub/events", include_in_schema=False)
    def receive_pubsub_event(
        envelope: dict[str, Any],
        authorization: str | None = Header(default=None),
    ) -> Response:
        _verify_push_token(authorization)

        message_id = "unknown"
        raw_payload: object = envelope
        try:
            raw_payload, message_id = _decode_envelope(envelope)
            handler(raw_payload)
        except (ValueError, ValidationError) as exc:
            try:
                _publish_dead_letter(raw_payload, message_id, exc)
            except Exception as publish_exc:
                logger.exception("Failed to quarantine invalid Pub/Sub push event; requesting retry")
                raise HTTPException(status_code=503, detail="Dead-letter publishing failed") from publish_exc
            logger.warning(
                "Quarantined permanently invalid Pub/Sub push event",
                extra={"pubsub_message_id": message_id},
            )
            return Response(status_code=204)
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception(
                "Transient Pub/Sub push processing failure; requesting retry",
                extra={"pubsub_message_id": message_id},
            )
            raise HTTPException(status_code=503, detail="Transient Pub/Sub processing failure") from exc

        return Response(status_code=204)
