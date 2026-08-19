"""Read-only HTTP health tool."""

from __future__ import annotations

import ipaddress
import socket
from typing import Any
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class _NoRedirectHandler(HTTPRedirectHandler):
    """Healthchecks must not follow an unvalidated redirect target."""

    def redirect_request(self, req, fp, code, msg, headers, new):
        return None


_NO_REDIRECT_OPENER = build_opener(_NoRedirectHandler)


def _validate_health_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Healthcheck URL must use http or https and include a hostname")
    if parsed.username or parsed.password:
        raise ValueError("Healthcheck URL must not contain credentials")
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(parsed.hostname, parsed.port, type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise ValueError("Healthcheck hostname could not be resolved") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if any((ip.is_private, ip.is_loopback, ip.is_link_local, ip.is_multicast, ip.is_reserved, ip.is_unspecified)):
            raise ValueError("Healthcheck target must not resolve to a private or local address")


def get_health_status(url: str, timeout_seconds: float = 3.0, expected_status: int = 200) -> dict[str, Any]:
    """Query one health endpoint and return an honest status result."""

    try:
        _validate_health_url(url)
        request = Request(url, method="GET")
        with _NO_REDIRECT_OPENER.open(request, timeout=timeout_seconds) as response:
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
            "reason": f"Healthcheck failed: {exc}",
        }
