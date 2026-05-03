"""Tests for the IsolationForest detector wrapper — SPEC §7.5 layer 2."""
from __future__ import annotations

import random

import pytest

from app.detectors.isoforest import IsoForestDetector


def baseline(mean: float = 100.0, sigma: float = 1.0, n: int = 500, seed: int = 0) -> list[float]:
    rng = random.Random(seed)
    return [rng.gauss(mean, sigma) for _ in range(n)]


class TestConstruction:
    def test_rejects_invalid_contamination(self):
        with pytest.raises(ValueError):
            IsoForestDetector(contamination=0)
        with pytest.raises(ValueError):
            IsoForestDetector(contamination=0.6)

    def test_unfitted_predict_raises(self):
        d = IsoForestDetector()
        with pytest.raises(RuntimeError):
            d.predict(100.0)

    def test_fitted_flag(self):
        d = IsoForestDetector()
        assert d.fitted is False
        d.fit(baseline())
        assert d.fitted is True


class TestFitting:
    def test_rejects_too_few_samples(self):
        d = IsoForestDetector()
        with pytest.raises(ValueError):
            d.fit([42.0])

    def test_predict_returns_bool(self):
        d = IsoForestDetector()
        d.fit(baseline())
        out = d.predict(100.0)
        assert isinstance(out, bool)


class TestDetection:
    def test_in_distribution_value_is_normal(self):
        d = IsoForestDetector(contamination=0.01, random_state=42)
        d.fit(baseline(mean=100.0, sigma=1.0, n=500))
        assert d.predict(100.0) is False

    def test_extreme_outlier_is_anomalous(self):
        d = IsoForestDetector(contamination=0.01, random_state=42)
        d.fit(baseline(mean=100.0, sigma=1.0, n=500))
        # 50σ away from the baseline — must trip.
        assert d.predict(5_000.0) is True

    def test_deterministic_with_fixed_seed(self):
        samples = baseline(seed=7)
        d1 = IsoForestDetector(random_state=42)
        d2 = IsoForestDetector(random_state=42)
        d1.fit(samples)
        d2.fit(samples)
        for v in [100.0, 105.0, 95.0, 1000.0, -1000.0]:
            assert d1.predict(v) == d2.predict(v)
