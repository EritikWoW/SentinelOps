import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import ValidationError

from src.agents.coordinator import IncidentCoordinator
from src.models.incident import ApprovalRequest, ExecutionRequest, HealthVerificationRequest, IncidentAnalysis, IncidentCreate, IncidentResponse, VerificationRequest
from src.models.events import EventIngestionResponse, NodeHeartbeat, NodeRecord, NormalizedEvent
from src.models.settings import SettingsResponse, SettingsUpdate
from src.services.event_bus import EventConsumer, build_event_consumer, build_event_publisher
from src.services.ingestion import incident_from_event
from src.services.incident_store import IncidentNotFoundError, build_incident_store
from src.services.node_registry import NodeRegistry, build_node_registry
from src.services.pubsub_push import register_pubsub_push
from src.services.verification import verify_health
from src.policy.safety import SafetyPolicy
from src.services.runtime_settings import current_settings, save_settings

WEB_DIR = Path(__file__).parent / "web"
coordinator = IncidentCoordinator()
incident_store = build_incident_store()
event_publisher = build_event_publisher()
event_consumer: EventConsumer = build_event_consumer()
node_registry: NodeRegistry = build_node_registry()
safety_policy = SafetyPolicy()


def require_control_token(x_sentinelops_token: str | None = Header(default=None)) -> None:
    """Protect mutating control-plane routes when deployment auth is enabled."""

    configured = os.getenv("SENTINELOPS_API_TOKEN", "")
    required = os.getenv("SENTINELOPS_AUTH_REQUIRED", "false").strip().lower() == "true"
    if not configured and not required:
        return
    if not configured:
        raise HTTPException(status_code=503, detail="Control-plane authentication is not configured")
    if x_sentinelops_token != configured:
        raise HTTPException(status_code=401, detail="A valid X-SentinelOps-Token is required")


def _handle_external_event(raw_payload: dict[str, object]) -> None:
    """Validate and route one Pub/Sub payload through the normal event path."""

    payload = NormalizedEvent.model_validate(raw_payload)
    if payload.kind == "recovery":
        event_publisher.publish("incident.recovered", payload.model_dump(mode="json"))
        return
    _analyze_and_store(incident_from_event(payload))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Start pull ingestion only when explicitly selected for local/worker deployments."""

    delivery_mode = os.getenv("PUBSUB_DELIVERY_MODE", "pull").strip().lower()
    if delivery_mode == "pull":
        event_consumer.start(_handle_external_event)
    try:
        yield
    finally:
        if delivery_mode == "pull":
            event_consumer.stop()


app = FastAPI(title="SentinelOps", version="0.3.0", lifespan=lifespan)
register_pubsub_push(app, _handle_external_event)


@app.get("/", include_in_schema=False)
def dashboard_root() -> FileResponse:
    return FileResponse(WEB_DIR / "dashboard.html")


@app.get("/dashboard", include_in_schema=False)
def dashboard() -> FileResponse:
    return FileResponse(WEB_DIR / "dashboard.html")


@app.get("/dashboard.css", include_in_schema=False)
def dashboard_css() -> FileResponse:
    return FileResponse(WEB_DIR / "dashboard.css", media_type="text/css")


@app.get("/dashboard.js", include_in_schema=False)
def dashboard_js() -> FileResponse:
    return FileResponse(WEB_DIR / "dashboard.js", media_type="application/javascript")


@app.get("/dashboard-assets/{asset_path:path}", include_in_schema=False)
def dashboard_asset(asset_path: str) -> FileResponse:
    asset_dir = WEB_DIR / "assets"
    resolved_path = (asset_dir / asset_path).resolve()
    try:
        resolved_path.relative_to(asset_dir.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Dashboard asset not found") from exc
    if not resolved_path.is_file():
        raise HTTPException(status_code=404, detail="Dashboard asset not found")
    return FileResponse(resolved_path)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "sentinelops"}


@app.get("/ready")
def readiness() -> dict[str, object]:
    """Expose a dependency-free readiness contract for Cloud Run probes."""

    return {
        "status": "ready",
        "service": "sentinelops",
        "mode": coordinator.mode,
        "store": os.getenv("SENTINELOPS_STORE", "memory"),
        "pubsub_enabled": os.getenv("PUBSUB_ENABLED", "false").strip().lower() == "true",
        "pubsub_delivery_mode": os.getenv("PUBSUB_DELIVERY_MODE", "pull").strip().lower(),
    }


@app.get("/settings", response_model=SettingsResponse)
def get_settings() -> SettingsResponse:
    """Return safe operational settings without exposing credentials."""

    return current_settings()


@app.post("/nodes/heartbeat", response_model=NodeRecord)
def node_heartbeat(payload: NodeHeartbeat, _: None = Depends(require_control_token)) -> NodeRecord:
    """Register a Node heartbeat and return its current liveness record."""

    return node_registry.heartbeat(payload)


@app.get("/nodes", response_model=list[NodeRecord])
def list_nodes() -> list[NodeRecord]:
    return node_registry.list()


@app.get("/nodes/{node_id}", response_model=NodeRecord)
def get_node(node_id: str) -> NodeRecord:
    node = node_registry.get(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found")
    return node


@app.get("/incidents", response_model=list[IncidentResponse])
def list_incidents(limit: int = 25) -> list[IncidentResponse]:
    """Return recent incidents for the command-center history panel."""

    return incident_store.list(limit)


@app.post("/settings", response_model=SettingsResponse)
def update_settings(payload: SettingsUpdate, _: None = Depends(require_control_token)) -> SettingsResponse:
    """Persist non-secret settings; a process restart applies backend changes."""

    return save_settings(payload, os.getenv("SENTINELOPS_ENV_FILE", ".env"))


@app.get("/events")
def list_events(limit: int = 50) -> list[dict[str, object]]:
    """Return recent local events for debugging and workflow observability."""

    return [event.model_dump(mode="json") for event in event_publisher.recent(limit)]


@app.post("/events", response_model=EventIngestionResponse, status_code=202)
def ingest_event(payload: NormalizedEvent, _: None = Depends(require_control_token)) -> EventIngestionResponse:
    """Accept one bounded detector event and create an incident when needed."""

    if payload.kind == "recovery":
        event_publisher.publish("incident.recovered", payload.model_dump(mode="json"))
        return EventIngestionResponse(event_id=payload.event_id, kind=payload.kind)
    stored = _analyze_and_store(incident_from_event(payload))
    return EventIngestionResponse(event_id=payload.event_id, kind=payload.kind, incident=stored)


@app.post("/events/{event_id}/replay")
def replay_event(event_id: str, _: None = Depends(require_control_token)) -> dict[str, object]:
    """Replay one local event without mutating its original record."""

    try:
        return event_publisher.replay(event_id).model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _analyze_and_store(payload: IncidentCreate) -> IncidentResponse:
    """Analyze a newly received incident and persist its workflow state."""

    try:
        raw_analysis = coordinator.analyze(payload)
        parsed = json.loads(raw_analysis)
        analysis = IncidentAnalysis.model_validate(parsed)
        action = _classify_action(analysis.remediation_action)
        policy_decision = safety_policy.evaluate(action)
        if not policy_decision.allowed:
            analysis.remediation_status = "blocked"
            analysis.execution_notes = f"Safety policy blocked action '{action}': {policy_decision.reason}"
        if policy_decision.requires_human_approval:
            analysis.requires_human_approval = True
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Invalid Gemini analysis response: {exc}",
        ) from exc

    response = IncidentResponse.analyzed(payload, analysis, execution_mode=coordinator.mode)
    if analysis.requires_human_approval:
        response.approval_status = "pending"
    stored = incident_store.save(response)
    if stored.node_id:
        node_registry.record_incident(stored.node_id)
    event_publisher.publish("incident.created", stored.model_dump(mode="json"))
    return stored


def _classify_action(remediation_action: str) -> str:
    """Map model language to a bounded policy action name."""

    lowered = remediation_action.lower()
    if "restart" in lowered:
        return "restart_process"
    if "delete" in lowered or "destroy" in lowered:
        return "delete_resource"
    return "rollback"


@app.post("/incidents", response_model=IncidentResponse, status_code=202)
def create_incident(payload: IncidentCreate, _: None = Depends(require_control_token)) -> IncidentResponse:
    return _analyze_and_store(payload)


@app.get("/incidents/{incident_id}", response_model=IncidentResponse)
def get_incident(incident_id: str) -> IncidentResponse:
    try:
        return incident_store.get(incident_id)
    except IncidentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Incident not found") from exc


@app.post("/incidents/{incident_id}/approval", response_model=IncidentResponse)
def decide_incident_approval(
    incident_id: str,
    payload: ApprovalRequest,
    _: None = Depends(require_control_token),
) -> IncidentResponse:
    try:
        updated = incident_store.decide(incident_id, payload.decision, payload.comment)
        event_publisher.publish("incident.approval_decided", updated.model_dump(mode="json"))
        return updated
    except IncidentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Incident not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/incidents/{incident_id}/execute", response_model=IncidentResponse)
def execute_incident_remediation(incident_id: str, payload: ExecutionRequest, _: None = Depends(require_control_token)) -> IncidentResponse:
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="Explicit execution confirmation is required")
    try:
        updated = incident_store.execute(incident_id)
        event_publisher.publish("incident.remediation_executed", updated.model_dump(mode="json"))
        return updated
    except IncidentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Incident not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/incidents/{incident_id}/verify", response_model=IncidentResponse)
def verify_incident_remediation(incident_id: str, payload: VerificationRequest, _: None = Depends(require_control_token)) -> IncidentResponse:
    try:
        updated = incident_store.verify(incident_id, payload.passed, payload.notes)
        if payload.passed and updated.node_id:
            node_registry.record_resolution(updated.node_id)
        event_publisher.publish("incident.remediation_verified", updated.model_dump(mode="json"))
        return updated
    except IncidentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Incident not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/incidents/{incident_id}/verify/health", response_model=IncidentResponse)
def verify_incident_health(incident_id: str, payload: HealthVerificationRequest, _: None = Depends(require_control_token)) -> IncidentResponse:
    """Verify recovery against a real health endpoint before resolving."""

    result = verify_health(payload.url, payload.timeout_seconds, payload.expected_status)
    try:
        updated = incident_store.verify(incident_id, result["passed"], result["notes"])
        if result["passed"] and updated.node_id:
            node_registry.record_resolution(updated.node_id)
        event_publisher.publish("incident.remediation_verified", updated.model_dump(mode="json"))
        return updated
    except IncidentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Incident not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
