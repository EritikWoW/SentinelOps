"""Operating-system service adapter boundary."""

from __future__ import annotations

from typing import Any


class ServiceRemediationAdapter:
    """Windows Service/systemd/Docker adapters can be plugged in later."""

    def restart(self, service_name: str) -> dict[str, Any]:
        return {
            "action": "restart_service",
            "supported": False,
            "executed": False,
            "reason": f"Service execution adapter is not configured for '{service_name}'",
        }
