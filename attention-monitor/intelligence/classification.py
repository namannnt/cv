class StateClassifier:
    def classify(self, attention_score: float, off_screen_time: float,
                 fatigue_score: float,
                 fatigue_threshold: float = 60.0,
                 off_threshold: float = 3.0) -> str:
        """
        fatigue_threshold: adjusted by CalibrationManager + Personalization.
          Default 60. Positive offset → harder to trigger FATIGUED.
        off_threshold: adjusted by Personalization.get_off_threshold().
          Default 3.0s. Personalized to user's natural gaze patterns.
        """
        if fatigue_score >= fatigue_threshold:
            return "FATIGUED"

        if off_screen_time > off_threshold:
            return "DISTRACTED"

        if attention_score > 70:
            return "FOCUSED"
        elif attention_score > 40:
            return "LOW FOCUS"
        else:
            return "DISTRACTED"
