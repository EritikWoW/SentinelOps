"""Bounded tail-style log collector with configurable trigger rules."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from src.models.evidence import EvidenceItem
from src.models.events import NormalizedEvent


@dataclass(frozen=True, slots=True)
class LogRule:
    pattern: str
    severity: str = "high"


@dataclass(slots=True)
class LogFileCollector:
    """Read only appended bytes and emit events for matching rules."""

    node_id: str
    service: str
    path: str
    rules: list[LogRule]
    context_before: int = 3
    context_after: int = 2
    _offset: int = field(default=0, init=False)
    _initialized: bool = field(default=False, init=False)
    _recent_lines: deque[str] = field(default_factory=lambda: deque(maxlen=20), init=False)

    def poll(self) -> list[NormalizedEvent]:
        log_path = Path(self.path)
        if not log_path.exists() or not log_path.is_file():
            return []
        try:
            size = log_path.stat().st_size
            if not self._initialized:
                self._offset = size
                self._initialized = True
                return []
            if size < self._offset:
                self._offset = 0
                self._recent_lines.clear()
            with log_path.open("rb") as handle:
                handle.seek(self._offset)
                raw = handle.read()
                self._offset = handle.tell()
        except OSError:
            return []
        if not raw:
            return []
        lines = raw.decode("utf-8", errors="replace").splitlines()
        events: list[NormalizedEvent] = []
        for index, line in enumerate(lines):
            matching = next((rule for rule in self.rules if rule.pattern.lower() in line.lower()), None)
            if matching is None:
                self._recent_lines.append(line)
                continue
            before = list(self._recent_lines)[-self.context_before:]
            after = lines[index + 1:index + 1 + self.context_after]
            context = "\n".join([*before, line, *after])
            timestamp = datetime.now(timezone.utc)
            evidence = EvidenceItem(
                type="log",
                source=str(log_path),
                timestamp=timestamp,
                content=context,
                metadata={"rule": matching.pattern, "node_id": self.node_id},
            )
            events.append(
                NormalizedEvent(
                    node_id=self.node_id,
                    service=self.service,
                    severity=matching.severity,  # type: ignore[arg-type]
                    source="log_file",
                    trigger="log_pattern",
                    message=line,
                    timestamp=timestamp,
                    evidence=[evidence],
                    metadata={"path": str(log_path), "rule": matching.pattern},
                )
            )
            self._recent_lines.append(line)
        return events
