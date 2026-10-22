"""Server-observed health verification for SentinelOps incidents."""
from __future__ import annotations

import json
import os
from typing import Any

from src.tools.health import get_health_status


def approved_health_url(service: str, requested_url: str) -> str:
    """Production health URLs originate from trusted server config, never client choice."""
    if os.getenv("SENTINELOPS_ENV", "development").strip().lower() not in {"production", "staging"}:
        return requested_url
    try:
        targets = json.loads(os.getenv("SENTINELOPS_VERIFICATION_TARGETS_JSON", "{}"))
    except json.JSONDecodeError as exc:
        raise ValueError("Verification targets configuration is invalid") from exc
    if not isinstance(targets, dict) or not isinstance(targets.get(service), str):
        raise ValueError("No trusted verification URL configured for the incident service")
    expected = targets[service]
    if not expected.startswith("https://") or requested_url != expected:
        raise ValueError("Verification URL does not match the configured target")
    return expected


def verify_health(url: str, timeout_seconds: float = 3.0, expected_status: int = 200) -> dict[str, Any]:
    """Perform a read-only health check; a caller cannot supply passed=True."""
    result = get_health_status(url, timeout_seconds, expected_status)
    return {
        "passed": bool(result.get("healthy")),
        "url": url,
        "status_code": result.get("status_code"),
        "expected_status": expected_status,
        "notes": result.get("reason", "Healthcheck completed"),
    }
