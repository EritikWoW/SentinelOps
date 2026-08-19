"""Allowlist and approval decisions independent of the LLM."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ActionName = Literal[
    "read_logs",
    "health_check",
    "read_process_state",
    "restart_process",
    "restart_service",
    "rollback",
    "delete_resource",
]


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    action: str
    allowed: bool
    requires_human_approval: bool
    reason: str


class SafetyPolicy:
    """Central action policy; agents cannot bypass this class."""

    _AUTO = {"read_logs", "health_check", "read_process_state"}
    _APPROVAL = {"restart_process", "restart_service", "rollback"}

    def evaluate(self, action: str) -> PolicyDecision:
        if action in self._AUTO:
            return PolicyDecision(action, True, False, "Read-only action is allowed automatically")
        if action in self._APPROVAL:
            return PolicyDecision(action, True, True, "Explicit human approval is required")
        return PolicyDecision(action, False, False, "Action is not on the SentinelOps allowlist")
