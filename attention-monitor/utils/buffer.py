import time


class TimeBuffer:
    def __init__(self):
        self.start_time = time.time()
        self.blinks = 0

    def update_blinks(self, blink_count):
        self.blinks = blink_count

    def get_blink_rate(self):
        elapsed = time.time() - self.start_time
        if elapsed == 0:
            return 0
        return (self.blinks / elapsed) * 60  # blinks per minute
