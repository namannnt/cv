# Requirements Document

## Introduction

This feature delivers targeted robustness and personalization upgrades to an existing attention monitoring system. The scope is strictly additive: no system-wide refactoring, only minimal, stable extensions to four areas — gaze accuracy, personalization depth, removal of academic shortcuts, and teacher-system persistence. All new logic must fall back gracefully to existing defaults when calibration or baseline data is not yet available.

---

## Glossary

- **GazeDetector**: The class in `features/gaze.py` responsible for computing gaze direction from iris and eye landmarks.
- **HeadPoseEstimator**: The lightweight sub-component added to `GazeDetector` that estimates head yaw using `cv2.solvePnP`.
- **GazeCalibrator**: The per-user calibration sub-component added to `GazeDetector` that collects center-gaze samples during the first 5–10 seconds of a session.
- **Personalization**: The class in `intelligence/personalization.py` that tracks per-user baselines and adjusts scoring thresholds.
- **MovementDetector**: The class in `features/movement.py` that tracks nose landmark displacement between frames.
- **AttentionScorer**: The class in `intelligence/scoring.py` that computes the raw attention score.
- **TeacherServer**: The FastAPI application in `teacher-system/server.py` that aggregates and broadcasts student attention data.
- **SessionDB**: The SQLite-backed persistence layer added to `TeacherServer`.
- **WebApp**: The Flask application in `attention-web/app.py` that launches the attention monitor subprocess.
- **MainProcess**: The Python process defined in `attention-monitor/main.py` that runs the real-time attention monitoring loop.
- **Yaw**: Horizontal head rotation angle (left/right) in degrees, estimated from facial landmarks.
- **IrisRatio**: The normalized horizontal position of the iris within the eye bounding box, in the range [0, 1].
- **BaselinePhase**: The first 120 seconds of a session during which `Personalization` collects per-user baseline measurements.
- **CalibrationWindow**: The first 5–10 seconds of a session during which `GazeCalibrator` collects center-gaze iris ratios.

---

## Requirements

### Requirement 1: Head Pose Compensation for Gaze

**User Story:** As a user, I want the gaze detector to account for my head rotation, so that looking straight at the screen while my head is turned does not incorrectly register as a left or right gaze.

#### Acceptance Criteria

1. THE `GazeDetector` SHALL estimate head yaw using exactly 6 facial landmarks (nose tip, chin, left eye corner, right eye corner, left mouth corner, right mouth corner) and `cv2.solvePnP` with a fixed approximate 3D model.
2. WHEN head yaw is estimated, THE `HeadPoseEstimator` SHALL compute the adjusted iris ratio as `adjusted_ratio = raw_ratio - (yaw * 0.01)`.
3. THE `GazeDetector` SHALL use `adjusted_ratio` in place of `raw_ratio` for all gaze direction classifications.
4. IF `cv2.solvePnP` fails or returns an invalid result, THEN THE `GazeDetector` SHALL fall back to using the unadjusted `raw_ratio` for classification.
5. THE `HeadPoseEstimator` SHALL use no deep learning model and SHALL require no external model file beyond the existing face landmark task.

### Requirement 2: Per-User Gaze Calibration

**User Story:** As a user, I want the gaze thresholds to adapt to my natural eye position, so that my center gaze is correctly identified regardless of my eye anatomy or camera placement.

#### Acceptance Criteria

1. WHEN a session starts, THE `GazeCalibrator` SHALL collect `adjusted_ratio` values into a `center_buffer` during the first 5–10 seconds of the session.
2. WHEN `center_buffer` contains enough samples (at least 30), THE `GazeCalibrator` SHALL compute `center_mean` as the mean of all buffered values.
3. WHEN `center_mean` is available, THE `GazeDetector` SHALL set `left_thresh = center_mean - 0.1` and `right_thresh = center_mean + 0.1`.
4. IF calibration is not yet complete (fewer than 30 samples collected), THEN THE `GazeDetector` SHALL use the default thresholds `left_thresh = 0.42` and `right_thresh = 0.58`.
5. THE `GazeCalibrator` SHALL ensure `left_thresh < right_thresh` at all times.

### Requirement 3: Gaze Stability Baseline Personalization

**User Story:** As a user, I want the system to learn my natural gaze movement patterns, so that I am not penalized for gaze transitions that are normal for me.

#### Acceptance Criteria

1. WHILE in `BaselinePhase`, THE `Personalization` SHALL count gaze direction transitions and store the result as `baseline_gaze_transitions`.
2. WHEN `BaselinePhase` ends, THE `Personalization` SHALL compute `gaze_transition_threshold = baseline_gaze_transitions * 1.5`.
3. WHEN the current session's gaze transition count exceeds `gaze_transition_threshold`, THE `Personalization` SHALL signal a gaze instability penalty to `AttentionScorer`.
4. IF `BaselinePhase` has not completed, THEN THE `Personalization` SHALL apply no gaze instability penalty.

### Requirement 4: Fatigue Personalization

**User Story:** As a user, I want the fatigue threshold to reflect my personal baseline blink rate and fatigue score, so that the system does not flag normal tiredness as a fatigue event.

#### Acceptance Criteria

1. WHILE in `BaselinePhase`, THE `Personalization` SHALL record blink rate samples as `baseline_blink_rate` and fatigue score samples as `baseline_fatigue_score`.
2. WHEN `BaselinePhase` ends, THE `Personalization` SHALL compute `fatigue_threshold = mean(baseline_fatigue_score) + 15`.
3. THE `Personalization` SHALL expose `fatigue_threshold` for use by `StateClassifier` in place of the system default of 60.
4. IF `BaselinePhase` has not completed, THEN THE `Personalization` SHALL return the default fatigue threshold of 60.

### Requirement 5: Off-Screen Time Personalization

**User Story:** As a user, I want the off-screen time threshold to adapt to my natural reading and thinking patterns, so that brief natural glances away are not counted as distractions.

#### Acceptance Criteria

1. WHILE in `BaselinePhase`, THE `Personalization` SHALL record off-screen time samples as `baseline_off_time`.
2. WHEN `BaselinePhase` ends, THE `Personalization` SHALL compute `off_threshold = mean(baseline_off_time) + 2`.
3. THE `Personalization` SHALL expose `off_threshold` for use by `StateClassifier` in place of the system default of 3 seconds.
4. IF `BaselinePhase` has not completed, THEN THE `Personalization` SHALL return the default off-screen threshold of 3 seconds.

### Requirement 6: Mode Selection Fix

**User Story:** As a user, I want the mode I select in the web interface to actually change the monitoring behavior, so that reading, problem-solving, and lecture modes apply their respective scoring weights.

#### Acceptance Criteria

1. WHEN the user selects a mode in the web interface and starts a session, THE `WebApp` SHALL pass the selected mode value (1, 2, or 3) to `MainProcess` via stdin before the process reads input.
2. THE `MainProcess` SHALL read the mode value from stdin and map it to the corresponding mode string (`READING`, `PROBLEM_SOLVING`, or `LECTURE`).
3. IF no mode value is provided or the value is invalid, THEN THE `MainProcess` SHALL default to `READING` mode.
4. THE `WebApp` SHALL expose a mode selection input in the session start flow that sends the selected value with the `/api/session/start` POST request body.

### Requirement 7: Nose Displacement Movement Tracking

**User Story:** As a user, I want the system to detect excessive head movement, so that restlessness or fidgeting is reflected in my attention score.

#### Acceptance Criteria

1. THE `MovementDetector` SHALL track the 2D position of the nose tip landmark across consecutive frames.
2. WHEN a new frame is processed, THE `MovementDetector` SHALL compute the Euclidean displacement of the nose tip from its position in the previous frame.
3. WHEN nose displacement exceeds a configurable threshold (default: 15 pixels), THE `MovementDetector` SHALL return a movement penalty value.
4. THE `AttentionScorer` SHALL subtract the movement penalty from the raw attention score, with the penalty capped at 10 points per frame.
5. IF no previous nose position is available (first frame or face lost), THEN THE `MovementDetector` SHALL return a penalty of 0.
6. THE `MovementDetector` SHALL require no deep learning model and SHALL use only landmark coordinates already provided by the existing `FaceMeshDetector`.

### Requirement 8: Teacher System SQLite Persistence

**User Story:** As a teacher, I want student attention data to be persisted to a database, so that I can review historical session data after students disconnect.

#### Acceptance Criteria

1. WHEN `TeacherServer` starts, THE `SessionDB` SHALL create a SQLite database file and a `class_data` table with columns: `student_id`, `score`, `state`, `fatigue`, `gaze`, `blinks`, `timestamp`.
2. WHEN a valid POST request is received at `/send-data`, THE `TeacherServer` SHALL insert the student data record into the `class_data` table in addition to updating the in-memory store.
3. THE `TeacherServer` SHALL maintain the existing in-memory `class_data` dict alongside the SQLite store so that real-time WebSocket broadcasts are unaffected.
4. IF the SQLite insert fails, THEN THE `TeacherServer` SHALL log the error and continue processing the request using the in-memory store without returning an error to the client.
5. THE `SessionDB` SHALL use Python's built-in `sqlite3` module and SHALL require no additional dependencies.
