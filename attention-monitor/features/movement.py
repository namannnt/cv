"""
MovementDetector — tracks head movement via nose-tip displacement between frames.
Task 7.1: Requirements 7.1, 7.2, 7.3, 7.5, 7.6
"""
import math


DISPLACEMENT_THRESHOLD = 15   # pixels
MAX_PENALTY            = 10.0


class MovementDetector:
    """Detects excessive head movement using nose-tip (landmark index 1) displacement."""

    def __init__(self):
        self._prev_pos: tuple[float, float] | None = None

    def update(self, nose_pos: tuple[float, float]) -> float:
        """
        Call each frame with the (x, y) pixel position of nose-tip landmark.
        Returns a penalty in [0, MAX_PENALTY] when displacement > threshold,
        or 0.0 on the first call.
        """
        if self._prev_pos is None:
            self._prev_pos = nose_pos
            return 0.0

        dx = nose_pos[0] - self._prev_pos[0]
        dy = nose_pos[1] - self._prev_pos[1]
        displacement = math.sqrt(dx * dx + dy * dy)
        self._prev_pos = nose_pos

        if displacement > DISPLACEMENT_THRESHOLD:
            return min(MAX_PENALTY, displacement * 0.2)
        return 0.0

    def reset(self) -> None:
        """Call when face is lost so the next detection starts fresh."""
        self._prev_pos = None
