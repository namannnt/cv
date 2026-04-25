import csv
import os
import threading
from datetime import datetime

_log_lock = threading.Lock()


class SessionLogger:
    def __init__(self):
        self.file_name = f"data/logs/session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        os.makedirs("data/logs", exist_ok=True)

        with _log_lock:
            with open(self.file_name, mode='w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp", "attention_score", "state",
                    "blink_rate", "gaze", "off_screen_time", "fatigue_score"
                ])

    def log(self, score, state, blink_rate, gaze, off_time, fatigue_score):
        with _log_lock:
            with open(self.file_name, mode='a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    datetime.now().strftime("%H:%M:%S"),
                    round(score, 1), state,
                    round(blink_rate, 1), gaze,
                    round(off_time, 1), round(fatigue_score, 1)
                ])
