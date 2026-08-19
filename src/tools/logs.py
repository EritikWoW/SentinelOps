"""Bounded read-only log tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def get_recent_logs(path: str, max_lines: int = 50) -> dict[str, Any]:
    """Return a bounded tail of a text log without mutating the file."""

    bounded = max(1, min(max_lines, 500))
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return {"supported": True, "executed": False, "reason": f"Unable to read log: {type(exc).__name__}", "path": path, "lines": []}
    return {"supported": True, "executed": False, "reason": "Read-only log inspection completed", "path": path, "lines": lines[-bounded:]}
