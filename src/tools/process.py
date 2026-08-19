"""Read-only local process status tool."""

from __future__ import annotations

import platform
import subprocess
from typing import Any


def get_process_status(process_name: str) -> dict[str, Any]:
    """Inspect process state through a platform adapter, never execute actions."""

    try:
        if platform.system() == "Windows":
            result = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {process_name}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            first = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
            running = bool(first and "No tasks are running" not in first and process_name.lower() in first.lower())
            parts = [part.strip('"') for part in first.split('","')]
            pid = int(parts[1]) if running and len(parts) > 1 and parts[1].isdigit() else None
        else:
            result = subprocess.run(["pgrep", "-x", process_name], capture_output=True, text=True, timeout=3, check=False)
            pid_text = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
            running = result.returncode == 0
            pid = int(pid_text) if pid_text.isdigit() else None
        return {"supported": True, "executed": False, "running": running, "pid": pid, "process": process_name, "reason": "Process status read"}
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        return {"supported": True, "executed": False, "running": False, "pid": None, "process": process_name, "reason": f"Process inspection failed: {type(exc).__name__}"}
