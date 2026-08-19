"""Safe runtime configuration inspection and non-secret .env updates."""

from __future__ import annotations

import os
from pathlib import Path

from src.models.settings import SettingsResponse, SettingsUpdate


CONFIG_KEYS = {
    "SENTINELOPS_MODE": "mode",
    "GEMINI_MODEL": "model",
    "SENTINELOPS_STORE": "store",
    "PUBSUB_ENABLED": "pubsub_enabled",
    "PUBSUB_TOPIC": "pubsub_topic",
    "PUBSUB_SUBSCRIPTION": "pubsub_subscription",
    "FIRESTORE_DATABASE": "firestore_database",
    "GOOGLE_CLOUD_PROJECT": "project",
    "GOOGLE_CLOUD_LOCATION": "location",
    "SENTINELOPS_ENV": "environment",
}


def _bool(value: str | None) -> bool:
    return (value or "false").strip().lower() in {"1", "true", "yes", "on"}


def current_settings() -> SettingsResponse:
    mode = os.getenv("SENTINELOPS_MODE", "demo").strip().lower()
    if mode not in {"demo", "gemini"}:
        mode = "demo"
    store = os.getenv("SENTINELOPS_STORE", "memory").strip().lower()
    if store not in {"memory", "file", "firestore"}:
        store = "memory"
    return SettingsResponse(
        mode=mode,
        model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash"),
        store=store,
        pubsub_enabled=_bool(os.getenv("PUBSUB_ENABLED")),
        pubsub_topic=os.getenv("PUBSUB_TOPIC", "sentinelops-incoming-events"),
        pubsub_subscription=os.getenv("PUBSUB_SUBSCRIPTION", ""),
        firestore_database=os.getenv("FIRESTORE_DATABASE", "(default)"),
        project=os.getenv("GOOGLE_CLOUD_PROJECT", ""),
        location=os.getenv("GOOGLE_CLOUD_LOCATION", "global"),
        environment=os.getenv("SENTINELOPS_ENV", "development"),
        api_key_configured=bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")),
    )


def save_settings(update: SettingsUpdate, env_path: str = ".env") -> SettingsResponse:
    """Persist only approved non-secret configuration keys and never API keys."""

    path = Path(env_path)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    values = {
        "SENTINELOPS_MODE": update.mode,
        "GEMINI_MODEL": update.model,
        "SENTINELOPS_STORE": update.store,
        "PUBSUB_ENABLED": "true" if update.pubsub_enabled else "false",
        "PUBSUB_TOPIC": update.pubsub_topic,
        "PUBSUB_SUBSCRIPTION": update.pubsub_subscription,
        "FIRESTORE_DATABASE": update.firestore_database,
        "GOOGLE_CLOUD_PROJECT": update.project,
        "GOOGLE_CLOUD_LOCATION": update.location,
        "SENTINELOPS_ENV": update.environment,
    }
    lines = existing.splitlines()
    seen: set[str] = set()
    output: list[str] = []
    for line in lines:
        stripped = line.lstrip()
        key = stripped.split("=", 1)[0].strip() if "=" in stripped and not stripped.startswith("#") else ""
        if key in values:
            output.append(f"{key}={values[key]}")
            seen.add(key)
        else:
            output.append(line)
    for key, value in values.items():
        if key not in seen:
            output.append(f"{key}={value}")
    path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    response = current_settings()
    # The running process deliberately keeps its current backend wiring until
    # restart. Return the persisted values, however, so the UI reflects what
    # was actually written instead of showing stale process values.
    response.mode = update.mode
    response.model = update.model
    response.store = update.store
    response.pubsub_enabled = update.pubsub_enabled
    response.pubsub_topic = update.pubsub_topic
    response.pubsub_subscription = update.pubsub_subscription
    response.firestore_database = update.firestore_database
    response.project = update.project
    response.location = update.location
    response.environment = update.environment
    response.restart_required = True
    response.save_target = str(path)
    return response
