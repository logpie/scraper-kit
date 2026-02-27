"""Generic cookie migration from a Playwright storage-state JSON file."""
import json
import os


def migrate_cookies(context, state_path: str) -> int:
    """Import cookies from a storage-state JSON file into a browser context.

    Returns the number of cookies migrated.  Never raises — returns 0 on
    missing file, corrupt JSON, or any other error.
    """
    if not os.path.isfile(state_path):
        return 0
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
        cookies = state.get("cookies", [])
        if cookies:
            context.add_cookies(cookies)
            return len(cookies)
        return 0
    except Exception:
        return 0
