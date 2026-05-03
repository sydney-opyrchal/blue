"""
Rolling z-score anomaly detector — SPEC §7.5 layer 1.

One instance per (device_id, tag). Window is in seconds, evicted by timestamp
rather than count so the detector behaves correctly across rate changes.
NaN values are skipped; an empty or single-sample window never alarms.
"""
from __future__ import annotations

import math
from collections import deque
from datetime import datetime, timedelta


class ZScoreDetector:
    def __init__(self, window_seconds: float = 60.0, threshold: float = 3.0):
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        if threshold <= 0:
            raise ValueError("threshold must be positive")
        self.window = timedelta(seconds=window_seconds)
        self.threshold = threshold
        self._buf: deque[tuple[datetime, float]] = deque()

    def update(self, value: float, timestamp: datetime) -> bool:
        """Record a reading; return True iff it is anomalous under the current window."""
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return False

        self._evict(timestamp)

        # Compute on the *prior* window so a single anomaly doesn't pull its own mean.
        anomalous = self._is_anomalous(value)

        self._buf.append((timestamp, float(value)))
        return anomalous

    def _evict(self, now: datetime) -> None:
        cutoff = now - self.window
        while self._buf and self._buf[0][0] < cutoff:
            self._buf.popleft()

    def _is_anomalous(self, value: float) -> bool:
        n = len(self._buf)
        if n < 2:
            return False
        mean = sum(v for _, v in self._buf) / n
        var = sum((v - mean) ** 2 for _, v in self._buf) / n
        std = math.sqrt(var)
        if std == 0:
            return False
        return abs(value - mean) / std > self.threshold

    def __len__(self) -> int:
        return len(self._buf)
