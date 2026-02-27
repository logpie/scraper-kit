"""Counting utilities for post limits."""
import time as _time

# card_only_reason values that represent posts we never attempted to fetch.
SKIP_REASONS = {"seen", "skipped"}


def fetch_count(posts: list[dict]) -> int:
    """Count posts we actually attempted to fetch (excludes seen/skipped)."""
    n = 0
    for p in posts:
        if p.get("card_only") and p.get("card_only_reason") in SKIP_REASONS:
            continue
        n += 1
    return n


def grind_count(posts: list[dict], max_age_days: int) -> int:
    """Count posts valid for grind mode: successfully fetched AND in the time window."""
    now = _time.time()
    cutoff = now - max_age_days * 86400
    n = 0
    for p in posts:
        if p.get("card_only"):
            continue
        ts = p.get("time") or 0
        # Timestamps may be in milliseconds; convert to seconds
        if ts > 1e12:
            ts = ts / 1000
        if ts <= 0 or ts >= cutoff:  # 0 = unknown -> benefit of doubt
            n += 1
    return n


def count_for_limit(posts: list[dict], grind: bool, max_age_days: int) -> int:
    """Count posts toward the max_posts limit."""
    return grind_count(posts, max_age_days) if grind else fetch_count(posts)
