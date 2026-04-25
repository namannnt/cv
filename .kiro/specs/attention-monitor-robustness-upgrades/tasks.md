# Implementation Plan: Attention Monitor Robustness Upgrades

## Overview

Additive upgrades across five areas: gaze accuracy (head-pose + calibration), personalization depth (gaze stability, fatigue, off-screen thresholds), mode selection fix, movement tracking, and teacher-system SQLite persistence. All changes fall back gracefully to existing defaults.

## Tasks

- [x] 1. Add HeadPoseEstimator to `features/gaze.py`
  - [x] 1.1 Implement `HeadPoseEstimator` class with `MODEL_POINTS` and `estimate_yaw` method
    - Use 6 landmarks (indices 1, 152, 33, 263, 61, 291) and `cv2.solvePnP`
    - Return `0.0` on failure so callers use raw ratio unchanged
    - _Requirements: 1.1, 1.4, 1.5_

  - [ ]* 1.2 Write property test for head-pose adjustment formula
    - **Property 1: Head-pose adjustment formula**
    - `@given(raw_ratio=floats(0,1), yaw=floats(-45,45))` — verify `adjusted == raw - yaw*0.01`
    - **Validates: Requirements 1.2**

  - [x] 1.3 Extend `GazeDetector.get_gaze_direction` to call `HeadPoseEstimator.estimate_yaw` and apply `adjusted_ratio = raw_ratio - (yaw * 0.01)`
    - Instantiate `HeadPoseEstimator` in `GazeDetector.__init__`
    - Use `adjusted_ratio` for all threshold comparisons; fall back to `raw_ratio` on failure
    - _Requirements: 1.2, 1.3, 1.4_

  - [ ]* 1.4 Write unit tests for `HeadPoseEstimator`
    - Test `estimate_yaw` with known landmark coordinates returns a plausible value
    - Test failure path returns `0.0`
    - _Requirements: 1.4_

- [x] 2. Add `GazeCalibrator` to `features/gaze.py`
  - [x] 2.1 Implement `GazeCalibrator` class with `center_buffer`, `update`, and `get_thresholds` methods
    - Collect `adjusted_ratio` values for ~7 s; compute `center_mean` once ≥ 30 samples exist
    - Set `left_thresh = center_mean - 0.1`, `right_thresh = center_mean + 0.1`
    - Return defaults `(0.42, 0.58)` until calibrated
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [ ]* 2.2 Write property test for gaze calibration threshold derivation
    - **Property 2: Gaze calibration threshold derivation**
    - `@given(samples=lists(floats(0.1,0.9), min_size=30))` — verify `left = mean-0.1`, `right = mean+0.1`, and `left < right`
    - **Validates: Requirements 2.2, 2.3, 2.5**

  - [x] 2.3 Wire `GazeCalibrator` into `GazeDetector`
    - Instantiate in `__init__`; call `calibrator.update(adjusted_ratio)` and fetch thresholds from `calibrator.get_thresholds()` each frame
    - _Requirements: 2.1, 2.4_

  - [ ]* 2.4 Write unit tests for `GazeCalibrator`
    - Test default thresholds returned before 30 samples
    - Test correct thresholds computed after 30 samples
    - _Requirements: 2.2, 2.4_

- [ ] 3. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Extend `Personalization` with gaze stability, fatigue, and off-screen baselines
  - [x] 4.1 Add new attributes to `Personalization.__init__` for gaze transitions, fatigue samples, and off-screen samples
    - `gaze_transitions`, `_prev_gaze`, `baseline_gaze_transitions`, `gaze_transition_threshold`
    - `baseline_fatigue_samples`, `baseline_off_time_samples`
    - _Requirements: 3.1, 4.1, 5.1_

  - [x] 4.2 Extend `Personalization.update` to record gaze transitions, fatigue scores, and off-screen times during baseline phase
    - Count consecutive gaze direction changes; set `gaze_transition_threshold = baseline_gaze_transitions * 1.5` at baseline end
    - _Requirements: 3.1, 3.2, 4.1, 5.1_

  - [ ]* 4.3 Write property test for gaze transition counting
    - **Property 3: Gaze transition counting**
    - `@given(gazes=lists(sampled_from(["LEFT","CENTER","RIGHT"]), min_size=1))` — verify `baseline_gaze_transitions` equals count of consecutive direction changes
    - **Validates: Requirements 3.1**

  - [x] 4.4 Add `get_gaze_instability_penalty`, `get_fatigue_threshold`, and `get_off_threshold` methods to `Personalization`
    - `get_fatigue_threshold`: returns `mean(baseline_fatigue_samples) + 15`, or `60` if baseline incomplete
    - `get_off_threshold`: returns `mean(baseline_off_time_samples) + 2`, or `3.0` if baseline incomplete
    - `get_gaze_instability_penalty`: returns > 0 iff `current_transitions > gaze_transition_threshold`
    - _Requirements: 3.3, 3.4, 4.2, 4.3, 4.4, 5.2, 5.3, 5.4_

  - [ ]* 4.5 Write property tests for personalization threshold formulas and gaze instability penalty
    - **Property 4: Personalization threshold formulas**
    - `@given(fatigue_samples=lists(floats(0,100), min_size=1), off_samples=lists(floats(0,10), min_size=1))` — verify formulas
    - **Property 5: Gaze instability penalty signal**
    - `@given(count=integers(0,100), threshold=floats(0,100))` — verify penalty > 0 iff `count > threshold`
    - **Validates: Requirements 4.2, 5.2, 3.3**

  - [ ]* 4.6 Write unit tests for `Personalization` new methods
    - Test `get_fatigue_threshold` returns 60 before baseline ends
    - Test `get_off_threshold` returns 3.0 before baseline ends
    - _Requirements: 4.4, 5.4_

- [-] 5. Wire personalization thresholds into `main.py` and `StateClassifier`
  - [ ] 5.1 Update `StateClassifier.classify` in `intelligence/classification.py` to accept optional `off_threshold` parameter (default `3`)
    - Existing call signature must remain valid
    - _Requirements: 5.3_

  - [ ] 5.2 Update `main.py` to pass `fatigue_score` and `off_time` to `personalization.update()` and read dynamic thresholds
    - Call `personalization.get_fatigue_threshold()` and `personalization.get_off_threshold()` each loop iteration
    - Pass thresholds to `classifier.classify`
    - _Requirements: 3.3, 4.3, 5.3_

- [ ] 6. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Implement `MovementDetector` in `features/movement.py`
  - [ ] 7.1 Implement `MovementDetector` class with `update` and `reset` methods
    - Track nose tip (landmark index 1) displacement between frames using Euclidean distance
    - Return penalty in `[0, 10]` when displacement > 15 px; return 0 on first call or after face loss
    - _Requirements: 7.1, 7.2, 7.3, 7.5, 7.6_

  - [ ]* 7.2 Write property test for nose displacement computation
    - **Property 6: Nose displacement computation**
    - `@given(p1=tuples(integers(0,640),integers(0,480)), p2=tuples(integers(0,640),integers(0,480)))` — verify displacement formula and penalty cap
    - **Validates: Requirements 7.2, 7.3, 7.4**

  - [ ] 7.3 Add optional `movement_penalty=0.0` parameter to `AttentionScorer.calculate` in `intelligence/scoring.py`
    - Subtract `min(10, movement_penalty)` from score
    - _Requirements: 7.4_

  - [ ] 7.4 Wire `MovementDetector` into `main.py`
    - Instantiate once at startup; call `movement_detector.update(nose_pos)` inside `if landmarks:` block
    - Call `movement_detector.reset()` in the `else` (face lost) block
    - Pass penalty to `scorer.calculate`
    - _Requirements: 7.1, 7.4, 7.5_

  - [ ]* 7.5 Write unit tests for `MovementDetector`
    - Test returns 0 on first call
    - Test returns 0 when displacement ≤ threshold
    - Test penalty capped at 10
    - _Requirements: 7.3, 7.4, 7.5_

- [ ] 8. Fix mode selection in web UI and `attention-web/app.py`
  - [ ] 8.1 Add `<select id="modeSelect">` with options 1/2/3 to `attention-web/templates/index.html`
    - _Requirements: 6.4_

  - [ ] 8.2 Update `toggleSession()` in `attention-web/static/js/app.js` to read `modeSelect` value and include it in the POST body
    - _Requirements: 6.1_

  - [ ] 8.3 Update `/api/session/start` in `attention-web/app.py` to read `mode` from JSON body, validate it, and write it to subprocess stdin
    - Validate mode is in `("1", "2", "3")`; default to `"1"` otherwise
    - _Requirements: 6.1, 6.3_

  - [ ]* 8.4 Write unit tests for mode mapping
    - Test all three valid inputs map to correct mode strings
    - Test invalid input defaults to `READING`
    - _Requirements: 6.2, 6.3_

- [ ] 9. Add `SessionDB` to `teacher-system/server.py`
  - [ ] 9.1 Implement `SessionDB` class with `_init_db` and `insert` methods using `sqlite3`
    - Create `class_data` table on init; catch and log insert failures without raising
    - _Requirements: 8.1, 8.4, 8.5_

  - [ ]* 9.2 Write property test for dual-store consistency
    - **Property 7: Dual-store consistency**
    - `@given(data=student_data_strategy())` — verify both in-memory dict and SQLite contain matching record after POST
    - **Validates: Requirements 8.2, 8.3**

  - [ ] 9.3 Instantiate `SessionDB` at module level in `server.py` and call `session_db.insert(...)` in the `send_data` handler after updating `class_data`
    - In-memory dict and WebSocket broadcast path must remain untouched
    - _Requirements: 8.2, 8.3_

  - [ ]* 9.4 Write unit and integration tests for `SessionDB`
    - Test `_init_db` creates table on fresh in-memory database
    - Test POST to `/send-data` inserts SQLite row
    - Test SQLite failure → HTTP 200 still returned and error logged
    - _Requirements: 8.1, 8.2, 8.4_

- [ ] 10. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- All changes are strictly additive; no existing logic is removed or refactored
- Every new code path falls back to system defaults when calibration/baseline data is unavailable
- Property tests use Hypothesis; run with `pytest tests/ --hypothesis-seed=0`
