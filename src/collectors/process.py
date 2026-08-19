"""Portable process-state collector with platform adapters behind one API."""

from __future__ import annotations

import platform
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone

from src.models.evidence import EvidenceItem
from src.models.events import NormalizedEvent


@dataclass(slots=True)
class ProcessCollector:
    node_id: str
    service: str
    process_name: str

    def poll(self) -> list[NormalizedEvent]:
        running, pid = self._status()
        if running:
            return []
        timestamp = datetime.now(timezone.utc)
        evidence = EvidenceItem(
            type="process",
            source=self.process_name,
            timestamp=timestamp,
            content=f"Process {self.process_name} is stopped.",
            metadata={"pid": pid, "platform": platform.system()},
        )
        return [NormalizedEvent(
            node_id=self.node_id,
            service=self.service,
            severity="high",
            source="process",
            trigger="process_stopped",
            message=f"Process {self.process_name} is not running",
            timestamp=timestamp,
            evidence=[evidence],
        )]

    def _status(self) -> tuple[bool, int | None]:
        try:
            if platform.system() == "Windows":
                result = subprocess.run(
                    ["tasklist", "/FI", f"IMAGENAME eq {self.process_name}", "/FO", "CSV", "/NH"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    check=False,
                )
                if "No tasks are running" in result.stdout:
                    return False, None
                first = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
                parts = [part.strip('"') for part in first.split('","')]
                return bool(parts and self.process_name.lower() in parts[0].lower()), int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
            result = subprocess.run(["pgrep", "-x", self.process_name], capture_output=True, text=True, timeout=3, check=False)
            pid_text = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
            return result.returncode == 0, int(pid_text) if pid_text.isdigit() else None
        except (OSError, subprocess.SubprocessError, ValueError):
            return False, None
