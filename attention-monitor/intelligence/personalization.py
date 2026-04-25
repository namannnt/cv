import time


class Personalization:
    def __init__(self):
        self.start_time     = time.time()
        self.baseline_blink = []
        self.baseline_gaze  = []
        self.learning       = True

        # Task 4.1: gaze stability baseline
        self.gaze_transitions: int          = 0
        self._prev_gaze: str                = "CENTER"
        self.baseline_gaze_transitions: int = 0
        self.gaze_transition_threshold      = None  # set at baseline end

        # Task 4.1: fatigue + off-screen baselines
        self.baseline_fatigue_samples: list[float]  = []
        self.baseline_off_time_samples: list[float] = []

    # Task 4.2: extended update — records gaze transitions, fatigue, off_time
    def update(self, blink_rate: float, gaze: str,
               fatigue_score: float = 0.0, off_time: float = 0.0) -> None:
        in_baseline = time.time() - self.start_time < 120

        if in_baseline:
            self.baseline_blink.append(blink_rate)
            self.baseline_gaze.append(gaze)
            self.baseline_fatigue_samples.append(fatigue_score)
            self.baseline_off_time_samples.append(off_time)

            # count gaze direction transitions
            if gaze != self._prev_gaze:
                self.gaze_transitions += 1
            self._prev_gaze = gaze

        else:
            if self.learning:
                # baseline just ended — freeze transition count
                self.baseline_gaze_transitions  = self.gaze_transitions
                self.gaze_transition_threshold  = self.baseline_gaze_transitions * 1.5
                self.learning = False

    def get_baseline_blink(self) -> float:
        if self.baseline_blink:
            return sum(self.baseline_blink) / len(self.baseline_blink)
        return 15.0

    def get_gaze_stability(self) -> float:
        if not self.baseline_gaze:
            return 0.8
        return self.baseline_gaze.count("CENTER") / len(self.baseline_gaze)

    # Task 4.4: gaze instability penalty
    def get_gaze_instability_penalty(self, current_transitions: int) -> float:
        """Returns > 0 if current_transitions > gaze_transition_threshold, else 0."""
        if self.gaze_transition_threshold is None:
            return 0.0  # baseline not complete yet
        if current_transitions > self.gaze_transition_threshold:
            return min(10.0, (current_transitions - self.gaze_transition_threshold) * 0.5)
        return 0.0

    # Task 4.4: personalized fatigue threshold
    def get_fatigue_threshold(self) -> float:
        """Returns mean(baseline_fatigue_samples) + 15, or 60 if baseline incomplete."""
        if not self.learning and self.baseline_fatigue_samples:
            mean = sum(self.baseline_fatigue_samples) / len(self.baseline_fatigue_samples)
            return max(40.0, min(80.0, mean + 15))
        return 60.0

    # Task 4.4: personalized off-screen threshold
    def get_off_threshold(self) -> float:
        """Returns mean(baseline_off_time_samples) + 2, or 3.0 if baseline incomplete."""
        if not self.learning and self.baseline_off_time_samples:
            mean = sum(self.baseline_off_time_samples) / len(self.baseline_off_time_samples)
            return max(1.5, min(8.0, mean + 2))
        return 3.0
