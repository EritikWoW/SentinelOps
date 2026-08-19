from datetime import datetime, timezone

from src.models.incident import IncidentAnalysis, IncidentResponse
from src.services.incident_store import IncidentStore


def _executed_incident() -> IncidentResponse:
    return IncidentResponse(
        incident_id="inc_report_test",
        status="analyzed",
        service="demo-api",
        severity="high",
        summary="HTTP 500 after deployment",
        created_at=datetime.now(timezone.utc),
        approval_status="approved",
        analysis=IncidentAnalysis(
            root_cause_hypothesis="The new revision cannot connect to the database.",
            evidence=["health returned HTTP 500"],
            remediation_action="Rollback traffic to the previous healthy revision.",
            risk_level="high",
            requires_human_approval=True,
            verification_plan=["GET /health returns 200"],
            incident_summary="Deployment regression detected.",
            remediation_status="executed",
        ),
    )


def test_successful_verification_appends_report_stage() -> None:
    store = IncidentStore()
    store.save(_executed_incident())

    resolved = store.verify("inc_report_test", True, "Healthcheck completed")

    assert resolved.status == "resolved"
    assert resolved.analysis.verification_status == "passed"
    assert [event.stage for event in resolved.analysis.timeline[-2:]] == ["verify", "report"]
    report = resolved.analysis.timeline[-1]
    assert report.status == "completed"
    assert "Incident inc_report_test resolved." in report.detail
    assert "Root cause: The new revision cannot connect to the database." in report.detail
    assert "Remediation: Rollback traffic to the previous healthy revision." in report.detail
    assert "Verification: Healthcheck completed" in report.detail


def test_failed_verification_still_appends_report_stage() -> None:
    store = IncidentStore()
    store.save(_executed_incident())

    failed = store.verify("inc_report_test", False, "Healthcheck returned 500")

    assert failed.status == "remediation_failed"
    assert failed.analysis.verification_status == "failed"
    assert failed.analysis.timeline[-1].stage == "report"
    assert "Incident inc_report_test remediation failed." in failed.analysis.timeline[-1].detail
    assert "Verification: Healthcheck returned 500" in failed.analysis.timeline[-1].detail
