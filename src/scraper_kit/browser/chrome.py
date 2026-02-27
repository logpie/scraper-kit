"""Chrome discovery, CDP launch, and stale-process cleanup.

macOS and Linux only — uses lsof/signals for process management.
"""
import logging
import os
import platform
import shutil
import signal
import subprocess
import time
import urllib.request

log = logging.getLogger(__name__)


def find_system_chrome() -> str | None:
    """Find Chrome or Edge binary on the system.

    Returns the path to the browser executable, or None if not found.
    """
    system = platform.system()
    if system == "Darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
    elif system == "Linux":
        candidates = [
            "google-chrome",
            "google-chrome-stable",
            "chromium-browser",
            "chromium",
            "microsoft-edge",
            "microsoft-edge-stable",
        ]
    else:
        return None

    for candidate in candidates:
        if system == "Darwin":
            if os.path.isfile(candidate):
                return candidate
        else:
            path = shutil.which(candidate)
            if path:
                return path
    return None


def launch_cdp_browser(
    playwright,
    chrome_path: str,
    *,
    headed: bool = False,
    port: int = 9222,
    user_data_dir: str = "",
    extra_args: list[str] | None = None,
):
    """Launch system Chrome with remote debugging and connect via CDP.

    Returns ``(browser, chrome_proc)`` on success.

    Bug-fix vs the original monolith:
    * Wraps ``connect_over_cdp`` in try/except — terminates the spawned
      Chrome process before re-raising on connection failure.
    * Checks ``proc.poll()`` in the readiness loop to fail fast if Chrome
      exited unexpectedly.
    """
    if user_data_dir:
        os.makedirs(user_data_dir, exist_ok=True)

    args = [
        chrome_path,
        f"--remote-debugging-port={port}",
    ]
    if user_data_dir:
        args.append(f"--user-data-dir={user_data_dir}")
    if extra_args:
        args.extend(extra_args)
    if not headed:
        args.append("--headless=new")
    args.append("--window-size=1920,1080")
    args.append("about:blank")

    log.info("Launching Chrome via CDP: %s", os.path.basename(chrome_path))
    proc = subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    def _terminate_browser() -> None:
        if proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)

    # Wait for the debugger to be ready
    cdp_url = f"http://127.0.0.1:{port}"
    for _ in range(30):
        if proc.poll() is not None:
            raise RuntimeError(
                f"Chrome exited unexpectedly (code {proc.returncode})"
            )
        try:
            urllib.request.urlopen(f"{cdp_url}/json/version", timeout=1)
            break
        except Exception:
            time.sleep(0.3)
    else:
        _terminate_browser()
        raise RuntimeError("Chrome failed to start with remote debugging")

    try:
        browser = playwright.chromium.connect_over_cdp(cdp_url)
    except Exception:
        _terminate_browser()
        raise
    log.info("Connected to Chrome via CDP (port %d)", port)
    return browser, proc


def kill_stale_cdp(port: int = 9222) -> None:
    """Kill any existing Chrome process listening on *port*."""
    try:
        out = subprocess.check_output(
            ["lsof", "-ti", f":{port}"], text=True
        ).strip()
        if out:
            for pid_str in out.split("\n"):
                try:
                    os.kill(int(pid_str), signal.SIGTERM)
                except (ProcessLookupError, ValueError):
                    pass
            log.info("Killed stale Chrome on port %d", port)
    except subprocess.CalledProcessError:
        pass  # nothing on this port
    except FileNotFoundError:
        log.warning("lsof not found; cannot auto-kill stale CDP processes")
    time.sleep(2)
