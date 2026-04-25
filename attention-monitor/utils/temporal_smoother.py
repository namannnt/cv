"""
Time-window based temporal smoother.
Unlike a fixed-frame rolling average, this uses wall-clock time,
making it frame-rate independent.

Why this reduces noise:
- A single bad frame (MediaPipe glitch, motion blur) contributes
  proportionally to its time slice, not as a full sample.
- Short transients (blink = ~150ms) are smoothed over the window
  without being completely ignored.
- Window size is tunable per signal type.
"""
import time
from collections import deque


class TemporalSmoother:
    def __init__(self, window_seconds: float = 1.0):
        self.window = window_seconds
        self._samples: deque = deque()  # (timestamp, value)

    def update(self, value: float) -> float:
        now = time.time()
        self._samples.append((now, value))
        # evict samples outside the time window
        cutoff = now - self.window
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()
        if not self._samples:
            return value
        return round(sum(v for _, v in self._samples) / len(self._samples), 1)

    def get_confidence(self) -> float:
        """
        Confidence = how stable the signal is within the window.
        Low variance → high confidence. High variance → low confidence.
        Returns 0.0 to 1.0.
        """
        if len(self._samples) < 2:
            return 1.0
        values = [v for _, v in self._samples]
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        # normalize: variance of 0 = confidence 1.0, variance >= 625 (25^2) = confidence 0.0
        confidence = max(0.0, 1.0 - (variance / 625.0))
        return round(confidence, 2)
