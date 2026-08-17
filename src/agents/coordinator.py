import os
from dataclasses import dataclass

from google import genai
from google.genai import types

from src.models.incident import IncidentCreate


SYSTEM_INSTRUCTION = """
You are SentinelOps, an autonomous AI incident commander.
Analyze the supplied incident as an SRE/DevOps responder.
Return concise, actionable JSON with these keys only:
root_cause_hypothesis, evidence, remediation_action, risk_level,
requires_human_approval, verification_plan, incident_summary.

Rules:
- Never invent evidence that was not supplied.
- Prefer reversible, low-risk remediation.
- Any destructive or high-impact action requires human approval.
- The incident is not resolved until verification succeeds.
""".strip()


@dataclass(slots=True)
class IncidentCoordinator:
    """Coordinates the SentinelOps incident lifecycle with Gemini reasoning."""

    name: str = "incident-coordinator"
    model: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")

    def workflow(self) -> tuple[str, ...]:
        return (
            "detect",
            "investigate",
            "decide",
            "remediate",
            "verify",
            "report",
        )

    def analyze(self, incident: IncidentCreate) -> str:
        """Ask Gemini to produce the first structured incident-response decision."""

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")

        client = genai.Client(api_key=api_key)
        prompt = (
            f"Service: {incident.service}\n"
            f"Severity: {incident.severity}\n"
            f"Incident summary: {incident.summary}\n\n"
            "Perform the investigate -> decide -> remediation planning -> verification planning stages."
        )

        response = client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                temperature=0.2,
            ),
        )

        if not response.text:
            raise RuntimeError("Gemini returned an empty response")

        return response.text
