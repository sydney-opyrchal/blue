"""
Wire-format contracts for SPEC §6.

These models are the single source of truth for what enters the system over
MQTT (telemetry) and what leaves it over the WebSocket (alarms, envelopes).
Validation lives at the boundaries (ingest, REST handlers); internal code
should pass model instances, not dicts.
"""
from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator


SCHEMA_VERSION = "1.0"

DEVICE_ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
TAG_RE = re.compile(r"^[a-z0-9]+(_[a-z0-9]+)*$")
ULID_RE = re.compile(r"^alm_[0-9A-HJKMNP-TV-Z]{26}$")


class Quality(str, Enum):
    GOOD = "good"
    UNCERTAIN = "uncertain"
    BAD = "bad"
    STALE = "stale"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlarmState(str, Enum):
    RAISED = "raised"
    ACKNOWLEDGED = "acknowledged"
    CLEARED = "cleared"


class TelemetryMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unit: str
    site: str
    bay: str
    cell: str


class Telemetry(BaseModel):
    """SPEC §6.1 — payload published to factory/{site}/{bay}/{cell}/{device_id}/{tag}."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"]
    timestamp: datetime
    device_id: str
    tag: str
    value: Union[float, bool]
    quality: Quality
    metadata: TelemetryMetadata

    @field_validator("device_id")
    @classmethod
    def _device_id_format(cls, v: str) -> str:
        if not DEVICE_ID_RE.match(v):
            raise ValueError("device_id must be lowercase, hyphenated")
        return v

    @field_validator("tag")
    @classmethod
    def _tag_format(cls, v: str) -> str:
        if not TAG_RE.match(v):
            raise ValueError("tag must be lowercase snake_case")
        return v


class Alarm(BaseModel):
    """SPEC §6.2 — emitted on alarm state change, persisted to alarms table."""

    model_config = ConfigDict(extra="forbid")

    alarm_id: str
    device_id: str
    tag: str
    current_value: float
    expected_range: tuple[float, float]
    severity: Severity
    state: AlarmState
    raised_at: datetime
    acknowledged_at: datetime | None = None
    acknowledged_by: str | None = None
    cleared_at: datetime | None = None
    detector: str

    @field_validator("alarm_id")
    @classmethod
    def _alarm_id_format(cls, v: str) -> str:
        if not ULID_RE.match(v):
            raise ValueError("alarm_id must be 'alm_' + 26-char ULID")
        return v


class MachineStatusPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str
    status: Literal["healthy", "degraded", "alarming"]
    reason: str | None = None


class SystemStatusPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    broker: Literal["up", "down", "degraded"]
    db: Literal["up", "down", "degraded"]
    ingest: Literal["up", "down", "degraded"]
    last_message_at: datetime | None = None


# SPEC §6.3 — discriminated envelope. The `type` field selects the payload.

class _EnvelopeBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: datetime


class TelemetryEnvelope(_EnvelopeBase):
    type: Literal["telemetry"]
    payload: Telemetry


class AlarmEnvelope(_EnvelopeBase):
    type: Literal["alarm"]
    payload: Alarm


class MachineStatusEnvelope(_EnvelopeBase):
    type: Literal["machine_status"]
    payload: MachineStatusPayload


class SystemStatusEnvelope(_EnvelopeBase):
    type: Literal["system_status"]
    payload: SystemStatusPayload


WSEnvelope = Annotated[
    Union[
        TelemetryEnvelope,
        AlarmEnvelope,
        MachineStatusEnvelope,
        SystemStatusEnvelope,
    ],
    Field(discriminator="type"),
]
