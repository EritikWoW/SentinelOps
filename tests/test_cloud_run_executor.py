from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.services import cloud_run_executor


class FakeCredentials:
    token = "test-token"

    def refresh(self, _request: object) -> None:
        self.token = "test-token"


class FakeResponse:
    def __init__(self, status_code: int = 200, text: str = "ok") -> None:
        self.status_code = status_code
        self.text = text


def test_rollback_requires_allowlisted_service(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTINELOPS_REMEDIATION_ALLOWED_SERVICES", "demo-api")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "sentinelops-test")

    with pytest.raises(cloud_run_executor.CloudRunExecutionError, match="not allowlisted"):
        cloud_run_executor.rollback_cloud_run("other-api", "other-api-00001-abc", "europe-west1")


def test_rollback_rejects_revision_from_other_service(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTINELOPS_REMEDIATION_ALLOWED_SERVICES", "demo-api")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "sentinelops-test")

    with pytest.raises(cloud_run_executor.CloudRunExecutionError, match="does not belong"):
        cloud_run_executor.rollback_cloud_run("demo-api", "other-api-00001-abc", "europe-west1")


def test_rollback_patches_cloud_run_traffic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTINELOPS_REMEDIATION_ALLOWED_SERVICES", "demo-api")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "sentinelops-test")
    monkeypatch.setattr(cloud_run_executor.google.auth, "default", lambda scopes: (FakeCredentials(), None))
    monkeypatch.setattr(cloud_run_executor, "Request", lambda: object())

    captured: dict[str, object] = {}

    def fake_patch(url: str, headers: dict[str, str], json: dict[str, object], timeout: float) -> FakeResponse:
        captured.update(url=url, headers=headers, json=json, timeout=timeout)
        return FakeResponse()

    monkeypatch.setattr(cloud_run_executor.httpx, "patch", fake_patch)

    detail = cloud_run_executor.rollback_cloud_run(
        "demo-api",
        "demo-api-00003-fqh",
        "europe-west1",
    )

    assert "demo-api-00003-fqh" in detail
    assert "updateMask=traffic" in str(captured["url"])
    assert captured["headers"] == {"Authorization": "Bearer test-token"}
    assert captured["json"] == {
        "traffic": [
            {
                "type": "TRAFFIC_TARGET_ALLOCATION_TYPE_REVISION",
                "revision": "demo-api-00003-fqh",
                "percent": 100,
            }
        ]
    }
