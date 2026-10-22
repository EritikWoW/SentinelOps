"""Offline tests deliberately opt out; staging and production cannot."""
import pytest

@pytest.fixture(autouse=True)
def offline_demo_auth(monkeypatch):
    monkeypatch.setenv("SENTINELOPS_ENV", "development")
    monkeypatch.setenv("SENTINELOPS_AUTH_REQUIRED", "false")
