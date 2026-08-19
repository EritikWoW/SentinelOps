"""Translate Cloud Logging sink payloads into SentinelOps detector events."""

from __future__ import annotations

import json
from typing import Any


def _severity(value: object) -> str:
    level = str(value or "DEFAULT").upper()
    if level in {"EMERGENCY", "ALERT", "CRITICAL"}:
        return "critical"
    if level == "ERROR":
        return "high"
    if level == "WARNING":
        return "medium"
    return "low"


def _request_message(payload: dict[str, Any], service: str) -> str | None:
    http_request = payload.get("httpRequest")
    if not isinstance(http_request, dict):
        return None
    status = http_request.get("status")
    method = str(http_request.get("requestMethod") or "HTTP")
    url = str(http_request.get("requestUrl") or service)
    if status is None:
        return None
    return f"Cloud Run request failed: {method} {url} returned HTTP {status}"


def _message(payload: dict[str, Any], service: str) -> str:
    request_message = _request_message(payload, service)
    if request_message:
        return request_message

    text_payload = payload.get("textPayload")
    if isinstance(text_payload, str) and text_payload.strip():
        return text_payload.strip()

    for field in ("jsonPayload", "protoPayload"):
        value = payload.get(field)
        if isinstance(value, dict) and value:
            return json.dumps(value, ensure_ascii=False, default=str)[:10_000]

    return f"Cloud Logging detected an error for {service}"


def is_cloud_logging_entry(payload: dict[str, Any]) -> bool:
    """Return True when a decoded Pub/Sub payload looks like a LogEntry."""

    resource = payload.get("resource")
    return isinstance(resource, dict) and isinstance(resource.get("type"), str) and any(
        key in payload
        for key in ("logName", "insertId", "textPayload", "jsonPayload", "protoPayload", "httpRequest")
    )


def normalize_pubsub_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Pass native SentinelOps events through and adapt Cloud Logging LogEntry payloads."""

    if not is_cloud_logging_entry(payload):
        return payload

    resource = payload.get("resource") or {}
    labels = resource.get("labels") if isinstance(resource, dict) else {}
    labels = labels if isinstance(labels, dict) else {}

    service = str(labels.get("service_name") or labels.get("service") or resource.get("type") or "unknown-service")
    revision = str(labels.get("revision_name") or "")
    resource_type = str(resource.get("type") or "unknown")
    message = _message(payload, service)
    http_request = payload.get("httpRequest") if isinstance(payload.get("httpRequest"), dict) else {}

    evidence: list[str] = [message]
    if revision:
        evidence.append(f"Cloud Run revision: {revision}")
    if http_request:
        status = http_request.get("status")
        if status is not None:
            evidence.append(f"HTTP status: {status}")
        request_url = http_request.get("requestUrl")
        if request_url:
            evidence.append(f"Request URL: {request_url}")
    if payload.get("logName"):
        evidence.append(f"Log: {payload['logName']}")

    event: dict[str, Any] = {
        "kind": "incident",
        "node_id": f"gcp:{resource_type}:{service}"[:120],
        "hostname": revision,
        "service": service,
        "severity": _severity(payload.get("severity")),
        "source": "cloud_logging",
        "trigger": "cloud_run_http_5xx" if http_request else "cloud_logging_error",
        "message": message,
        "evidence": evidence[:20],
        "metadata": {
            "gcp_log_name": payload.get("logName"),
            "gcp_insert_id": payload.get("insertId"),
            "resource_type": resource_type,
            "resource_labels": labels,
            "http_request": http_request,
        },
    }

    if payload.get("timestamp"):
        event["timestamp"] = payload["timestamp"]
    if payload.get("insertId"):
        event["event_id"] = f"gcp_log_{payload['insertId']}"

    return event
