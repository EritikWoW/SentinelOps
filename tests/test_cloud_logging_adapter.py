from src.models.events import NormalizedEvent
from src.services.cloud_logging_adapter import normalize_pubsub_payload


def test_cloud_run_log_entry_becomes_normalized_event() -> None:
    payload = {
        "insertId": "abc123",
        "logName": "projects/test/logs/run.googleapis.com%2Fstderr",
        "severity": "ERROR",
        "timestamp": "2026-08-19T18:00:00Z",
        "textPayload": "demo_api_health_failed version=v2 reason=database connection failed",
        "resource": {
            "type": "cloud_run_revision",
            "labels": {
                "service_name": "demo-api",
                "revision_name": "demo-api-00004-wlk",
                "location": "europe-west1",
            },
        },
    }

    normalized = NormalizedEvent.model_validate(normalize_pubsub_payload(payload))

    assert normalized.event_id == "gcp_log_abc123"
    assert normalized.service == "demo-api"
    assert normalized.severity == "high"
    assert normalized.source == "cloud_logging"
    assert normalized.trigger == "cloud_logging_error"
    assert normalized.hostname == "demo-api-00004-wlk"
    assert "database connection failed" in normalized.message
    assert "Cloud Run revision: demo-api-00004-wlk" in normalized.evidence


def test_native_sentinelops_event_passes_through() -> None:
    payload = {
        "node_id": "node-1",
        "service": "api",
        "severity": "medium",
        "source": "healthcheck",
        "trigger": "http_500",
        "message": "health check failed",
    }

    assert normalize_pubsub_payload(payload) == payload


def test_critical_logging_severity_maps_to_critical() -> None:
    payload = {
        "severity": "CRITICAL",
        "textPayload": "database unavailable",
        "resource": {"type": "cloud_run_revision", "labels": {"service_name": "demo-api"}},
    }

    normalized = NormalizedEvent.model_validate(normalize_pubsub_payload(payload))

    assert normalized.severity == "critical"
