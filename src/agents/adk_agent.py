"""Google ADK agent graph for the SentinelOps incident workflow."""

from __future__ import annotations

import asyncio
import json
import os

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.runners import InMemoryRunner

from src.models.incident import IncidentAnalysis, IncidentCreate
from src.tools.health import get_health_status
from src.tools.logs import get_recent_logs
from src.tools.process import get_process_status


# Load local development settings without overriding Cloud Run environment values.
load_dotenv(override=False)

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")

SAFETY_INSTRUCTION = """
SentinelOps is an incident commander, not an unrestricted infrastructure operator.
Read-only investigation and health checks are allowed. Never claim that a rollback,
restart, deployment, database mutation, or other external side effect was executed.
For high-impact or destructive actions set requires_human_approval to true.
Only use evidence present in the incident input or supplied by another agent.
The incident is not resolved until the verification plan is explicit.
""".strip()


def _configure_gemini_runtime() -> None:
    """Configure ADK/Gen AI SDK to use Vertex AI with Application Default Credentials."""

    project = os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "global").strip() or "global"
    if not project:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT is required for Gemini mode")

    # Google ADK uses the Google Gen AI SDK underneath. These environment values
    # select Vertex AI, where Cloud Run authenticates with its attached service
    # account through Application Default Credentials; no Gemini API key is needed.
    os.environ["GOOGLE_CLOUD_PROJECT"] = project
    os.environ["GOOGLE_CLOUD_LOCATION"] = location
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"


def _specialist(name: str, role: str) -> Agent:
    return Agent(
        name=name,
        model=MODEL,
        instruction=(
            f"You are the SentinelOps {role}. {SAFETY_INSTRUCTION} "
            "Return concise findings for the incident commander; do not invent tools or data."
        ),
    )


def build_root_agent() -> Agent:
    """Build the coordinator and specialist-agent graph used by the MVP."""

    return Agent(
        name="sentinelops_incident_commander",
        model=MODEL,
        description="Coordinates investigation and safe remediation planning for service incidents.",
        instruction=(
            "You are the SentinelOps Incident Commander. Follow this workflow: "
            "detect -> investigate -> decide -> remediate -> verify -> report. "
            "Delegate relevant investigation to the specialist agents. Your final answer is constrained "
            "by the IncidentAnalysis output schema. Populate every required field using only bounded "
            "incident evidence and actual tool results. "
            f"{SAFETY_INSTRUCTION} "
            "Use only the supplied evidence and these read-only tools when their inputs are available. "
            "Never claim that a tool was called unless its result is present."
        ),
        output_schema=IncidentAnalysis,
        tools=[get_recent_logs, get_health_status, get_process_status],
        sub_agents=[
            _specialist("log_analysis_agent", "Log Analysis Agent"),
            _specialist("infrastructure_agent", "Infrastructure Agent"),
            _specialist("code_analysis_agent", "Code Analysis Agent"),
            _specialist("remediation_agent", "Remediation Agent"),
            _specialist("verification_agent", "Verification Agent"),
        ],
    )


class ADKIncidentAgent:
    """Synchronous application boundary around the asynchronous ADK runner."""

    def __init__(self) -> None:
        self.mode = os.getenv("SENTINELOPS_MODE", "demo").strip().lower()
        if self.mode not in {"demo", "gemini"}:
            raise RuntimeError("SENTINELOPS_MODE must be either 'demo' or 'gemini'")
        if self.mode == "gemini":
            _configure_gemini_runtime()
            self.root_agent = build_root_agent()
        else:
            self.root_agent = None

    def analyze(self, incident: IncidentCreate) -> str:
        """Run one isolated incident analysis and return the final JSON text."""

        if self.mode == "demo":
            return json.dumps(_demo_analysis(incident), ensure_ascii=False)

        prompt = (
            "Analyze this incident and produce the required structured response.\n"
            f"Service: {incident.service}\n"
            f"Severity: {incident.severity}\n"
            f"Summary: {incident.summary}\n"
            f"Source: {incident.source}\n"
            f"Trigger: {incident.trigger or 'manual'}\n"
            f"Node: {incident.node_id or 'none'}\n"
            f"Bounded evidence: {json.dumps([item.model_dump(mode='json') if hasattr(item, 'model_dump') else item for item in incident.evidence], ensure_ascii=False)}"
        )
        try:
            return asyncio.run(self._run(prompt))
        except Exception as exc:
            # Avoid leaking provider traces or credential metadata through the API.
            if "PERMISSION_DENIED" in str(exc) or "403" in str(exc):
                raise RuntimeError(
                    "Vertex AI rejected the request (403). Grant the Cloud Run runtime service account "
                    "Vertex AI User and verify that aiplatform.googleapis.com is enabled."
                ) from exc
            raise RuntimeError(f"Gemini request failed: {type(exc).__name__}") from exc

    async def _run(self, prompt: str) -> str:
        if self.root_agent is None:
            raise RuntimeError("The ADK agent is unavailable in demo mode")
        runner = InMemoryRunner(agent=self.root_agent, app_name="sentinelops")
        events = await runner.run_debug(
            prompt,
            user_id="sentinelops-api",
            session_id="incident-analysis",
            quiet=True,
        )
        for event in reversed(events):
            content = getattr(event, "content", None)
            if not content or not getattr(content, "parts", None):
                continue
            for part in reversed(content.parts):
                text = getattr(part, "text", None)
                if text:
                    return _extract_json(text)
        raise RuntimeError("ADK returned no final analysis")


def _demo_analysis(incident: IncidentCreate) -> dict[str, object]:
    """Produce a deterministic, auditable incident run without calling Gemini."""

    summary = incident.summary.lower()
    deployment_signal = "deployment" in summary or "release" in summary or "revision" in summary
    cause = (
        "The incident is correlated with a recent deployment or revision change."
        if deployment_signal
        else "The supplied incident summary indicates a service failure, but more operational evidence is required."
    )
    evidence = [f"Incident reported for service '{incident.service}'.", incident.summary]
    if deployment_signal:
        evidence.append("The summary contains a deployment/revision signal; no external logs were queried in demo mode.")

    approval = incident.severity in {"high", "critical"}
    action = (
        "Simulate rollback to the previous known-good revision; request human approval before any real production change."
        if approval
        else "Simulate a restart of the test workload, then run health checks; no external action is executed."
    )
    timeline = [
        {"stage": "detect", "status": "completed", "detail": "Incident accepted from the API."},
        {"stage": "investigate", "status": "completed", "detail": "Evidence bounded to the supplied incident payload."},
        {"stage": "decide", "status": "completed", "detail": "Selected a reversible remediation plan."},
        {"stage": "remediate", "status": "completed", "detail": "Simulation only; no infrastructure mutation was executed."},
        {"stage": "verify", "status": "completed", "detail": "Demo health-check verification plan generated."},
        {"stage": "report", "status": "completed", "detail": "Structured incident report returned to the caller."},
    ]
    return {
        "root_cause_hypothesis": cause,
        "evidence": evidence,
        "remediation_action": action,
        "risk_level": "high" if approval else "low",
        "requires_human_approval": approval,
        "verification_plan": [
            "Check the service health endpoint.",
            "Confirm HTTP 5xx rate returns to baseline.",
            "Confirm latency and revision status are healthy.",
        ],
        "incident_summary": "Deterministic SentinelOps demo run completed without external side effects.",
        "remediation_status": "simulated",
        "execution_notes": "Demo mode is active; no infrastructure mutation was executed. Switch SENTINELOPS_MODE to 'gemini' to call Google ADK.",
        "timeline": timeline,
    }


def _extract_json(text: str) -> str:
    """Accept plain JSON or a fenced JSON response from the model."""

    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.removeprefix("```").removeprefix("json").removesuffix("```").strip()
    try:
        json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"ADK returned non-JSON analysis: {exc}") from exc
    return candidate
