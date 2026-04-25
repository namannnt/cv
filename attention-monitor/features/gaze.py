import time
import math
import numpy as np
import cv2


# ── Task 1.1: HeadPoseEstimator ──────────────────────────────────────────────
class HeadPoseEstimator:
    """
    Lightweight head yaw estimation using 6 facial landmarks + cv2.solvePnP.
    Landmark indices used:
      1   = nose tip
      152 = chin
      33  = left eye outer corner
      263 = right eye outer corner
      61  = left mouth corner
      291 = right mouth corner

    Returns yaw in degrees. Returns 0.0 on any failure so callers
    can use the raw iris ratio unchanged.
    """

    # Approximate 3D model points (generic face, units = mm)
    MODEL_POINTS = np.array([
        [0.0,    0.0,    0.0],    # nose tip
        [0.0,   -63.6, -12.5],   # chin
        [-43.3,  32.7, -26.0],   # left eye outer corner
        [43.3,   32.7, -26.0],   # right eye outer corner
        [-28.9, -28.9, -24.1],   # left mouth corner
        [28.9,  -28.9, -24.1],   # right mouth corner
    ], dtype=np.float64)

    # Landmark indices matching MODEL_POINTS order
    LANDMARK_INDICES = [1, 152, 33, 263, 61, 291]

    def estimate_yaw(self, landmarks: list, frame_shape: tuple) -> float:
        """
        landmarks: flat list of (x, y) pixel tuples (478 points from FaceMesh)
        frame_shape: (height, width, channels)
        Returns yaw angle in degrees, or 0.0 on failure.
        """
        try:
            h, w = frame_shape[:2]
            focal = w  # approximate focal length
            cam_matrix = np.array([
                [focal, 0,     w / 2],
                [0,     focal, h / 2],
                [0,     0,     1    ]
            ], dtype=np.float64)
            dist_coeffs = np.zeros((4, 1), dtype=np.float64)

            image_points = np.array(
                [landmarks[i] for i in self.LANDMARK_INDICES],
                dtype=np.float64
            )

            success, rvec, _ = cv2.solvePnP(
                self.MODEL_POINTS, image_points,
                cam_matrix, dist_coeffs,
                flags=cv2.SOLVEPNP_ITERATIVE
            )
            if not success:
                return 0.0

            rmat, _ = cv2.Rodrigues(rvec)
            # Extract yaw from rotation matrix
            yaw = math.degrees(math.atan2(rmat[1][0], rmat[0][0]))
            return yaw

        except Exception:
            return 0.0


# ── Task 2.1: GazeCalibrator ─────────────────────────────────────────────────
class GazeCalibrator:
    """
    Per-user gaze calibration.
    Collects adjusted_ratio values during the first ~7 seconds of a session
    while the user looks straight at the screen.
    Once ≥ MIN_SAMPLES collected, derives personalized thresholds:
      left_thresh  = center_mean - 0.1
      right_thresh = center_mean + 0.1
    Falls back to defaults (0.42, 0.58) until calibration is complete.
    """
    CALIBRATION_SECONDS = 7
    MIN_SAMPLES = 30
    DEFAULT_LEFT  = 0.42
    DEFAULT_RIGHT = 0.58

    def __init__(self):
        self.center_buffer: list[float] = []
        self.calibrated = False
        self.left_thresh  = self.DEFAULT_LEFT
        self.right_thresh = self.DEFAULT_RIGHT
        self._start = time.time()

    def update(self, adjusted_ratio: float) -> None:
        """Call every frame during the calibration window."""
        if self.calibrated:
            return
        elapsed = time.time() - self._start
        if elapsed <= self.CALIBRATION_SECONDS:
            self.center_buffer.append(adjusted_ratio)
        elif len(self.center_buffer) >= self.MIN_SAMPLES:
            center_mean = sum(self.center_buffer) / len(self.center_buffer)
            self.left_thresh  = center_mean - 0.1
            self.right_thresh = center_mean + 0.1
            # safety: ensure left < right
            if self.left_thresh >= self.right_thresh:
                self.left_thresh  = self.DEFAULT_LEFT
                self.right_thresh = self.DEFAULT_RIGHT
            self.calibrated = True

    def get_thresholds(self) -> tuple[float, float]:
        """Returns (left_thresh, right_thresh). Uses defaults until calibrated."""
        return self.left_thresh, self.right_thresh


# ── GazeDetector (extended with HeadPoseEstimator + GazeCalibrator) ──────────
class GazeDetector:
    def __init__(self):
        self.off_screen_start = None
        self.off_screen_time  = 0
        self.last_gaze        = "CENTER"
        self.gaze_history     = []
        self.history_size     = 5

        # Task 1.1 + 2.1: new sub-components
        self.head_pose  = HeadPoseEstimator()
        self.calibrator = GazeCalibrator()

    # Task 1.3: extended to apply head-pose compensation + calibrated thresholds
    def get_gaze_direction(self, eye_points, iris_point,
                           landmarks=None, frame_shape=None):
        """
        landmarks and frame_shape are optional.
        If provided, head-pose yaw compensation is applied.
        """
        left  = eye_points[0][0]
        right = eye_points[3][0]
        eye_width = right - left

        if eye_width == 0:
            return self.last_gaze

        iris_x    = iris_point[0]
        raw_ratio = (iris_x - left) / eye_width

        # Task 1.3: head-pose compensation
        yaw = 0.0
        if landmarks is not None and frame_shape is not None:
            yaw = self.head_pose.estimate_yaw(landmarks, frame_shape)
        adjusted_ratio = raw_ratio - (yaw * 0.01)

        # Task 2.3: update calibrator + fetch thresholds
        self.calibrator.update(adjusted_ratio)
        left_thresh, right_thresh = self.calibrator.get_thresholds()

        if adjusted_ratio < left_thresh:
            return "LEFT"
        elif adjusted_ratio > right_thresh:
            return "RIGHT"
        else:
            return "CENTER"

    def smooth_gaze(self, gaze):
        self.gaze_history.append(gaze)
        if len(self.gaze_history) > self.history_size:
            self.gaze_history.pop(0)
        return max(set(self.gaze_history), key=self.gaze_history.count)

    def update_off_screen(self, gaze, face_detected):
        if not face_detected:
            gaze = self.last_gaze

        smoothed       = self.smooth_gaze(gaze)
        self.last_gaze = smoothed

        if smoothed != "CENTER":
            if self.off_screen_start is None:
                self.off_screen_start = time.time()
            self.off_screen_time = time.time() - self.off_screen_start
        else:
            self.off_screen_start = None
            self.off_screen_time  = 0

        return smoothed, self.off_screen_time
