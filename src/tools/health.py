"""Read-only HTTP health tool."""

from __future__ import annotations

from typing import Any
from urllib.request import Request, urlopen


def get_health_status(url: str, timeout_seconds: float = 3.0, expected_status: int = 200) -> dict[str, Any]:
    """Query one health endpoint and return an honest status result."""

    try:
        request = Request(url, method="GET")
        with urlopen(request, timeout=timeout_seconds) as response:
            status_code = response.status
        return {
            "supported": True,
            "executed": False,
            "healthy": status_code == expected_status,
            "status_code": status_code,
            "expected_status": expected_status,
            "url": url,
            "reason": "Healthcheck completed",
        }
    except Exception as exc:
        return {
            "supported": True,
            "executed": False,
            "healthy": False,
            "status_code": None,
            "url": url,
            "reason": f"Healthcheck failed: {type(exc).__name__}",
        }
