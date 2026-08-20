from src.services.runtime_settings import current_settings


def test_live_remediation_enabled_when_gemini_project_and_allowlist_are_configured(monkeypatch):
    monkeypatch.setenv("SENTINELOPS_MODE", "gemini")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "sentinelops-test")
    monkeypatch.setenv("SENTINELOPS_REMEDIATION_ALLOWED_SERVICES", "demo-api")

    settings = current_settings()

    assert settings.live_remediation_enabled is True


def test_live_remediation_disabled_without_allowlist(monkeypatch):
    monkeypatch.setenv("SENTINELOPS_MODE", "gemini")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "sentinelops-test")
    monkeypatch.delenv("SENTINELOPS_REMEDIATION_ALLOWED_SERVICES", raising=False)

    settings = current_settings()

    assert settings.live_remediation_enabled is False
