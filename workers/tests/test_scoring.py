from workers.common.quarantine import should_quarantine
from workers.common.scoring import composite_score, normalize_latency, normalize_speed


def test_normalizers_and_score_ranges():
    assert 0 <= normalize_latency(100) <= 1
    assert 0 <= normalize_speed(20, 20) <= 1
    score = composite_score(0.8, 0.9, 0.7, 0.1)
    assert 0 <= score <= 1


def test_should_quarantine_cases():
    assert should_quarantine(0.2, 100, 0.1) is True
    assert should_quarantine(0.9, 5000, 0.1, 1000) is True
    assert should_quarantine(0.9, 100, 0.9) is True
    assert should_quarantine(0.9, 100, 0.1) is False
