from typing import Literal

from pydantic import BaseModel, Field


class SettingsUpdate(BaseModel):
    mode: Literal["demo", "gemini"]
    model: str = Field(min_length=1, max_length=120)
    store: Literal["memory", "file", "firestore"]
    pubsub_enabled: bool
    pubsub_topic: str = Field(min_length=1, max_length=120)
    pubsub_subscription: str = Field(default="", max_length=120)
    firestore_database: str = Field(default="(default)", min_length=1, max_length=120)
    project: str = Field(default="", max_length=120)
    location: str = Field(default="global", min_length=1, max_length=80)
    environment: Literal["development", "staging", "production"] = "development"


class SettingsResponse(BaseModel):
    mode: Literal["demo", "gemini"]
    model: str
    store: Literal["memory", "file", "firestore"]
    pubsub_enabled: bool
    pubsub_topic: str
    pubsub_subscription: str
    firestore_database: str
    project: str
    location: str
    environment: str
    api_key_configured: bool
    human_approval_required: bool = True
    live_remediation_enabled: bool = False
    restart_required: bool = False
    save_target: str = ".env"
