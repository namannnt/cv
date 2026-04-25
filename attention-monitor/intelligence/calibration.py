"""
CalibrationManager — Human-in-the-Loop threshold adaptation.

Fixes applied (v2):
  1. Feedback noise resistance — uses last 3 sessions to compute
     consistent signal before applying full adjustment. Inconsistent
     feedback gets half-weight.
  2. Over-adaptation decay — offsets drift back toward 0 by 10% per
     session when no mismatch is detected, preventing runaway tolerance.
  3. Fatigue threshold fix — offset applied to the THRESHOLD (60),
     not to the signal. Cleaner and safer.
  4. Audit trail — every calibration change is appended to
     calibration_history in calibration.json for debugging.
"""
import json
import os
import threading
from datetime import datetime

CALIBRATION_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'calibration.json')
FEEDBACK_FILE    = os.path.join(os.path.dirname(__file__), '..', 'data', 'user_feedback.json')

_calibration_lock = threading.Lock()
_feedback_lock    = threading.Lock()

# Safe clamp ranges
BLINK_OFFSET_MIN,   BLINK_OFFSET_MAX   = -8,   8
GAZE_SCALE_MIN,     GAZE_SCALE_MAX     = 0.5,  1.5
FATIGUE_OFFSET_MIN, FATIGUE_OFFSET_MAX = -15,  15

DEFAULTS = {
    "blink_offset":   0,
    "gaze_scale":     1.0,
    "fatigue_offset": 0,     # added to fatigue THRESHOLD (60), not signal
    "sessions_used":  0,
    "calibration_history": []
}

# How many recent sessions to consider for consistency check
CONSISTENCY_WINDOW = 3


class CalibrationManager:
    def __init__(self):
        self.params = self._load()

    def _load(self) -> dict:
        if os.path.exists(CALIBRATION_FILE):
            try:
                with open(CALIBRATION_FILE, "r") as f:
                    data = json.load(f)
                for k, v in DEFAULTS.items():
                    data.setdefault(k, v)
                return data
            except (json.JSONDecodeError, IOError):
                pass
        return dict(DEFAULTS)

    def _save(self):
        os.makedirs(os.path.dirname(CALIBRATION_FILE), exist_ok=True)
        with _calibration_lock:
            with open(CALIBRATION_FILE, "w") as f:
                json.dump(self.params, f, indent=4)

    # ── public properties ──

    @property
    def blink_offset(self) -> float:
        return self.params["blink_offset"]

    @property
    def gaze_scale(self) -> float:
        return self.params["gaze_scale"]

    @property
    def fatigue_threshold(self) -> float:
        """
        Fix 3: return the adjusted fatigue THRESHOLD.
        Classifier uses: if fatigue_score >= calibration.fatigue_threshold
        Default threshold is 60. Positive offset raises it (harder to trigger),
        negative offset lowers it (easier to trigger).
        """
        return _clamp(60 + self.params["fatigue_offset"],
                      60 + FATIGUE_OFFSET_MIN,
                      60 + FATIGUE_OFFSET_MAX)

    def summary(self) -> str:
        parts = []
        if self.params["blink_offset"] != 0:
            sign = "+" if self.params["blink_offset"] > 0 else ""
            parts.append(f"blink {sign}{self.params['blink_offset']:.0f}")
        if abs(self.params["gaze_scale"] - 1.0) > 0.01:
            pct = (self.params["gaze_scale"] - 1.0) * 100
            sign = "+" if pct > 0 else ""
            parts.append(f"gaze {sign}{pct:.0f}%")
        if self.params["fatigue_offset"] != 0:
            sign = "+" if self.params["fatigue_offset"] > 0 else ""
            parts.append(f"fatigue threshold {sign}{self.params['fatigue_offset']:.0f}")
        if not parts:
            return "Default (no calibration yet)"
        return "Calibrated: " + ", ".join(parts)

    # ── Fix 1: consistency check ──

    def _get_recent_feedback(self) -> list:
        """Load last CONSISTENCY_WINDOW feedback entries."""
        if not os.path.exists(FEEDBACK_FILE):
            return []
        try:
            with open(FEEDBACK_FILE, "r") as f:
                data = json.load(f)
            return data.get("sessions", [])[-CONSISTENCY_WINDOW:]
        except (json.JSONDecodeError, IOError):
            return []

    def _is_consistent(self, key: str, value: bool, recent: list) -> bool:
        """
        Returns True if the last N sessions all agree on this feedback key.
        If consistent → apply full adjustment.
        If inconsistent → apply half adjustment.
        """
        if len(recent) < 2:
            return True  # not enough history, treat as consistent
        return all(s.get(key) == value for s in recent)

    def _boundary_damping(self, param: str, step: float) -> float:
        """
        Reduce step size when value approaches limits (>75% of max range).
        Slows adaptation near extremes without hard-stopping it.
        """
        val = self.params[param]
        if param == "blink_offset":
            ratio = abs(val) / BLINK_OFFSET_MAX
        elif param == "gaze_scale":
            ratio = abs(val - 1.0) / (GAZE_SCALE_MAX - 1.0)
        elif param == "fatigue_offset":
            ratio = abs(val) / FATIGUE_OFFSET_MAX
        else:
            ratio = 0.0
        return step * 0.5 if ratio > 0.75 else step

    def _apply_decay(self):
        """
        Pull offsets 10% toward zero when no mismatch is detected.
        Prevents runaway tolerance from one-sided feedback.
        """
        self.params["blink_offset"]   = round(self.params["blink_offset"]   * 0.9, 2)
        self.params["gaze_scale"]     = round(1.0 + (self.params["gaze_scale"] - 1.0) * 0.9, 4)
        self.params["fatigue_offset"] = round(self.params["fatigue_offset"] * 0.9, 2)

    # ── main update ──

    def update_from_feedback(self, avg_score: float, avg_fatigue: float,
                              user_attention: bool, user_fatigue: bool):
        changed        = False
        attention_mismatch = False
        fatigue_mismatch   = False

        recent = self._get_recent_feedback()

        # ── attention mismatch ──
        if user_attention and avg_score < 60:
            consistent = self._is_consistent("user_attention", True, recent)
            step = 2.0 if consistent else 1.0
            step = self._boundary_damping("blink_offset", step)
            self.params["blink_offset"] = _clamp(
                self.params["blink_offset"] + step, BLINK_OFFSET_MIN, BLINK_OFFSET_MAX)
            gaze_step = (0.05 if consistent else 0.025)
            gaze_step = self._boundary_damping("gaze_scale", gaze_step)
            self.params["gaze_scale"]   = _clamp(
                self.params["gaze_scale"] - gaze_step, GAZE_SCALE_MIN, GAZE_SCALE_MAX)
            attention_mismatch = True
            changed = True

        elif not user_attention and avg_score > 75:
            consistent = self._is_consistent("user_attention", False, recent)
            step = 2.0 if consistent else 1.0
            step = self._boundary_damping("blink_offset", step)
            self.params["blink_offset"] = _clamp(
                self.params["blink_offset"] - step, BLINK_OFFSET_MIN, BLINK_OFFSET_MAX)
            gaze_step = (0.05 if consistent else 0.025)
            gaze_step = self._boundary_damping("gaze_scale", gaze_step)
            self.params["gaze_scale"]   = _clamp(
                self.params["gaze_scale"] + gaze_step, GAZE_SCALE_MIN, GAZE_SCALE_MAX)
            attention_mismatch = True
            changed = True

        if user_fatigue and avg_fatigue < 40:
            consistent = self._is_consistent("user_fatigue", True, recent)
            step = 5 if consistent else 2
            step = self._boundary_damping("fatigue_offset", step)
            self.params["fatigue_offset"] = _clamp(
                self.params["fatigue_offset"] - step,
                FATIGUE_OFFSET_MIN, FATIGUE_OFFSET_MAX)
            fatigue_mismatch = True
            changed = True

        elif not user_fatigue and avg_fatigue > 60:
            consistent = self._is_consistent("user_fatigue", False, recent)
            step = 5 if consistent else 2
            step = self._boundary_damping("fatigue_offset", step)
            self.params["fatigue_offset"] = _clamp(
                self.params["fatigue_offset"] + step,
                FATIGUE_OFFSET_MIN, FATIGUE_OFFSET_MAX)
            fatigue_mismatch = True
            changed = True

        # Fix 2: decay when no mismatch detected
        if not attention_mismatch and not fatigue_mismatch:
            self._apply_decay()
            changed = True  # save the decay

        if changed:
            self.params["sessions_used"] += 1

            # Fix 4: audit trail
            self.params["calibration_history"].append({
                "ts":             datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "blink_offset":   round(self.params["blink_offset"], 2),
                "gaze_scale":     round(self.params["gaze_scale"], 4),
                "fatigue_offset": round(self.params["fatigue_offset"], 2),
                "trigger":        ("attention_mismatch" if attention_mismatch else "") +
                                  ("fatigue_mismatch"   if fatigue_mismatch   else "") +
                                  ("decay"              if not attention_mismatch
                                                           and not fatigue_mismatch else "")
            })
            # keep history to last 50 entries
            self.params["calibration_history"] = self.params["calibration_history"][-10:]
            self._save()

        return changed


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


# ── feedback storage ──

def store_feedback(session_id: str, avg_score: float, avg_fatigue: float,
                   user_attention: bool, user_fatigue: bool) -> bool:
    os.makedirs(os.path.dirname(FEEDBACK_FILE), exist_ok=True)

    with _feedback_lock:
        if os.path.exists(FEEDBACK_FILE):
            try:
                with open(FEEDBACK_FILE, "r") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, IOError):
                data = {"sessions": []}
        else:
            data = {"sessions": []}

        existing_ids = {s["session_id"] for s in data["sessions"]}
        if session_id in existing_ids:
            return False

        data["sessions"].append({
            "session_id":     session_id,
            "avg_score":      round(avg_score, 1),
            "avg_fatigue":    round(avg_fatigue, 1),
            "user_attention": user_attention,
            "user_fatigue":   user_fatigue
        })

        with open(FEEDBACK_FILE, "w") as f:
            json.dump(data, f, indent=4)

    return True
