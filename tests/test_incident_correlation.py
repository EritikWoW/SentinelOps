from datetime import datetime, timedelta, timezone

import src.main as main
from src.models.events import NormalizedEvent
from src.models.incident import IncidentAnalysis, IncidentCreate, IncidentResponse
from src.services.incident_store import IncidentStore


def _analysis() -> IncidentAnalysis:
    return IncidentAnalysis(
        root_cause_hypothesis="Cloud Run revision is returning 5xx",
        evidence=["HTTP 500"],
        remediation_action="Rollback to the previous healthy revision",
        risk_level="high",
        requires_human_approval=True,
        verification_plan=["Check health endpoint"],
        incident_summary="demo-api is unhealthy",
    )


def _stored_incident(*, trigger: str = "cloud_run_http_5xx", status: str = "analyzed") -> IncidentResponse:
    payload = IncidentCreate(
        service="demo-api",
        severity="high",
        summary="HTTP 500",
        source="cloud_logging",
        node_id="gcp:cloud_run_revision:demo-api",
        trigger=trigger,
        evidence=["HTTP status: 500"],
    )
    incident = IncidentResponse.analyzed(payload, _analysis(), execution_mode="gemini")
    incident.status = status
    return incident


def _event(trigger: str = "cloud_run_http_5xx") -> NormalizedEvent:
    return NormalizedEvent(
        event_id="gcp_log_req500",
        node_id="gcp:cloud_run_revision:demo-api",
        hostname="demo-api-00004-wlk",
        service="demo-api",
        severity="high",
        source="cloud_logging",
        trigger=trigger,
        message="Cloud Run request returned HTTP 500",
    )


def test_recent_matching_detector_event_reuses_unresolved_incident(monkeypatch) -> None:
    store = IncidentStore()
    incident = _stored_incident()
    store.save(incident)
    monkeypatch.setattr(main, "incident_store", store)
    monkeypatch.setenv("SENTINELOPS_INCIDENT_CORRELATION_SECONDS", "60")

    correlated = main._find_correlated_incident(_event())

    assert correlated is not None
    assert correlated.incident_id == incident.incident_id


def test_resolved_or_different_trigger_does_not_correlate(monkeypatch) -> None:
    store = IncidentStore()
    store.save(_stored_incident(status="resolved"))
    monkeypatch.setattr(main, "incident_store", store)
    monkeypatch.setenv("SENTINELOPS_INCIDENT_CORRELATION_SECONDS", "60")

    assert main._find_correlated_incident(_event()) is None

    store = IncidentStore()
    store.save(_stored_incident(trigger="different_trigger"))
    monkeypatch.setattr(main, "incident_store", store)
    assert main._find_correlated_incident(_event()) is None


def test_process_detector_event_skips_second_analysis(monkeypatch) -> None:
    store = IncidentStore()
    incident = _stored_incident()
    incident.created_at = datetime.now(timezone.utc) - timedelta(seconds=5)
    store.save(incident)
    monkeypatch.setattr(main, "incident_store", store)
    monkeypatch.setenv("SENTINELOPS_INCIDENT_CORRELATION_SECONDS", "60")

    analyzed: list[IncidentCreate] = []
    monkeypatch.setattr(main, "_analyze_and_store", lambda payload: analyzed.append(payload))

    published: list[tuple[str, dict[str, object]]] = []

    class Publisher:
        def publish(self, event_type: str, payload: dict[str, object]) -> None:
            published.append((event_type, payload))

    monkeypatch.setattr(main, "event_publisher", Publisher())

    correlated = main._process_detector_event(_event())

    assert correlated.incident_id == incident.incident_id
    assert analyzed == []
    assert published[0][0] == "incident.correlated"
    assert published[0][1]["incident_id"] == incident.incident_id
