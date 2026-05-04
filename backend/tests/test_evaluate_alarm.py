"""Tests for the redline alarm path in main.py — verifies wiring of the
Alarm lifecycle module into evaluate_alarm and acknowledgment."""
from __future__ import annotations

import importlib

import pytest

from app.alarms import Alarm
from app.contracts import AlarmState


@pytest.fixture
def main_module(monkeypatch):
    from app import main as m
    importlib.reload(m)
    # Stub broadcast to a no-op; we are testing alarm state, not WS plumbing.
    monkeypatch.setattr(m, "broadcast", lambda msg: None)
    # Don't try to persist; DB pool will be None in this fixture.
    monkeypatch.setattr(m, "_persist_alarm", lambda *a, **kw: None)
    m.active_alarms.clear()
    return m


def test_breach_creates_alarm(main_module):
    m = main_module
    asset_id = next(iter(m.asset_lookup))
    asset = m.asset_lookup[asset_id]
    metric, cfg = next(iter(asset["metrics"].items()))
    over = cfg["redline_high"] * 1.5

    m.evaluate_alarm(asset_id, metric, over)
    key = f"{asset_id}::{metric}"
    assert key in m.active_alarms
    alarm = m.active_alarms[key]
    assert isinstance(alarm, Alarm)
    assert alarm.alarm_id.startswith("alm_")
    assert alarm.state is AlarmState.RAISED


def test_return_to_normal_clears_alarm(main_module):
    m = main_module
    asset_id = next(iter(m.asset_lookup))
    asset = m.asset_lookup[asset_id]
    metric, cfg = next(iter(asset["metrics"].items()))
    over = cfg["redline_high"] * 1.5
    nominal = cfg["nominal"]

    m.evaluate_alarm(asset_id, metric, over)
    m.evaluate_alarm(asset_id, metric, nominal)
    key = f"{asset_id}::{metric}"
    assert key not in m.active_alarms
