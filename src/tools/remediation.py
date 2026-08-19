"""Safe remediation boundary; unsupported actions never report fake success."""

from __future__ import annotations

from typing import Any

from src.tools.adapters.process_adapter import ProcessRemediationAdapter
from src.tools.adapters.service_adapter import ServiceRemediationAdapter


def _unsupported(action: str, reason: str) -> dict[str, Any]:
    return {"action": action, "supported": False, "executed": False, "reason": reason}


def restart_process(process_name: str) -> dict[str, Any]:
    """Return an explicit unsupported result until a configured adapter exists."""

    return ProcessRemediationAdapter().restart(process_name)


def restart_service(service_name: str) -> dict[str, Any]:
    """Return an explicit unsupported result; do not invoke shell commands."""

    return ServiceRemediationAdapter().restart(service_name)
