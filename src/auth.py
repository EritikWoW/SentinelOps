"""Fail-closed application authentication for SentinelOps operator-facing APIs."""
from __future__ import annotations

import hmac
import os
from fastapi import Header, HTTPException


def auth_required() -> bool:
    environment = os.getenv("SENTINELOPS_ENV", "development").strip().lower()
    preference = os.getenv("SENTINELOPS_AUTH_REQUIRED", "true").strip().lower()
    if environment in {"production", "staging"} and preference == "false":
        raise HTTPException(status_code=503, detail="Control-plane authentication cannot be disabled")
    return preference != "false"


def validate_security_configuration() -> None:
    """Fail startup before opening any production HTTP listener with unsafe state."""
    if os.getenv("SENTINELOPS_ENV", "development").strip().lower() not in {"production", "staging"}:
        return
    if not auth_required() or len(os.getenv("SENTINELOPS_API_TOKEN", "")) < 16:
        raise RuntimeError("A strong SentinelOps control token is required")
    if os.getenv("SENTINELOPS_STORE", "memory").strip().lower() != "firestore":
        raise RuntimeError("Production/staging requires a shared Firestore incident store")


def require_control_token(x_sentinelops_token: str | None = Header(default=None)) -> None:
    """Pub/Sub ingress is authenticated independently using its Google OIDC token."""
    if not auth_required():
        return
    expected = os.getenv("SENTINELOPS_API_TOKEN", "")
    if len(expected) < 16:
        raise HTTPException(status_code=503, detail="Control-plane authentication is not configured")
    if not x_sentinelops_token or not hmac.compare_digest(x_sentinelops_token, expected):
        raise HTTPException(status_code=401, detail="A valid X-SentinelOps-Token is required")
