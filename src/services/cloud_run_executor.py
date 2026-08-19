"""Bounded live remediation executor for approved Cloud Run rollbacks."""

from __future__ import annotations

import os

import google.auth
from google.auth.transport.requests import Request
import httpx


class CloudRunExecutionError(RuntimeError):
    """Raised when a bounded Cloud Run remediation cannot be executed."""


def _allowed_services() -> set[str]:
    raw = os.getenv("SENTINELOPS_REMEDIATION_ALLOWED_SERVICES", "")
    return {item.strip() for item in raw.split(",") if item.strip()}


def rollback_cloud_run(service: str, target_revision: str, region: str | None = None) -> str:
    """Route 100 percent of one allowlisted Cloud Run service to one named revision."""

    allowed = _allowed_services()
    if service not in allowed:
        raise CloudRunExecutionError(f"Service '{service}' is not allowlisted for live remediation")
    if not target_revision.startswith(f"{service}-"):
        raise CloudRunExecutionError("Target revision does not belong to the incident service")

    project = os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
    location = (region or os.getenv("GOOGLE_CLOUD_REGION") or "europe-west1").strip()
    if not project:
        raise CloudRunExecutionError("GOOGLE_CLOUD_PROJECT is required for live remediation")

    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    credentials.refresh(Request())
    if not credentials.token:
        raise CloudRunExecutionError("Could not obtain Google Cloud access token")

    url = (
        f"https://run.googleapis.com/v2/projects/{project}/locations/{location}/services/{service}"
        "?updateMask=traffic"
    )
    payload = {
        "traffic": [
            {
                "type": "TRAFFIC_TARGET_ALLOCATION_TYPE_REVISION",
                "revision": target_revision,
                "percent": 100,
            }
        ]
    }
    response = httpx.patch(
        url,
        headers={"Authorization": f"Bearer {credentials.token}"},
        json=payload,
        timeout=30.0,
    )
    if response.status_code >= 400:
        detail = response.text[:1000]
        raise CloudRunExecutionError(
            f"Cloud Run rollback failed with HTTP {response.status_code}: {detail}"
        )

    return f"Cloud Run traffic routed 100% to revision {target_revision} in {location}."
