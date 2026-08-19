"""YAML configuration models for a standalone SentinelOps Node."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from src.collectors.log_file import LogRule


class NodeIdentity(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    server_url: str = Field(min_length=1)
    hostname: str = ""
    version: str = "0.1.0"


class LogConfig(BaseModel):
    service: str = Field(min_length=1)
    path: str = Field(min_length=1)
    rules: list[LogRule] = Field(default_factory=list)


class HealthConfig(BaseModel):
    service: str = Field(min_length=1)
    url: str = Field(min_length=1)
    interval_seconds: float = Field(default=10.0, gt=0)
    timeout_seconds: float = Field(default=3.0, gt=0)
    expected_status: int = 200
    failure_threshold: int = Field(default=3, ge=1)


class ProcessConfig(BaseModel):
    service: str = Field(min_length=1)
    name: str = Field(min_length=1)


class CollectorConfig(BaseModel):
    logs: list[LogConfig] = Field(default_factory=list)
    healthchecks: list[HealthConfig] = Field(default_factory=list)
    processes: list[ProcessConfig] = Field(default_factory=list)


class NodeConfig(BaseModel):
    node: NodeIdentity
    collectors: CollectorConfig = Field(default_factory=CollectorConfig)
    poll_interval_seconds: float = Field(default=5.0, gt=0)
    heartbeat_interval_seconds: float = Field(default=30.0, gt=0)

    @classmethod
    def from_file(cls, path: str) -> "NodeConfig":
        raw: dict[str, Any] = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        return cls.model_validate(raw)
