from dataclasses import dataclass


@dataclass(slots=True)
class IncidentCoordinator:
    """Coordinates the SentinelOps incident lifecycle.

    The first MVP keeps orchestration deterministic. Google ADK agent wiring will
    be added here as the project moves from API scaffold to autonomous workflow.
    """

    name: str = "incident-coordinator"

    def workflow(self) -> tuple[str, ...]:
        return (
            "detect",
            "investigate",
            "decide",
            "remediate",
            "verify",
            "report",
        )
