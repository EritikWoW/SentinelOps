"""Process remediation adapter with an explicit unsupported default."""

from __future__ import annotations

from typing import Any


class ProcessRemediationAdapter:
    """A future host-specific adapter can implement restart safely here."""

    def restart(self, process_name: str) -> dict[str, Any]:
        return {
            "action": "restart_process",
            "supported": False,
            "executed": False,
            "reason": f"Process restart adapter is not configured for '{process_name}'",
        }
