import os

import pytest

from src.agents.adk_agent import _configure_gemini_runtime, build_formatter_agent, build_root_agent
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


def test_root_agent_keeps_tools_without_output_schema() -> None:
    agent = build_root_agent()

    assert agent.output_schema is None
    assert len(agent.tools) == 3
    assert len(agent.sub_agents) == 5


def test_formatter_agent_enforces_schema_without_tools() -> None:
    agent = build_formatter_agent()

    assert agent.output_schema is IncidentAnalysis
    assert agent.tools == []
    assert agent.sub_agents == []
