import numpy as np


class BlinkDetector:
    def __init__(self):
        self.blink_count = 0
        self.prev_eye_closed = False

    def calculate_ear(self, eye_points):
        # vertical distances
        v1 = np.linalg.norm(np.array(eye_points[1]) - np.array(eye_points[5]))
        v2 = np.linalg.norm(np.array(eye_points[2]) - np.array(eye_points[4]))

        # horizontal distance
        h = np.linalg.norm(np.array(eye_points[0]) - np.array(eye_points[3]))

        ear = (v1 + v2) / (2.0 * h)
        return ear

    def detect(self, left_eye, right_eye):
        left_ear = self.calculate_ear(left_eye)
        right_ear = self.calculate_ear(right_eye)

        ear = (left_ear + right_ear) / 2.0

        eye_closed = ear < 0.25

        # blink detection logic
        if eye_closed and not self.prev_eye_closed:
            self.blink_count += 1

        self.prev_eye_closed = eye_closed

        return ear, eye_closed, self.blink_count
