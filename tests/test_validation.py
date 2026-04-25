"""
Validation layer — compares predicted attention states against
manually labeled expected behavior for known test scenarios.

This is a qualitative evaluation, not a train/test split, because:
- We have no large labeled dataset
- The system is rule-based, not trained
- Ground truth is defined by the developer based on known behavior

Each test case represents a scenario with known expected output.
We verify the system produces the correct state for that scenario.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'attention-monitor'))

from intelligence.scoring import AttentionScorer
from intelligence.classification import StateClassifier
from intelligence.fatigue import FatigueDetector

scorer    = AttentionScorer()
classifier = StateClassifier()


def simulate(gaze, off_time, eye_closed, blink_rate, fatigue_score,
             blink_threshold=20, gaze_w=0.5, blink_w=0.2):
    score = scorer.calculate(gaze, off_time, eye_closed, blink_rate,
                             blink_threshold, gaze_w, blink_w)
    state = classifier.classify(score, off_time, fatigue_score)
    return score, state


# ── Scenario 1: Student actively reading ──
# Expected: FOCUSED
# Signals: gaze CENTER, no blink excess, no fatigue
def test_scenario_reading_focused():
    score, state = simulate("CENTER", 0, False, 12, 5)
    assert state == "FOCUSED", f"Expected FOCUSED, got {state} (score={score})"
    assert score >= 70

# ── Scenario 2: Student looks away for 5 seconds ──
# Expected: DISTRACTED
# Signals: gaze LEFT, off_time=5s
def test_scenario_looking_away():
    score, state = simulate("LEFT", 5.0, False, 12, 5)
    assert state == "DISTRACTED", f"Expected DISTRACTED, got {state} (score={score})"

# ── Scenario 3: Student blinking normally ──
# A single blink lasts ~150ms. EAR drops below threshold for ~4 frames.
# The score smoother averages this over 1s window.
# Expected: FOCUSED (blink should not cause DISTRACTED)
def test_scenario_normal_blink():
    # eye_closed=True but off_time=0, blink_rate=15 (normal)
    score, state = simulate("CENTER", 0, True, 15, 5)
    # score = 100 - 30 (eye closed) = 70 → FOCUSED boundary
    assert score == 70.0
    assert state == "FOCUSED"

# ── Scenario 4: Student thinking (looking up briefly) ──
# Problem-solving mode: gaze_w=0.3 (looking away is more acceptable)
# Expected: score higher than in READING mode for same gaze
def test_scenario_thinking_problem_solving():
    score_reading, _  = simulate("LEFT", 2.0, False, 12, 5, gaze_w=0.5)
    score_problem, _  = simulate("LEFT", 2.0, False, 12, 5, gaze_w=0.3)
    assert score_problem > score_reading, \
        "Problem-solving mode should penalize gaze less than reading mode"

# ── Scenario 5: Fatigued student ──
# Expected: FATIGUED regardless of attention score
def test_scenario_fatigued():
    score, state = simulate("CENTER", 0, False, 12, 65)
    assert state == "FATIGUED", f"Expected FATIGUED, got {state}"

# ── Scenario 6: Low attention but not distracted ──
# Expected: LOW FOCUS
def test_scenario_low_focus():
    score, state = simulate("CENTER", 0, False, 12, 5)
    # manually set score to 55 range by adjusting blink rate above threshold
    score2, state2 = simulate("CENTER", 0, False, 25, 5, blink_threshold=20)
    # score = 100 - 20 = 80 → FOCUSED, not LOW FOCUS
    # To get LOW FOCUS we need score 41-70 without off_screen > 3
    # Use gaze off for 1s: 100 - 10 = 90 → still FOCUSED
    # Use eye closed + blink: 100 - 30 - 20 = 50 → LOW FOCUS
    score3, state3 = simulate("CENTER", 0, True, 25, 5, blink_threshold=20)
    assert state3 == "LOW FOCUS", f"Expected LOW FOCUS, got {state3} (score={score3})"
    assert 40 < score3 <= 70

# ── Summary report ──
if __name__ == "__main__":
    scenarios = [
        ("Reading focused",        lambda: simulate("CENTER", 0, False, 12, 5)),
        ("Looking away 5s",        lambda: simulate("LEFT", 5.0, False, 12, 5)),
        ("Normal blink",           lambda: simulate("CENTER", 0, True, 15, 5)),
        ("Thinking (PS mode)",     lambda: simulate("LEFT", 2.0, False, 12, 5, gaze_w=0.3)),
        ("Fatigued",               lambda: simulate("CENTER", 0, False, 12, 65)),
        ("Low focus",              lambda: simulate("CENTER", 0, True, 25, 5)),
    ]
    print(f"\n{'Scenario':<30} {'Score':>6} {'State':<15}")
    print("-" * 55)
    for name, fn in scenarios:
        score, state = fn()
        print(f"{name:<30} {score:>6.1f} {state:<15}")
