import json
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from src.agents.coordinator import IncidentCoordinator
from src.main import app
from src.agents.adk_agent import ADKIncidentAgent
from src.collectors.healthcheck import HealthCheckCollector
from src.collectors.log_file import LogFileCollector, LogRule
from src.models.events import NormalizedEvent
from src.policy.safety import SafetyPolicy
from src.tools.remediation import restart_process, restart_service
from src.services.event_bus import InMemoryEventConsumer
from src.models.incident import IncidentCreate
from src.models.incident import IncidentResponse
from src.services.incident_store import JsonIncidentStore

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "sentinelops"}


def test_readiness_contract_is_safe() -> None:
    response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["service"] == "sentinelops"
    assert "GEMINI_API_KEY" not in response.text


def test_application_lifespan_starts_and_stops_event_consumer(monkeypatch) -> None:
    from src import main as main_module

    calls: list[str] = []
    monkeypatch.setattr(main_module.event_consumer, "start", lambda handler: calls.append("start"))
    monkeypatch.setattr(main_module.event_consumer, "stop", lambda: calls.append("stop"))
    with TestClient(main_module.app):
        assert calls == ["start"]
    assert calls == ["start", "stop"]


def test_log_collector_triggers_only_on_matching_appended_line(tmp_path) -> None:
    path = tmp_path / "application.log"
    path.write_text("INFO startup complete\n", encoding="utf-8")
    collector = LogFileCollector(
        node_id="node-test",
        service="demo-app",
        path=str(path),
        rules=[LogRule(pattern="FATAL", severity="critical")],
    )
    assert collector.poll() == []
    with path.open("a", encoding="utf-8") as handle:
        handle.write("INFO still healthy\nFATAL database connection failed\nINFO trailing context\n")
    events = collector.poll()
    assert len(events) == 1
    assert events[0].severity == "critical"
    assert events[0].evidence[0].type == "log"
    assert "database connection failed" in events[0].evidence[0].content
    assert collector.poll() == []


def test_healthcheck_requires_failure_threshold_and_emits_recovery(monkeypatch) -> None:
    class FakeResponse:
        def __init__(self, status: int) -> None:
            self.status = status

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    statuses = iter([500, 500, 500, 200])
    monkeypatch.setattr(
        "src.collectors.healthcheck.urlopen",
        lambda *args, **kwargs: FakeResponse(next(statuses)),
    )
    collector = HealthCheckCollector(
        node_id="node-test",
        service="demo-api",
        url="http://demo.invalid/health",
        failure_threshold=3,
    )
    assert collector.poll() == []
    assert collector.poll() == []
    failure = collector.poll()
    assert len(failure) == 1
    assert failure[0].trigger == "health_failure_threshold"
    recovery = collector.poll()
    assert len(recovery) == 1
    assert recovery[0].kind == "recovery"


def test_node_heartbeat_and_normalized_event_ingestion(monkeypatch) -> None:
    monkeypatch.setattr(
        IncidentCoordinator,
        "analyze",
        lambda self, payload: '{"root_cause_hypothesis":"log trigger", "evidence":["bounded evidence"],'
        '"remediation_action":"inspect service", "risk_level":"high", "requires_human_approval":true,'
        '"verification_plan":["check health"], "incident_summary":"detected"}',
    )
    heartbeat = client.post(
        "/nodes/heartbeat",
        json={"node_id": "node-test", "hostname": "workstation", "platform": "windows", "services": ["demo-api"]},
    )
    assert heartbeat.status_code == 200
    assert heartbeat.json()["status"] == "online"
    assert client.get("/nodes/node-test").json()["node_id"] == "node-test"

    event = NormalizedEvent(
        node_id="node-test",
        service="demo-api",
        severity="high",
        source="log_file",
        trigger="log_pattern",
        message="FATAL database connection failed",
        evidence=[{"type": "log", "source": "application.log", "content": "FATAL database connection failed"}],
    )
    ingested = client.post("/events", json=event.model_dump(mode="json"))
    assert ingested.status_code == 202
    body = ingested.json()
    assert body["accepted"] is True
    assert body["incident"]["source"] == "log_file"
    assert body["incident"]["node_id"] == "node-test"
    assert body["incident"]["evidence"][0]["type"] == "log"
    assert client.get("/nodes/node-test").json()["active_incidents"] == 1


def test_node_incident_resolves_and_decrements_active_count(monkeypatch) -> None:
    monkeypatch.setattr(
        IncidentCoordinator,
        "analyze",
        lambda self, payload: '{"root_cause_hypothesis":"health failure", "evidence":[],'
        '"remediation_action":"rollback after approval", "risk_level":"high", "requires_human_approval":true,'
        '"verification_plan":["check health"], "incident_summary":"detected"}',
    )
    node_id = "node-resolution-test"
    client.post("/nodes/heartbeat", json={"node_id": node_id, "hostname": "host", "platform": "windows"})
    event = NormalizedEvent(
        node_id=node_id,
        service="demo-api",
        severity="high",
        source="healthcheck",
        trigger="health_failure_threshold",
        message="health endpoint returned 500",
        evidence=[{"type": "healthcheck", "source": "http://demo/health", "status_code": 500}],
    )
    created = client.post("/events", json=event.model_dump(mode="json")).json()["incident"]
    assert client.get(f"/nodes/{node_id}").json()["active_incidents"] == 1
    incident_id = created["incident_id"]
    assert client.post(f"/incidents/{incident_id}/approval", json={"decision": "approve"}).status_code == 200
    assert client.post(f"/incidents/{incident_id}/execute", json={"confirm": True}).status_code == 200
    monkeypatch.setattr("src.services.verification.get_health_status", lambda *args: {"healthy": True, "status_code": 200, "reason": "Healthcheck completed"})
    resolved = client.post(f"/incidents/{incident_id}/verify/health", json={"url": "http://demo/health"})
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"
    assert client.get(f"/nodes/{node_id}").json()["active_incidents"] == 0


def test_safety_policy_and_unsupported_remediation_are_honest() -> None:
    policy = SafetyPolicy()
    assert policy.evaluate("read_logs").allowed is True
    assert policy.evaluate("read_logs").requires_human_approval is False
    assert policy.evaluate("restart_service").requires_human_approval is True
    blocked = policy.evaluate("delete_resource")
    assert blocked.allowed is False
    process_result = restart_process("demo.exe")
    service_result = restart_service("DemoService")
    assert process_result == {
        "action": "restart_process",
        "supported": False,
        "executed": False,
        "reason": "Process restart adapter is not configured for 'demo.exe'",
    }
    assert service_result["supported"] is False
    assert service_result["executed"] is False


def test_policy_upgrades_restart_plan_to_approval(monkeypatch) -> None:
    monkeypatch.setattr(
        IncidentCoordinator,
        "analyze",
        lambda self, payload: '{"root_cause_hypothesis":"test", "evidence":[],"remediation_action":"Restart the process after approval",'
        '"risk_level":"low","requires_human_approval":false,"verification_plan":["health"],"incident_summary":"test"}',
    )
    response = client.post("/incidents", json={"service": "worker", "severity": "low", "summary": "worker stopped"})
    assert response.status_code == 202
    assert response.json()["analysis"]["requires_human_approval"] is True
    assert response.json()["approval_status"] == "pending"


def test_policy_blocks_destructive_plan(monkeypatch) -> None:
    monkeypatch.setattr(
        IncidentCoordinator,
        "analyze",
        lambda self, payload: '{"root_cause_hypothesis":"test", "evidence":[],"remediation_action":"Delete the resource",'
        '"risk_level":"critical","requires_human_approval":true,"verification_plan":["health"],"incident_summary":"test"}',
    )
    response = client.post("/incidents", json={"service": "worker", "severity": "critical", "summary": "unsafe action"})
    assert response.status_code == 202
    body = response.json()
    assert body["analysis"]["remediation_status"] == "blocked"
    assert client.post(f"/incidents/{body['incident_id']}/execute", json={"confirm": True}).status_code == 409


def test_health_verification_resolves_or_fails_incident(monkeypatch) -> None:
    monkeypatch.setattr(
        IncidentCoordinator,
        "analyze",
        lambda self, payload: '{"root_cause_hypothesis":"test", "evidence":[],"remediation_action":"rollback after approval",'
        '"risk_level":"high","requires_human_approval":true,"verification_plan":["health"],"incident_summary":"test"}',
    )
    created = client.post("/incidents", json={"service": "api", "severity": "high", "summary": "failure"}).json()
    incident_id = created["incident_id"]
    client.post(f"/incidents/{incident_id}/approval", json={"decision": "approve"})
    client.post(f"/incidents/{incident_id}/execute", json={"confirm": True})
    monkeypatch.setattr("src.services.verification.get_health_status", lambda *args: {"healthy": True, "status_code": 200, "reason": "Healthcheck completed"})
    resolved = client.post(f"/incidents/{incident_id}/verify/health", json={"url": "http://demo/health"})
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"

    failed_created = client.post("/incidents", json={"service": "api-2", "severity": "high", "summary": "failure"}).json()
    failed_id = failed_created["incident_id"]
    client.post(f"/incidents/{failed_id}/approval", json={"decision": "approve"})
    client.post(f"/incidents/{failed_id}/execute", json={"confirm": True})
    monkeypatch.setattr("src.services.verification.get_health_status", lambda *args: {"healthy": False, "status_code": 500, "reason": "Healthcheck failed"})
    failed = client.post(f"/incidents/{failed_id}/verify/health", json={"url": "http://demo/health"})
    assert failed.status_code == 200
    assert failed.json()["status"] == "remediation_failed"


def test_event_consumer_is_separate_from_publisher() -> None:
    consumer = InMemoryEventConsumer()
    received: list[dict[str, object]] = []
    consumer.start(received.append)
    consumer.submit({"event_id": "external-1", "source": "monitoring"})
    consumer.stop()
    consumer.submit({"event_id": "external-2"})
    assert received == [{"event_id": "external-1", "source": "monitoring"}]


def test_settings_are_safe_and_persist_non_secret_values(monkeypatch, tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "GEMINI_API_KEY=keep-this-secret\n"
        "SENTINELOPS_MODE=demo\n"
        "UNRELATED_FLAG=preserve-me\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SENTINELOPS_ENV_FILE", str(env_path))
    monkeypatch.setenv("GEMINI_API_KEY", "keep-this-secret")
    monkeypatch.setenv("SENTINELOPS_MODE", "demo")

    current = client.get("/settings")
    assert current.status_code == 200
    current_body = current.json()
    assert current_body["mode"] == "demo"
    assert current_body["api_key_configured"] is True
    assert current_body["human_approval_required"] is True
    assert current_body["live_remediation_enabled"] is False
    assert "GEMINI_API_KEY" not in current.text
    assert "keep-this-secret" not in current.text

    updated = client.post(
        "/settings",
        json={
            "mode": "gemini",
            "model": "gemini-3.5-flash",
            "store": "file",
            "pubsub_enabled": True,
            "pubsub_topic": "sentinelops-incidents",
            "pubsub_subscription": "sentinelops-events-sub",
            "firestore_database": "(default)",
            "project": "sentinelops-505805",
            "location": "europe-west1",
            "environment": "staging",
        },
    )
    assert updated.status_code == 200
    updated_body = updated.json()
    assert updated_body["mode"] == "gemini"
    assert updated_body["store"] == "file"
    assert updated_body["restart_required"] is True
    persisted = env_path.read_text(encoding="utf-8")
    assert "GEMINI_API_KEY=keep-this-secret" in persisted
    assert "UNRELATED_FLAG=preserve-me" in persisted
    assert "SENTINELOPS_MODE=gemini" in persisted
    assert "SENTINELOPS_STORE=file" in persisted
    assert "PUBSUB_ENABLED=true" in persisted
    assert "PUBSUB_SUBSCRIPTION=sentinelops-events-sub" in persisted
    assert "FIRESTORE_DATABASE=(default)" in persisted


def test_dashboard_assets_are_served() -> None:
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "Incident command center" in page.text
    assert "node-card-status" in page.text
    assert client.get("/dashboard.css").status_code == 200
    assert client.get("/dashboard.js").status_code == 200
    for asset_name in (
        "metric-active.png",
        "metric-workflow.png",
        "metric-safety.png",
        "brand-shield.png",
        "incident-heartbeat.png",
        "workflow-graph.png",
        "safety-shield.png",
        "system-layers.png",
        "document-action.png",
        "verification-shield.png",
        "settings-gear.png",
        "sentinelops-icon-sheet.png",
    ):
        assert client.get(f"/dashboard-assets/{asset_name}").status_code == 200
    assert client.get("/dashboard-assets/sheet/heartbeat.png").status_code == 200
    assert client.get("/dashboard-assets/sheet/container.png").status_code == 200
    assert client.get("/dashboard-assets/sheet/brand-lockup.png").status_code == 200
    assert client.get("/dashboard-assets/sheet/brand-lockup-final.png").status_code == 200
    assert client.get("/dashboard-assets/sheet/button-heartbeat.png").status_code == 200
    assert client.get("/dashboard-assets/sheet/button-flow.png").status_code == 200
    assert client.get("/dashboard-assets/sheet/button-shield-check.png").status_code == 200
    assert client.get("/dashboard-assets/sheet/button-workflow-layers.png").status_code == 200
    assert client.get("/dashboard-assets/sheet/../dashboard.css").status_code == 404


def test_create_incident(monkeypatch) -> None:
    monkeypatch.setattr(
        IncidentCoordinator,
        "analyze",
        lambda self, payload: '{"root_cause_hypothesis":"deployment regression",'
        '"evidence":["HTTP 500 rate exceeded threshold"],'
        '"remediation_action":"prepare rollback to the previous revision",'
        '"risk_level":"medium","requires_human_approval":true,'
        '"verification_plan":["check health endpoint","confirm error rate recovers"],'
        '"incident_summary":"A deployment regression is suspected."}',
    )
    response = client.post(
        "/incidents",
        json={
            "service": "demo-api",
            "severity": "high",
            "summary": "HTTP 500 rate exceeded threshold",
        },
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "analyzed"
    assert body["service"] == "demo-api"
    assert body["incident_id"].startswith("inc_")
    assert body["analysis"]["requires_human_approval"] is True
    assert body["approval_status"] == "pending"

    incident_id = body["incident_id"]
    blocked_execution = client.post(
        f"/incidents/{incident_id}/execute",
        json={"confirm": True},
    )
    assert blocked_execution.status_code == 409
    blocked_verification = client.post(
        f"/incidents/{incident_id}/verify",
        json={"passed": True},
    )
    assert blocked_verification.status_code == 409
    stored = client.get(f"/incidents/{incident_id}")
    assert stored.status_code == 200
    assert stored.json()["incident_id"] == incident_id

    approved = client.post(
        f"/incidents/{incident_id}/approval",
        json={"decision": "approve", "comment": "Approved for the demo rehearsal."},
    )
    assert approved.status_code == 200
    approved_body = approved.json()
    assert approved_body["approval_status"] == "approved"
    assert approved_body["analysis"]["remediation_status"] == "planned"
    assert "simulation-only" in approved_body["analysis"]["execution_notes"]

    executed = client.post(
        f"/incidents/{incident_id}/execute",
        json={"confirm": True},
    )
    assert executed.status_code == 200
    executed_body = executed.json()
    assert executed_body["analysis"]["remediation_status"] == "executed"
    assert "executed locally" in executed_body["analysis"]["execution_notes"]

    verified = client.post(
        f"/incidents/{incident_id}/verify",
        json={"passed": True, "notes": "Local demo health checks passed."},
    )
    assert verified.status_code == 200
    assert verified.json()["analysis"]["verification_status"] == "passed"

    events = client.get("/events?limit=10")
    assert events.status_code == 200
    event_types = [event["event_type"] for event in events.json()]
    assert "incident.created" in event_types
    assert "incident.approval_decided" in event_types
    assert "incident.remediation_executed" in event_types
    assert "incident.remediation_verified" in event_types

    created_event = next(event for event in events.json() if event["event_type"] == "incident.created")
    replayed = client.post(f"/events/{created_event['event_id']}/replay")
    assert replayed.status_code == 200
    assert replayed.json()["event_type"] == "incident.created"
    assert replayed.json()["replayed_from"] == created_event["event_id"]
    assert replayed.json()["attempt"] == 2

    repeated = client.post(
        f"/incidents/{incident_id}/execute",
        json={"confirm": True},
    )
    assert repeated.status_code == 409

    history = client.get("/incidents?limit=5")
    assert history.status_code == 200
    assert any(item["incident_id"] == incident_id for item in history.json())
    reopened = client.get(f"/incidents/{incident_id}")
    assert reopened.status_code == 200
    assert reopened.json()["analysis"]["verification_status"] == "passed"
    assert client.get("/events?limit=8").json()


def test_incident_history_limit_is_bounded(monkeypatch) -> None:
    monkeypatch.setattr(
        IncidentCoordinator,
        "analyze",
        lambda self, payload: '{"root_cause_hypothesis":"test","evidence":[],"remediation_action":"safe demo action",'
        '"risk_level":"low","requires_human_approval":false,"verification_plan":[],"incident_summary":"test"}',
    )
    response = client.get("/incidents?limit=0")
    assert response.status_code == 200


def test_unknown_incident_returns_404() -> None:
    response = client.get("/incidents/inc_missing")
    assert response.status_code == 404


def test_demo_mode_runs_without_gemini(monkeypatch) -> None:
    monkeypatch.setenv("SENTINELOPS_MODE", "demo")

    agent = ADKIncidentAgent()
    raw = agent.analyze(
        IncidentCreate(
            service="demo-api",
            severity="high",
            summary="HTTP 500 rate exceeded after latest deployment",
        )
    )
    body = json.loads(raw)
    assert body["remediation_status"] == "simulated"
    assert len(body["timeline"]) == 6
    assert "no infrastructure mutation" in body["execution_notes"]


def test_json_store_survives_reopen(tmp_path) -> None:
    path = tmp_path / "incidents.json"
    store = JsonIncidentStore(str(path))
    incident = IncidentResponse(
        incident_id="inc_persisted",
        status="analyzed",
        service="demo-api",
        severity="high",
        summary="deployment regression",
        created_at=datetime.now(timezone.utc),
        analysis={
            "root_cause_hypothesis": "deployment",
            "evidence": ["test"],
            "remediation_action": "safe demo action",
            "risk_level": "high",
            "requires_human_approval": True,
            "verification_plan": ["health check"],
            "incident_summary": "test",
            "remediation_status": "planned",
            "timeline": [],
        },
        execution_mode="demo",
        approval_status="pending",
    )
    store.save(incident)
    reopened = JsonIncidentStore(str(path))
    assert reopened.get("inc_persisted").service == "demo-api"
