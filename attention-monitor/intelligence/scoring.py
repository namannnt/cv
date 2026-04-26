class AttentionScorer:
    def calculate(self, gaze, off_screen_time, eye_closed, blink_rate,
                  blink_threshold=20, gaze_w=0.5, blink_w=0.2,
                  movement_penalty=0.0):
        score = 100

        # gaze penalty — weighted by context mode
        if gaze != "CENTER":
            score -= min(40, off_screen_time * 10) * (gaze_w / 0.5)

        # eye closed penalty
        if eye_closed:
            score -= 30

        # blink rate penalty — threshold personalised per user
        if blink_rate > blink_threshold:
            score -= 20 * (blink_w / 0.2)

        # movement penalty — capped at 10 (task 7.3)
        score -= min(10, movement_penalty)

        return max(0, min(100, score))
