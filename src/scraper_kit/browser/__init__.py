"""browser — reusable Playwright/CDP browser automation primitives.

Zero site-specific dependencies. macOS and Linux only (uses lsof/signals).
"""
from .chrome import find_system_chrome, launch_cdp_browser, kill_stale_cdp  # noqa: F401
from .cookies import migrate_cookies  # noqa: F401
from .stealth import build_stealth_shim, inject_stealth, setup_cdp_stealth  # noqa: F401
from .ua import get_chromium_version, build_user_agent  # noqa: F401
