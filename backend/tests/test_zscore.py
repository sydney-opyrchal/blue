"""Tests for the rolling z-score detector — SPEC §7.5 layer 1, §11.1."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from app.detectors.zscore import ZScoreDetector


def t(seconds: float) -> datetime:
    """Build a deterministic timestamp at offset `seconds` from a fixed epoch."""
    base = datetime(2026, 5, 3, 12, 0, 0, tzinfo=timezone.utc)
    return base + timedelta(seconds=seconds)


class TestConstruction:
    def test_rejects_nonpositive_window(self):
        with pytest.raises(ValueError):
            ZScoreDetector(window_seconds=0)

    def test_rejects_nonpositive_threshold(self):
        with pytest.raises(ValueError):
            ZScoreDetector(threshold=-1)


class TestEmptyAndSparse:
    def test_first_sample_never_alarms(self):
        d = ZScoreDetector()
        assert d.update(100.0, t(0)) is False

    def test_second_sample_never_alarms(self):
        d = ZScoreDetector()
        d.update(100.0, t(0))
        # Even an extreme value can't be flagged with n<2 in the prior window.
        assert d.update(10_000.0, t(1)) is False


class TestSteadyStateDetection:
    def _seed_steady(self, d: ZScoreDetector, value: float, n: int) -> None:
        for i in range(n):
            d.update(value, t(i))

    def test_value_within_band_is_normal(self):
        d = ZScoreDetector(window_seconds=60, threshold=3.0)
        # All samples identical -> std=0 -> never alarm.
        self._seed_steady(d, 100.0, 30)
        assert d.update(100.5, t(31)) is False

    def test_zero_variance_window_does_not_alarm(self):
        d = ZScoreDetector(window_seconds=60, threshold=3.0)
        self._seed_steady(d, 100.0, 30)
        # Even an extreme value can't divide by zero std; detector returns False.
        assert d.update(1e9, t(31)) is False

    def test_clearly_anomalous_value_alarms(self):
        d = ZScoreDetector(window_seconds=60, threshold=3.0)
        # Build a window with non-zero variance.
        for i, v in enumerate([100, 101, 99, 100, 102, 98, 101, 100, 99, 101]):
            d.update(v, t(i))
        assert d.update(500.0, t(11)) is True

    def test_value_just_below_threshold_does_not_alarm(self):
        d = ZScoreDetector(window_seconds=60, threshold=3.0)
        for i, v in enumerate([100, 102, 98, 101, 99, 100, 101, 99, 100, 102]):
            d.update(v, t(i))
        # mean ≈ 100.2, std small but >0; pick a value barely under 3σ.
        # Using prior window stats, 102.5 is comfortably normal.
        assert d.update(102.5, t(11)) is False


class TestWindowEviction:
    def test_old_samples_are_evicted(self):
        d = ZScoreDetector(window_seconds=10, threshold=3.0)
        d.update(100.0, t(0))
        d.update(101.0, t(1))
        d.update(99.0, t(2))
        # Jump 1000s into the future — old samples must evict.
        d.update(50.0, t(1000))
        assert len(d) == 1

    def test_eviction_resets_stats(self):
        d = ZScoreDetector(window_seconds=5, threshold=3.0)
        # Build a tight cluster around 100.
        for i in range(5):
            d.update(100.0 + (i % 2) * 0.5, t(i))
        # After a long gap, the new value should NOT alarm because the window
        # is empty when evaluated.
        assert d.update(10_000.0, t(1000)) is False


class TestNaNAndNone:
    def test_nan_value_is_skipped(self):
        d = ZScoreDetector()
        assert d.update(float("nan"), t(0)) is False
        assert len(d) == 0

    def test_none_value_is_skipped(self):
        d = ZScoreDetector()
        assert d.update(None, t(0)) is False  # type: ignore[arg-type]
        assert len(d) == 0


class TestPriorWindowSemantics:
    def test_anomaly_does_not_pull_its_own_mean(self):
        """Regression: detector should evaluate a reading against the *prior*
        window, not a window that already contains the reading. Otherwise a
        large outlier dilutes its own anomaly score."""
        d = ZScoreDetector(window_seconds=60, threshold=3.0)
        for i, v in enumerate([100, 101, 99, 100, 102, 98, 101, 100, 99, 101]):
            d.update(v, t(i))
        anomalous = d.update(1000.0, t(11))
        # Should still alarm — the 1000 is evaluated against the steady prior.
        assert anomalous is True
