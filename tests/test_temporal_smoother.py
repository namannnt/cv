import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'attention-monitor'))

from utils.temporal_smoother import TemporalSmoother


def test_single_sample_returns_value():
    s = TemporalSmoother(window_seconds=1.0)
    assert s.update(80.0) == 80.0

def test_average_of_two_samples():
    s = TemporalSmoother(window_seconds=2.0)
    s.update(60.0)
    result = s.update(80.0)
    assert result == 70.0

def test_old_samples_evicted():
    s = TemporalSmoother(window_seconds=0.1)
    s.update(100.0)
    time.sleep(0.15)
    result = s.update(50.0)
    assert result == 50.0  # old sample evicted

def test_confidence_stable_signal():
    s = TemporalSmoother(window_seconds=2.0)
    for _ in range(10):
        s.update(80.0)
    assert s.get_confidence() == 1.0  # zero variance

def test_confidence_unstable_signal():
    s = TemporalSmoother(window_seconds=2.0)
    for i in range(10):
        s.update(0.0 if i % 2 == 0 else 100.0)
    assert s.get_confidence() < 0.5  # high variance = low confidence
