"""Standalone SentinelOps Node process."""

from __future__ import annotations

import argparse
import json
import platform
import time
from dataclasses import dataclass, field
from urllib.error import URLError
from urllib.request import Request, urlopen

from src.collectors.base import Collector
from src.collectors.healthcheck import HealthCheckCollector
from src.collectors.log_file import LogFileCollector
from src.collectors.process import ProcessCollector
from src.models.events import NodeHeartbeat, NormalizedEvent
from src.node.config import NodeConfig


def _post_json(url: str, payload: object, timeout: float = 5.0) -> None:
    body = json.dumps(payload.model_dump(mode="json") if hasattr(payload, "model_dump") else payload).encode("utf-8")
    request = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=timeout):
        return


@dataclass(slots=True)
class SentinelOpsNode:
    config: NodeConfig
    _collectors: list[Collector] = field(init=False, default_factory=list)

    def __post_init__(self) -> None:
        identity = self.config.node
        self._collectors: list[Collector] = [
            LogFileCollector(identity.id, item.service, item.path, item.rules)
            for item in self.config.collectors.logs
        ]
        self._collectors.extend(
            HealthCheckCollector(
                identity.id,
                item.service,
                item.url,
                item.interval_seconds,
                item.timeout_seconds,
                item.expected_status,
                item.failure_threshold,
            )
            for item in self.config.collectors.healthchecks
        )
        self._collectors.extend(
            ProcessCollector(identity.id, item.service, item.name)
            for item in self.config.collectors.processes
        )

    def heartbeat(self) -> None:
        identity = self.config.node
        payload = NodeHeartbeat(
            node_id=identity.id,
            hostname=identity.hostname or platform.node(),
            platform=platform.system().lower(),
            version=identity.version,
            services=sorted({getattr(item, "service", "") for item in self._collectors if getattr(item, "service", "")}),
        )
        _post_json(f"{identity.server_url.rstrip('/')}/nodes/heartbeat", payload)

    def poll_once(self) -> list[NormalizedEvent]:
        events: list[NormalizedEvent] = []
        for collector in self._collectors:
            try:
                events.extend(collector.poll())
            except Exception:
                # A broken local collector must not stop the Node or its other monitors.
                continue
        for event in events:
            try:
                _post_json(f"{self.config.node.server_url.rstrip('/')}/events", event)
            except (OSError, URLError):
                continue
        return events

    def run_forever(self) -> None:
        next_heartbeat = 0.0
        while True:
            now = time.monotonic()
            if now >= next_heartbeat:
                try:
                    self.heartbeat()
                except (OSError, URLError):
                    pass
                next_heartbeat = now + self.config.heartbeat_interval_seconds
            self.poll_once()
            time.sleep(self.config.poll_interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a SentinelOps Node collector")
    parser.add_argument("--config", required=True, help="Path to node.yaml")
    args = parser.parse_args()
    SentinelOpsNode(NodeConfig.from_file(args.config)).run_forever()


if __name__ == "__main__":
    main()
