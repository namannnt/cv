"""
Intervention system — triggers alerts based on sustained behavioral patterns.

Design rationale:
- Alerts fire only after a sustained condition, not on single-frame events.
  This prevents alert fatigue from transient noise.
- Each alert type has a cooldown to avoid repeated triggering.
- Thresholds are justified below.
"""
import time


class InterventionSystem:
    def __init__(self):
        self._last_alert_time: dict[str, float] = {}
        self._condition_start: dict[str, float] = {}

    def _sustained(self, key: str, condition: bool, required_seconds: float) -> bool:
        """Returns True if condition has been True for required_seconds continuously."""
        now = time.time()
        if condition:
            if key not in self._condition_start:
                self._condition_start[key] = now
            return (now - self._condition_start[key]) >= required_seconds
        else:
            self._condition_start.pop(key, None)
            return False

    def _cooldown_ok(self, key: str, cooldown_seconds: float) -> bool:
        now = time.time()
        last = self._last_alert_time.get(key, 0)
        return (now - last) >= cooldown_seconds

    def check(self, score: float, state: str, fatigue_score: float,
              off_time: float, session_min: float) -> list[str]:
        """
        Returns list of intervention messages to display.
        Empty list = no intervention needed.

        Threshold justifications:
        - DISTRACTED for 5s: gaze off-screen for 5s is clearly intentional,
          not a head adjustment. 3s would be too sensitive.
        - Fatigue >= 70 for 10s: fatigue score 60 triggers FATIGUED state,
          but 70 sustained for 10s indicates persistent fatigue, not a spike.
        - Score < 40 for 8s: score below 40 = DISTRACTED state. 8s sustained
          means it's not a transient blink/gaze event.
        - Session 25min: Pomodoro principle — 25min is the standard focus block.
        - Session 45min: hard break recommendation.
        """
        alerts = []
        now = time.time()

        # 1. Refocus alert — distracted for 5+ seconds
        if self._sustained("distracted", state == "DISTRACTED", 5.0):
            if self._cooldown_ok("distracted", 30.0):
                alerts.append("REFOCUS: Please look at the screen")
                self._last_alert_time["distracted"] = now

        # 2. Fatigue alert — fatigue >= 70 for 10+ seconds
        if self._sustained("fatigue_high", fatigue_score >= 70, 10.0):
            if self._cooldown_ok("fatigue_high", 60.0):
                alerts.append("FATIGUE: Blink slowly and rest your eyes for 20 seconds")
                self._last_alert_time["fatigue_high"] = now

        # 3. Low attention alert — score < 40 for 8+ seconds
        if self._sustained("low_score", score < 40, 8.0):
            if self._cooldown_ok("low_score", 45.0):
                alerts.append("LOW ATTENTION: Try to re-engage with the material")
                self._last_alert_time["low_score"] = now

        # 4. Pomodoro break — 25 min session
        if self._sustained("pomodoro", session_min >= 25, 0):
            if self._cooldown_ok("pomodoro", 1500.0):  # 25min cooldown
                alerts.append("BREAK TIME: You've been studying for 25 minutes. Take a 5-min break.")
                self._last_alert_time["pomodoro"] = now

        # 5. Hard break — 45 min session
        if self._sustained("hard_break", session_min >= 45, 0):
            if self._cooldown_ok("hard_break", 3600.0):
                alerts.append("MANDATORY BREAK: 45 minutes of study. Rest for at least 10 minutes.")
                self._last_alert_time["hard_break"] = now

        return alerts
