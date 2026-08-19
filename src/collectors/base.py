"""Collector protocols shared by log, health, and process monitors."""

from __future__ import annotations

from typing import Protocol

from src.models.events import NormalizedEvent


class Collector(Protocol):
    """A polling collector that never talks to Gemini directly."""

    def poll(self) -> list[NormalizedEvent]: ...
