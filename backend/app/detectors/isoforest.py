"""
Isolation Forest anomaly detector — SPEC §7.5 layer 2.

Wraps scikit-learn's IsolationForest. Trained per (device_id, tag) on synthetic
baseline samples drawn from the normal range in simulator.yaml. The "both must
agree" gate in the ingest service is what actually raises an alarm; this layer
on its own returns a per-reading bool.
"""
from __future__ import annotations

import numpy as np
from sklearn.ensemble import IsolationForest


class IsoForestDetector:
    def __init__(
        self,
        contamination: float = 0.01,
        n_estimators: int = 100,
        random_state: int = 42,
    ):
        if not 0 < contamination < 0.5:
            raise ValueError("contamination must be in (0, 0.5)")
        self._model = IsolationForest(
            contamination=contamination,
            n_estimators=n_estimators,
            random_state=random_state,
        )
        self._fitted = False

    def fit(self, samples: list[float] | np.ndarray) -> None:
        arr = np.asarray(samples, dtype=float).reshape(-1, 1)
        if arr.shape[0] < 2:
            raise ValueError("need at least 2 samples to fit")
        self._model.fit(arr)
        self._fitted = True

    def predict(self, value: float) -> bool:
        if not self._fitted:
            raise RuntimeError("predict() called before fit()")
        result = self._model.predict(np.array([[float(value)]]))
        return bool(result[0] == -1)

    @property
    def fitted(self) -> bool:
        return self._fitted
