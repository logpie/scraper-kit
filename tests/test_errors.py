"""Tests for ScraperSignal and ScraperError."""
from scraper_kit.engine.errors import ScraperSignal, ScraperError


def test_signal_values():
    assert ScraperSignal.CAPTCHA.value == "captcha"
    assert ScraperSignal.AUTH_EXPIRED.value == "auth_expired"
    assert ScraperSignal.RATE_LIMITED.value == "rate_limited"
    assert ScraperSignal.TRANSIENT.value == "transient"
    assert ScraperSignal.FATAL.value == "fatal"


def test_scraper_error_with_message():
    err = ScraperError(ScraperSignal.CAPTCHA, "Bot detected")
    assert err.signal == ScraperSignal.CAPTCHA
    assert str(err) == "Bot detected"


def test_scraper_error_default_message():
    err = ScraperError(ScraperSignal.FATAL)
    assert str(err) == "fatal"


def test_scraper_error_is_exception():
    try:
        raise ScraperError(ScraperSignal.TRANSIENT, "retry later")
    except ScraperError as e:
        assert e.signal == ScraperSignal.TRANSIENT
    except Exception:
        raise AssertionError("ScraperError should be catchable as ScraperError")
