"""
Alarm lifecycle — SPEC §6.2 / §7.4.

State machine:
    raised ──ack──► acknowledged ──clear──► cleared
       │                                       ▲
       └────────────────clear──────────────────┘

cleared is terminal. Any other transition raises IllegalTransition. The class
holds its lifecycle in one row (ADR-008): the same Alarm object accumulates
ack/clear timestamps as it moves through states.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ulid import ULID

from app.contracts import Alarm as AlarmModel, AlarmState, Severity


class IllegalTransition(Exception):
    """Raised when an alarm state transition is not permitted."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Alarm:
    """In-memory alarm with state-transition enforcement.

    Wraps the wire-format AlarmModel (contracts.py) so callers get both a typed
    object for state changes and a Pydantic model on demand for serialization.
    """

    def __init__(
        self,
        device_id: str,
        tag: str,
        current_value: float,
        expected_range: tuple[float, float],
        severity: Severity,
        detector: str,
        *,
        now: datetime | None = None,
        alarm_id: str | None = None,
    ):
        self.device_id = device_id
        self.tag = tag
        self.current_value = float(current_value)
        self.expected_range = (float(expected_range[0]), float(expected_range[1]))
        self.severity = Severity(severity)
        self.detector = detector

        self.state: AlarmState = AlarmState.RAISED
        self.raised_at: datetime = now or _utcnow()
        # Derive the ULID from raised_at so injected timestamps drive sort order
        # deterministically; in production this is equivalent to ULID().
        self.alarm_id = alarm_id or f"alm_{ULID.from_datetime(self.raised_at)}"
        self.acknowledged_at: datetime | None = None
        self.acknowledged_by: str | None = None
        self.cleared_at: datetime | None = None

    def acknowledge(self, by: str, *, now: datetime | None = None) -> None:
        if self.state != AlarmState.RAISED:
            raise IllegalTransition(
                f"cannot acknowledge from state {self.state.value}"
            )
        self.state = AlarmState.ACKNOWLEDGED
        self.acknowledged_at = now or _utcnow()
        self.acknowledged_by = by

    def clear(self, *, now: datetime | None = None) -> None:
        if self.state == AlarmState.CLEARED:
            raise IllegalTransition("alarm is already cleared")
        self.state = AlarmState.CLEARED
        self.cleared_at = now or _utcnow()

    def to_model(self) -> AlarmModel:
        return AlarmModel(
            alarm_id=self.alarm_id,
            device_id=self.device_id,
            tag=self.tag,
            current_value=self.current_value,
            expected_range=self.expected_range,
            severity=self.severity,
            state=self.state,
            raised_at=self.raised_at,
            acknowledged_at=self.acknowledged_at,
            acknowledged_by=self.acknowledged_by,
            cleared_at=self.cleared_at,
            detector=self.detector,
        )
