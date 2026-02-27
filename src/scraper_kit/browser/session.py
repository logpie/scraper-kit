"""Generic browser session lifecycle with runtime path injection.

The framework never auto-opens a browser — the app layer is responsible
for providing page/context. This module provides helpers for apps that
want to manage browser lifecycle.
"""
import logging
import os
from contextlib import contextmanager
from typing import Any

log = logging.getLogger(__name__)


@contextmanager
def open_browser(
    playwright: Any,
    adapter: Any,
    *,
    headed: bool = False,
    cdp_port: int = 9222,
    user_data_dir: str = "",
    browser_state_path: str = "",
    stealth_js_path: str = "",
):
    """Open a browser session using the adapter's config.

    Tries CDP with system Chrome first, falls back to Playwright Chromium.
    Yields (page, context).

    All paths are runtime-injected — never derived from package location.
    """
    from .chrome import find_system_chrome, launch_cdp_browser, kill_stale_cdp
    from .cookies import migrate_cookies
    from .stealth import setup_cdp_stealth, inject_stealth
    from .ua import get_chromium_version, build_user_agent

    chrome_proc = None
    cdp_session = None
    browser = None
    context = None
    page = None
    chrome_version = None

    extra_args = adapter.get_cdp_args()
    locale = adapter.get_locale()

    # Try CDP mode first
    chrome_path = find_system_chrome()
    if chrome_path:
        try:
            kill_stale_cdp(port=cdp_port)
            browser, chrome_proc = launch_cdp_browser(
                playwright, chrome_path,
                headed=headed, port=cdp_port,
                user_data_dir=user_data_dir,
                extra_args=extra_args,
            )
            context = browser.contexts[0] if browser.contexts else browser.new_context(
                viewport={"width": 1920, "height": 1080},
                locale=locale,
            )
            page = context.pages[0] if context.pages else context.new_page()
            chrome_version = browser.version
            if browser_state_path:
                migrate_cookies(context, browser_state_path)
            cdp_session = setup_cdp_stealth(
                page, context, chrome_version,
                stealth_js_path=stealth_js_path,
            )
            adapter.ensure_loaded(page)
            log.info("Using CDP mode (system Chrome)")
        except Exception as e:
            log.warning(f"CDP launch failed ({e}), falling back to Playwright Chromium")
            if cdp_session is not None:
                try:
                    cdp_session.detach()
                except Exception:
                    pass
                cdp_session = None
            if context is not None:
                try:
                    context.close()
                except Exception:
                    pass
                context = None
            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass
            if chrome_proc:
                chrome_proc.terminate()
                try:
                    chrome_proc.wait(timeout=5)
                except Exception:
                    chrome_proc.kill()
                chrome_proc = None
            browser = None

    # Fallback to Playwright bundled Chromium
    if browser is None:
        chrome_version = get_chromium_version(playwright)
        user_agent = build_user_agent(chrome_version)
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=user_data_dir or os.path.join(os.getcwd(), "browser_data"),
            headless=not headed,
            viewport={"width": 1920, "height": 1080},
            user_agent=user_agent,
            device_scale_factor=2,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--exclude-switches=enable-automation",
                "--disable-infobars",
            ],
            locale=locale,
        )
        if browser_state_path:
            migrate_cookies(context, browser_state_path)
        page = context.pages[0] if context.pages else context.new_page()
        cdp_session = setup_cdp_stealth(
            page, context, chrome_version,
            stealth_js_path=stealth_js_path,
        )
        adapter.ensure_loaded(page)
        log.info("Using Playwright Chromium mode")

    try:
        yield page, context
    finally:
        if cdp_session is not None:
            try:
                cdp_session.detach()
            except Exception:
                pass
        if context is not None:
            try:
                context.close()
            except Exception as e:
                log.warning(f"Failed to close browser context cleanly: {e}")
        if chrome_proc:
            chrome_proc.terminate()
            try:
                chrome_proc.wait(timeout=5)
            except Exception:
                chrome_proc.kill()
