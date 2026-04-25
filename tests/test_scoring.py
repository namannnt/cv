"""
Unit tests for AttentionScorer and StateClassifier.
Run with: pytest tests/
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'attention-monitor'))

import pytest
from intelligence.scoring import AttentionScorer
from intelligence.classification import StateClassifier


class TestAttentionScorer:
    def setup_method(self):
        self.scorer = AttentionScorer()

    def test_perfect_conditions(self):
        """No penalties → score = 100"""
        score = self.scorer.calculate(
            gaze="CENTER", off_screen_time=0,
            eye_closed=False, blink_rate=10,
            blink_threshold=20, gaze_w=0.5, blink_w=0.2
        )
        assert score == 100.0

    def test_eye_closed_penalty(self):
        """Eye closed → -30"""
        score = self.scorer.calculate(
            gaze="CENTER", off_screen_time=0,
            eye_closed=True, blink_rate=10,
            blink_threshold=20, gaze_w=0.5, blink_w=0.2
        )
        assert score == 70.0

    def test_gaze_off_penalty_scales_with_time(self):
        """Gaze off for 2s → penalty = min(40, 2*10) * 1.0 = 20"""
        score = self.scorer.calculate(
            gaze="LEFT", off_screen_time=2.0,
            eye_closed=False, blink_rate=10,
            blink_threshold=20, gaze_w=0.5, blink_w=0.2
        )
        assert score == 80.0

    def test_gaze_penalty_capped_at_40(self):
        """off_screen_time=10 → penalty capped at 40"""
        score = self.scorer.calculate(
            gaze="LEFT", off_screen_time=10.0,
            eye_closed=False, blink_rate=10,
            blink_threshold=20, gaze_w=0.5, blink_w=0.2
        )
        assert score == 60.0

    def test_blink_rate_penalty(self):
        """blink_rate > threshold → -20"""
        score = self.scorer.calculate(
            gaze="CENTER", off_screen_time=0,
            eye_closed=False, blink_rate=25,
            blink_threshold=20, gaze_w=0.5, blink_w=0.2
        )
        assert score == 80.0

    def test_all_penalties_stacked_clamped_to_zero(self):
        """All penalties active → score clamped to 0"""
        score = self.scorer.calculate(
            gaze="LEFT", off_screen_time=10.0,
            eye_closed=True, blink_rate=30,
            blink_threshold=20, gaze_w=0.5, blink_w=0.2
        )
        assert score == 0.0

    def test_gaze_weight_scales_penalty(self):
        """LECTURE mode gaze_w=0.6 → penalty = 20 * (0.6/0.5) = 24"""
        score = self.scorer.calculate(
            gaze="LEFT", off_screen_time=2.0,
            eye_closed=False, blink_rate=10,
            blink_threshold=20, gaze_w=0.6, blink_w=0.2
        )
        assert score == pytest.approx(76.0)

    def test_score_never_exceeds_100(self):
        score = self.scorer.calculate(
            gaze="CENTER", off_screen_time=0,
            eye_closed=False, blink_rate=0,
            blink_threshold=20, gaze_w=0.5, blink_w=0.2
        )
        assert score <= 100.0

    def test_score_never_below_zero(self):
        score = self.scorer.calculate(
            gaze="LEFT", off_screen_time=100.0,
            eye_closed=True, blink_rate=100,
            blink_threshold=5, gaze_w=1.0, blink_w=1.0
        )
        assert score >= 0.0


class TestStateClassifier:
    def setup_method(self):
        self.clf = StateClassifier()

    def test_focused(self):
        assert self.clf.classify(85, 0, 10) == "FOCUSED"

    def test_low_focus(self):
        assert self.clf.classify(55, 0, 10) == "LOW FOCUS"

    def test_distracted_by_score(self):
        assert self.clf.classify(30, 0, 10) == "DISTRACTED"

    def test_distracted_by_off_screen(self):
        """off_screen > 3s overrides score"""
        assert self.clf.classify(90, 4.0, 10) == "DISTRACTED"

    def test_fatigued_overrides_all(self):
        """fatigue >= 60 overrides even high score"""
        assert self.clf.classify(95, 0, 65) == "FATIGUED"

    def test_fatigued_threshold_boundary(self):
        assert self.clf.classify(80, 0, 59) == "FOCUSED"
        assert self.clf.classify(80, 0, 60) == "FATIGUED"

    def test_off_screen_boundary(self):
        assert self.clf.classify(80, 3.0, 10) == "FOCUSED"
        assert self.clf.classify(80, 3.1, 10) == "DISTRACTED"
