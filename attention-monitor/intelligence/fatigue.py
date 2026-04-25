import time


class FatigueDetector:
    def __init__(self):
        self.session_start      = time.time()
        self.eye_close_start    = None
        self.eye_close_duration = 0.0
        self.gaze_history       = []
        self.last_gaze          = "CENTER"
        self.blink_timestamps   = []  # track blink timing pattern

    # --- signal 1: eye closure duration ---
    def update_eye_closure(self, eye_closed):
        if eye_closed:
            if self.eye_close_start is None:
                self.eye_close_start = time.time()
            self.eye_close_duration = time.time() - self.eye_close_start
        else:
            self.eye_close_start    = None
            self.eye_close_duration = 0.0
        return self.eye_close_duration

    # --- signal 2: gaze instability (rolling 60 frames) ---
    def update_gaze_instability(self, gaze):
        self.gaze_history.append(gaze)
        if len(self.gaze_history) > 60:
            self.gaze_history.pop(0)

        transitions = sum(
            1 for i in range(1, len(self.gaze_history))
            if self.gaze_history[i] != self.gaze_history[i - 1]
        )
        self.last_gaze = gaze
        return transitions

    # --- signal 3: session time ---
    def get_session_minutes(self):
        return (time.time() - self.session_start) / 60.0

    # --- final fatigue score (0-100) ---
    def get_fatigue_score(self, eye_closed, blink_rate, gaze):
        score = 0

        # signal 1: eye closure duration
        # > 0.3s = mild, > 1s = strong fatigue
        closure_dur = self.update_eye_closure(eye_closed)
        if closure_dur > 1.0:
            score += 40
        elif closure_dur > 0.3:
            score += 20

        # signal 2: blink rate
        # > 25/min = high fatigue, > 15 = mild
        if blink_rate > 25:
            score += 30
        elif blink_rate > 15:
            score += 15

        # signal 3: gaze instability
        # > 15 transitions = unstable, > 8 = mild
        instability = self.update_gaze_instability(gaze)
        if instability > 15:
            score += 20
        elif instability > 8:
            score += 10

        # signal 4: session time
        session_min = self.get_session_minutes()
        if session_min > 30:
            score += 20
        elif session_min > 15:
            score += 10
        elif session_min > 5:
            score += 5

        return min(100, score), closure_dur, instability, session_min
