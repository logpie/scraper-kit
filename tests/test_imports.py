"""Smoke tests: all moved modules are importable."""


def test_browser_imports():
    from scraper_kit.browser import (
        find_system_chrome,
        launch_cdp_browser,
        kill_stale_cdp,
        migrate_cookies,
        build_stealth_shim,
        inject_stealth,
        setup_cdp_stealth,
        get_chromium_version,
        build_user_agent,
    )
    assert callable(find_system_chrome)
    assert callable(launch_cdp_browser)
    assert callable(kill_stale_cdp)
    assert callable(migrate_cookies)
    assert callable(build_stealth_shim)
    assert callable(inject_stealth)
    assert callable(setup_cdp_stealth)
    assert callable(get_chromium_version)
    assert callable(build_user_agent)


def test_human_imports():
    from scraper_kit.human import (
        human_sleep,
        bezier_move,
        inertial_wheel,
        human_scroll,
        human_click,
        human_dismiss_modal,
        scroll_count,
    )
    assert callable(human_sleep)
    assert callable(bezier_move)
    assert callable(inertial_wheel)
    assert callable(human_scroll)
    assert callable(human_click)
    assert callable(human_dismiss_modal)
    assert callable(scroll_count)


def test_telemetry_imports():
    from scraper_kit.telemetry import FetchEventLogger
    assert callable(FetchEventLogger)


def test_engine_imports():
    from scraper_kit.engine import HealthMonitor, ScraperSignal, ScraperError
    assert callable(HealthMonitor)
    assert ScraperSignal.CAPTCHA.value == "captcha"
    assert issubclass(ScraperError, Exception)
