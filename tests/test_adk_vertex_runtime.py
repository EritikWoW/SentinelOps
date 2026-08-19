import os

import pytest

from src.agents.adk_agent import _configure_gemini_runtime, build_root_agent
from src.models.incident import IncidentAnalysis


def test_configure_gemini_runtime_selects_vertex_ai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "sentinelops-test")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "global")
    monkeypatch.delenv("GOOGLE_GENAI_USE_VERTEXAI", raising=False)

    _configure_gemini_runtime()

    assert os.environ["GOOGLE_CLOUD_PROJECT"] == "sentinelops-test"
    assert os.environ["GOOGLE_CLOUD_LOCATION"] == "global"
    assert os.environ["GOOGLE_GENAI_USE_VERTEXAI"] == "true"


def test_configure_gemini_runtime_defaults_location(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "sentinelops-test")
    monkeypatch.delenv("GOOGLE_CLOUD_LOCATION", raising=False)

    _configure_gemini_runtime()

    assert os.environ["GOOGLE_CLOUD_LOCATION"] == "global"


def test_configure_gemini_runtime_requires_project(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)

    with pytest.raises(RuntimeError, match="GOOGLE_CLOUD_PROJECT"):
        _configure_gemini_runtime()


def test_root_agent_enforces_incident_analysis_schema() -> None:
    agent = build_root_agent()

    assert agent.output_schema is IncidentAnalysis
