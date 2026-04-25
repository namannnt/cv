class ContextManager:
    MODES = ["READING", "PROBLEM_SOLVING", "LECTURE"]

    def __init__(self):
        self.mode = "READING"

    def set_mode(self, mode):
        if mode in self.MODES:
            self.mode = mode

    def get_weights(self):
        # returns (gaze_weight, blink_weight)
        if self.mode == "READING":
            return 0.5, 0.2
        elif self.mode == "PROBLEM_SOLVING":
            return 0.3, 0.2
        elif self.mode == "LECTURE":
            return 0.6, 0.2
        return 0.4, 0.3
