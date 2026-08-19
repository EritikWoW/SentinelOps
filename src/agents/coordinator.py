from dataclasses import dataclass

from src.agents.adk_agent import ADKIncidentAgent
from src.models.incident import IncidentCreate


@dataclass(slots=True)
class IncidentCoordinator:
    """Application-facing coordinator backed by the Google ADK agent graph."""

    name: str = "incident-coordinator"
    agent: ADKIncidentAgent | None = None

    def __post_init__(self) -> None:
        self.agent = self.agent or ADKIncidentAgent()

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
        """Run the incident through the Google ADK coordinator."""

        assert self.agent is not None
        return self.agent.analyze(incident)

    @property
    def mode(self) -> str:
        assert self.agent is not None
        return self.agent.mode
