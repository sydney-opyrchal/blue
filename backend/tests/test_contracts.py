"""Tests for SPEC §6 wire-format contracts."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.contracts import (
    Alarm,
    AlarmEnvelope,
    AlarmState,
    MachineStatusEnvelope,
    Quality,
    Severity,
    SystemStatusEnvelope,
    Telemetry,
    TelemetryEnvelope,
    TelemetryMetadata,
)


VALID_TELEMETRY = {
    "schema_version": "1.0",
    "timestamp": "2026-05-03T16:42:13.500Z",
    "device_id": "cnc-07",
    "tag": "spindle_temp_c",
    "value": 187.4,
    "quality": "good",
    "metadata": {
        "unit": "celsius",
        "site": "merritt-island",
        "bay": "bay-3",
        "cell": "machining-2",
    },
}


VALID_ALARM = {
    "alarm_id": "alm_01HQX2T9R7K8YJWX5MVZP3D4QF",
    "device_id": "cnc-07",
    "tag": "spindle_temp_c",
    "current_value": 247.8,
    "expected_range": [60.0, 200.0],
    "severity": "high",
    "state": "raised",
    "raised_at": "2026-05-03T16:42:14.012Z",
    "acknowledged_at": None,
    "acknowledged_by": None,
    "cleared_at": None,
    "detector": "z_score_and_isolation_forest",
}


# -------------------- Telemetry --------------------

class TestTelemetry:
    def test_valid_payload(self):
        t = Telemetry.model_validate(VALID_TELEMETRY)
        assert t.device_id == "cnc-07"
        assert t.tag == "spindle_temp_c"
        assert t.value == 187.4
        assert t.quality is Quality.GOOD
        assert t.metadata.site == "merritt-island"

    def test_boolean_value_is_allowed(self):
        p = {**VALID_TELEMETRY, "value": True}
        t = Telemetry.model_validate(p)
        assert t.value is True

    def test_rejects_wrong_schema_version(self):
        p = {**VALID_TELEMETRY, "schema_version": "2.0"}
        with pytest.raises(ValidationError):
            Telemetry.model_validate(p)

    def test_rejects_missing_required_field(self):
        p = dict(VALID_TELEMETRY)
        del p["device_id"]
        with pytest.raises(ValidationError):
            Telemetry.model_validate(p)

    def test_rejects_extra_field(self):
        p = {**VALID_TELEMETRY, "rogue_field": "nope"}
        with pytest.raises(ValidationError):
            Telemetry.model_validate(p)

    @pytest.mark.parametrize("bad", ["CNC-07", "cnc_07", "cnc--07", "-cnc", "cnc-", "cnc 07"])
    def test_rejects_bad_device_id(self, bad):
        p = {**VALID_TELEMETRY, "device_id": bad}
        with pytest.raises(ValidationError):
            Telemetry.model_validate(p)

    @pytest.mark.parametrize("bad", ["SpindleTemp", "spindle-temp", "_spindle", "spindle_", "spindle__temp"])
    def test_rejects_bad_tag(self, bad):
        p = {**VALID_TELEMETRY, "tag": bad}
        with pytest.raises(ValidationError):
            Telemetry.model_validate(p)

    def test_rejects_bad_quality_enum(self):
        p = {**VALID_TELEMETRY, "quality": "great"}
        with pytest.raises(ValidationError):
            Telemetry.model_validate(p)

    def test_metadata_rejects_extra_field(self):
        p = {
            **VALID_TELEMETRY,
            "metadata": {**VALID_TELEMETRY["metadata"], "extra": "x"},
        }
        with pytest.raises(ValidationError):
            Telemetry.model_validate(p)


# -------------------- Alarm --------------------

class TestAlarm:
    def test_valid_alarm(self):
        a = Alarm.model_validate(VALID_ALARM)
        assert a.severity is Severity.HIGH
        assert a.state is AlarmState.RAISED
        assert a.expected_range == (60.0, 200.0)

    @pytest.mark.parametrize(
        "bad_id",
        [
            "01HQX2T9R7K8YJWX5MVZP3D4QF",                # missing prefix
            "alm_01HQX2T9R7K8YJWX5MVZP3D4Q",             # 25-char ULID
            "alm_01HQX2T9R7K8YJWX5MVZP3D4QFG",           # 27-char
            "ALM_01HQX2T9R7K8YJWX5MVZP3D4QF",            # uppercase prefix
            "alm_01hqx2t9r7k8yjwx5mvzp3d4qf",            # lowercase ULID body
            "alm_01HQX2T9R7K8YJWX5MVZP3D4QI",            # contains forbidden char I
        ],
    )
    def test_rejects_bad_alarm_id(self, bad_id):
        p = {**VALID_ALARM, "alarm_id": bad_id}
        with pytest.raises(ValidationError):
            Alarm.model_validate(p)

    def test_rejects_bad_severity(self):
        p = {**VALID_ALARM, "severity": "spicy"}
        with pytest.raises(ValidationError):
            Alarm.model_validate(p)

    def test_rejects_bad_state(self):
        p = {**VALID_ALARM, "state": "pending"}
        with pytest.raises(ValidationError):
            Alarm.model_validate(p)

    def test_acknowledged_fields_optional(self):
        a = Alarm.model_validate(VALID_ALARM)
        assert a.acknowledged_at is None
        assert a.cleared_at is None


# -------------------- WS envelopes --------------------

class TestEnvelopes:
    def _ts(self) -> str:
        return "2026-05-03T16:42:13.500Z"

    def test_telemetry_envelope_roundtrip(self):
        env = TelemetryEnvelope.model_validate({
            "type": "telemetry",
            "timestamp": self._ts(),
            "payload": VALID_TELEMETRY,
        })
        assert env.type == "telemetry"
        assert env.payload.device_id == "cnc-07"

    def test_alarm_envelope_roundtrip(self):
        env = AlarmEnvelope.model_validate({
            "type": "alarm",
            "timestamp": self._ts(),
            "payload": VALID_ALARM,
        })
        assert env.payload.alarm_id == VALID_ALARM["alarm_id"]

    def test_machine_status_envelope(self):
        env = MachineStatusEnvelope.model_validate({
            "type": "machine_status",
            "timestamp": self._ts(),
            "payload": {"device_id": "cnc-07", "status": "alarming", "reason": "z+iso"},
        })
        assert env.payload.status == "alarming"

    def test_system_status_envelope(self):
        env = SystemStatusEnvelope.model_validate({
            "type": "system_status",
            "timestamp": self._ts(),
            "payload": {"broker": "up", "db": "up", "ingest": "up"},
        })
        assert env.payload.broker == "up"
