"""Tests for HealthMonitor — migrated from xhs-bot test_health_monitor.py."""
from scraper_kit.engine.health import HealthMonitor


def test_initial_score_is_healthy():
    hm = HealthMonitor()
    assert hm.score == 1.0
    assert not hm.should_stop
    assert not hm.should_backoff


def test_ok_events_keep_healthy():
    hm = HealthMonitor()
    for _ in range(5):
        hm.record("ok")
    assert hm.score > 0.9
    assert not hm.should_stop
    assert not hm.should_backoff


def test_captcha_degrades_score():
    hm = HealthMonitor()
    for _ in range(5):
        hm.record("captcha")
    assert hm.score < 0.6
    assert hm.should_backoff


def test_auth_expired_triggers_stop():
    hm = HealthMonitor()
    for _ in range(3):
        hm.record("auth_expired")
    assert hm.should_stop


def test_mixed_events():
    hm = HealthMonitor()
    for _ in range(8):
        hm.record("ok")
    hm.record("captcha")
    hm.record("timeout")
    assert 0.5 < hm.score < 1.0
    assert not hm.should_stop


def test_stats():
    hm = HealthMonitor()
    hm.record("ok")
    hm.record("ok")
    hm.record("captcha")
    stats = hm.stats
    assert stats["events"]["ok"] == 2
    assert stats["events"]["captcha"] == 1
    assert stats["total"] == 3
    assert 0.0 <= stats["score"] <= 1.0


def test_window_limit():
    hm = HealthMonitor(window=5)
    for _ in range(10):
        hm.record("ok")
    assert hm.stats["total"] == 5
