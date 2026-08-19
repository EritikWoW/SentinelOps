"""HTTP healthcheck collector with failure threshold and recovery events."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.error import URLError
from urllib.request import Request, urlopen

from src.models.evidence import EvidenceItem
from src.models.events import NormalizedEvent


@dataclass(slots=True)
class HealthCheckCollector:
    node_id: str
    service: str
    url: str
    interval_seconds: float = 10.0
    timeout_seconds: float = 3.0
    expected_status: int = 200
    failure_threshold: int = 3
    _consecutive_failures: int = field(default=0, init=False)
    _triggered: bool = field(default=False, init=False)

    def poll(self) -> list[NormalizedEvent]:
        timestamp = datetime.now(timezone.utc)
        status_code: int | None = None
        error = ""
        try:
            request = Request(self.url, method="GET")
            with urlopen(request, timeout=self.timeout_seconds) as response:
                status_code = response.status
        except Exception as exc:  # network errors are collector state, not process-fatal
            error = type(exc).__name__

        healthy = status_code == self.expected_status
        if healthy:
            was_triggered = self._triggered
            self._consecutive_failures = 0
            self._triggered = False
            if not was_triggered:
                return []
            evidence = EvidenceItem(
                type="healthcheck",
                source=self.url,
                timestamp=timestamp,
                content=f"Healthcheck recovered with HTTP {status_code}.",
                status_code=status_code,
            )
            return [NormalizedEvent(
                kind="recovery",
                node_id=self.node_id,
                service=self.service,
                severity="low",
                source="healthcheck",
                trigger="health_recovery",
                message=f"{self.service} healthcheck recovered",
                timestamp=timestamp,
                evidence=[evidence],
            )]

        self._consecutive_failures += 1
        if self._consecutive_failures < max(1, self.failure_threshold) or self._triggered:
            return []
        self._triggered = True
        detail = f"Expected HTTP {self.expected_status}, received {status_code}." if status_code else f"Healthcheck failed: {error}."
        evidence = EvidenceItem(
            type="healthcheck",
            source=self.url,
            timestamp=timestamp,
            content=detail,
            status_code=status_code,
            metadata={"consecutive_failures": self._consecutive_failures},
        )
        return [NormalizedEvent(
            node_id=self.node_id,
            service=self.service,
            severity="high",
            source="healthcheck",
            trigger="health_failure_threshold",
            message=f"{self.service} healthcheck failed {self._consecutive_failures} times",
            timestamp=timestamp,
            evidence=[evidence],
            metadata={"failure_threshold": self.failure_threshold},
        )]
