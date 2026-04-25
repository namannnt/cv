# NOTE: These constants are NOT used by the main pipeline.
# Dynamic values come from personalization.py and calibration.py.
# This file is kept as a reference only.

# Time window (seconds)
TIME_WINDOW = 15

# Attention thresholds
GAZE_OFF_THRESHOLD = 3
BLINK_THRESHOLD = 20
EAR_THRESHOLD = 0.25

# Weights (default - reading mode)
GAZE_WEIGHT = 0.5
BLINK_WEIGHT = 0.2
MOVEMENT_WEIGHT = 0.3
