"""Verification services that prove health after a remediation boundary."""

from __future__ import annotations

from typing import Any

from src.tools.health import get_health_status


def verify_health(url: str, timeout_seconds: float = 3.0, expected_status: int = 200) -> dict[str, Any]:
    """Run a real read-only healthcheck and return its observed result."""

    result = get_health_status(url, timeout_seconds, expected_status)
    return {
        "passed": bool(result.get("healthy")),
        "url": url,
        "status_code": result.get("status_code"),
        "expected_status": expected_status,
        "notes": result.get("reason", "Healthcheck completed"),
    }
