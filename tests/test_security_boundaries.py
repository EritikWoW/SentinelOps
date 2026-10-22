"""Regression checks for the privileged API trust boundary."""
import pytest
from fastapi.testclient import TestClient
from src.auth import validate_security_configuration
from src.main import app
from src.services.verification import approved_health_url

client = TestClient(app)

def test_missing_token_and_config_fail_closed(monkeypatch):
    monkeypatch.delenv("SENTINELOPS_AUTH_REQUIRED", raising=False)
    monkeypatch.delenv("SENTINELOPS_API_TOKEN", raising=False)
    assert client.get("/incidents").status_code == 503
    assert client.get("/settings").status_code == 503
    assert client.get("/health").status_code == 200

def test_constant_time_token_check_on_read(monkeypatch):
    monkeypatch.setenv("SENTINELOPS_AUTH_REQUIRED", "true")
    monkeypatch.setenv("SENTINELOPS_API_TOKEN", "a-strong-control-token-1234")
    assert client.get("/incidents").status_code == 401
    assert client.get("/incidents", headers={"X-SentinelOps-Token": "wrong"}).status_code == 401
    assert client.get("/incidents", headers={"X-SentinelOps-Token": "a-strong-control-token-1234"}).status_code == 200

def test_production_rejects_auth_opt_out_and_memory_store(monkeypatch):
    monkeypatch.setenv("SENTINELOPS_ENV", "production")
    monkeypatch.setenv("SENTINELOPS_AUTH_REQUIRED", "false")
    assert client.get("/incidents").status_code == 503
    monkeypatch.setenv("SENTINELOPS_AUTH_REQUIRED", "true")
    monkeypatch.setenv("SENTINELOPS_API_TOKEN", "a-strong-control-token-1234")
    with pytest.raises(RuntimeError, match="Firestore"):
        validate_security_configuration()
    monkeypatch.setenv("SENTINELOPS_STORE", "firestore")
    validate_security_configuration()

def test_legacy_verify_cannot_inject_passed():
    assert client.post("/incidents/inc_missing/verify", json={"passed": True}).status_code == 422

def test_production_health_target_cannot_be_client_selected(monkeypatch):
    monkeypatch.setenv("SENTINELOPS_ENV", "production")
    monkeypatch.setenv("SENTINELOPS_VERIFICATION_TARGETS_JSON", '{"demo-api":"https://demo.example.com/health"}')
    assert approved_health_url("demo-api", "https://demo.example.com/health") == "https://demo.example.com/health"
    with pytest.raises(ValueError):
        approved_health_url("demo-api", "https://unrelated.example.com/health")
    with pytest.raises(ValueError):
        approved_health_url("other-api", "https://demo.example.com/health")
