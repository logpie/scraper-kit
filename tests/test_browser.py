"""Tests for browser module — no actual browser needed."""
from scraper_kit.browser.stealth import build_stealth_shim
from scraper_kit.browser.ua import build_user_agent
from scraper_kit.browser.cookies import migrate_cookies
from scraper_kit.browser.chrome import find_system_chrome


def test_build_stealth_shim_returns_js():
    js = build_stealth_shim("131.0.6778.86")
    assert "navigator" in js
    assert "userAgentData" in js
    assert "131" in js


def test_build_stealth_shim_custom_params():
    js = build_stealth_shim(
        "130.0.0.0",
        hardware_concurrency=8,
        device_memory=8,
        platform="Linux",
        screen_width=1920,
        screen_height=1080,
    )
    assert "Linux" in js
    assert "1920" in js


def test_build_user_agent():
    ua = build_user_agent("131.0.6778.86")
    assert "Chrome/131.0.6778.86" in ua
    assert "Macintosh" in ua


def test_build_user_agent_custom_template():
    ua = build_user_agent("131.0.0.0", template="MyBrowser/{version}")
    assert ua == "MyBrowser/131.0.0.0"


def test_migrate_cookies_missing_file():
    """migrate_cookies returns 0 for missing file."""

    class FakeContext:
        def add_cookies(self, cookies):
            pass

    assert migrate_cookies(FakeContext(), "/nonexistent/path.json") == 0


def test_find_system_chrome():
    """find_system_chrome returns a string or None."""
    result = find_system_chrome()
    assert result is None or isinstance(result, str)
