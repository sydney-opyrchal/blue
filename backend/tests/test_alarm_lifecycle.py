"""Tests for alarm lifecycle transitions — SPEC §6.2, §11.1."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import pytest

from app.alarms import Alarm, IllegalTransition
from app.contracts import AlarmState, Severity


def make_alarm(**overrides) -> Alarm:
    defaults = dict(
        device_id="cnc-07",
        tag="spindle_temp_c",
        current_value=247.8,
        expected_range=(60.0, 200.0),
        severity=Severity.HIGH,
        detector="z_score_and_isolation_forest",
    )
    defaults.update(overrides)
    return Alarm(**defaults)


# -------------------- Construction --------------------

class TestConstruction:
    def test_initial_state_is_raised(self):
        a = make_alarm()
        assert a.state is AlarmState.RAISED
        assert a.acknowledged_at is None
        assert a.acknowledged_by is None
        assert a.cleared_at is None
        assert a.raised_at.tzinfo is not None

    def test_alarm_id_format(self):
        a = make_alarm()
        assert re.match(r"^alm_[0-9A-HJKMNP-TV-Z]{26}$", a.alarm_id)

    def test_alarm_ids_are_unique(self):
        ids = {make_alarm().alarm_id for _ in range(50)}
        assert len(ids) == 50

    def test_ulids_sort_by_creation_time(self):
        # ULIDs are time-ordered at millisecond granularity. With deterministic
        # `now` values a second apart, the lex order must follow the time order.
        t0 = datetime(2026, 5, 3, 12, 0, 0, tzinfo=timezone.utc)
        a1 = make_alarm(now=t0)
        a2 = make_alarm(now=t0 + timedelta(seconds=1))
        assert a1.alarm_id < a2.alarm_id

    def test_severity_coerced_to_enum(self):
        a = make_alarm(severity="critical")
        assert a.severity is Severity.CRITICAL


# -------------------- Legal transitions --------------------

class TestLegalTransitions:
    def test_raised_to_acknowledged(self):
        a = make_alarm()
        a.acknowledge(by="operator-1")
        assert a.state is AlarmState.ACKNOWLEDGED
        assert a.acknowledged_by == "operator-1"
        assert a.acknowledged_at is not None
        assert a.cleared_at is None

    def test_raised_to_cleared_directly(self):
        a = make_alarm()
        a.clear()
        assert a.state is AlarmState.CLEARED
        assert a.cleared_at is not None
        assert a.acknowledged_at is None

    def test_acknowledged_to_cleared(self):
        a = make_alarm()
        a.acknowledge(by="operator-1")
        a.clear()
        assert a.state is AlarmState.CLEARED
        assert a.acknowledged_at is not None
        assert a.cleared_at is not None

    def test_timestamps_are_utc_aware(self):
        a = make_alarm()
        a.acknowledge(by="op")
        assert a.acknowledged_at.tzinfo is not None
        a.clear()
        assert a.cleared_at.tzinfo is not None


# -------------------- Illegal transitions --------------------

class TestIllegalTransitions:
    def test_double_acknowledge_raises(self):
        a = make_alarm()
        a.acknowledge(by="op")
        with pytest.raises(IllegalTransition):
            a.acknowledge(by="op2")

    def test_acknowledge_after_clear_raises(self):
        a = make_alarm()
        a.clear()
        with pytest.raises(IllegalTransition):
            a.acknowledge(by="op")

    def test_double_clear_raises(self):
        a = make_alarm()
        a.clear()
        with pytest.raises(IllegalTransition):
            a.clear()

    def test_acknowledge_from_cleared_after_ack_raises(self):
        a = make_alarm()
        a.acknowledge(by="op")
        a.clear()
        with pytest.raises(IllegalTransition):
            a.acknowledge(by="op")


# -------------------- Serialization --------------------

class TestToModel:
    def test_to_model_returns_valid_pydantic(self):
        a = make_alarm()
        m = a.to_model()
        assert m.alarm_id == a.alarm_id
        assert m.state is AlarmState.RAISED
        assert m.expected_range == (60.0, 200.0)

    def test_to_model_reflects_post_ack_state(self):
        a = make_alarm()
        a.acknowledge(by="op")
        m = a.to_model()
        assert m.state is AlarmState.ACKNOWLEDGED
        assert m.acknowledged_by == "op"
        assert m.acknowledged_at is not None

    def test_to_model_reflects_post_clear_state(self):
        a = make_alarm()
        a.clear()
        m = a.to_model()
        assert m.state is AlarmState.CLEARED
        assert m.cleared_at is not None
