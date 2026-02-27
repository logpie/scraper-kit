"""Seen-set management: load, save, should_refetch.

The seen set tracks which posts have been fetched before and their engagement
levels, enabling smart dedup (skip unchanged posts, refetch trending ones).

The adapter provides parse_engagement() for engagement comparison.
Path management is runtime-injected — no hardcoded paths.
"""
import json
import logging
import os
import tempfile

log = logging.getLogger(__name__)


def _atomic_write_json(filepath: str, data) -> None:
    """Atomically write JSON to avoid partial writes."""
    directory = os.path.dirname(filepath) or "."
    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            delete=False,
            dir=directory,
            encoding="utf-8",
        ) as tmp:
            json.dump(data, tmp, ensure_ascii=False)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = tmp.name
        os.replace(tmp_path, filepath)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def load_seen(seen_file: str) -> dict:
    """Load seen data from a JSON file.

    Returns dict mapping note_id -> {"likes": int, "comments": int, "ts": str}.
    Auto-migrates from old list format.
    """
    if not os.path.exists(seen_file):
        return {}
    try:
        with open(seen_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
        log.warning("Failed to load seen data %s: %s", seen_file, exc)
        return {}
    # Old format: list of ID strings -> migrate
    if isinstance(data, list):
        return {nid: {"likes": 0, "comments": 0} for nid in data}
    if not isinstance(data, dict):
        log.warning("Invalid seen data format in %s (expected dict/list)", seen_file)
        return {}
    normalized = {}
    for nid, value in data.items():
        if not nid:
            continue
        if isinstance(value, dict):
            normalized[nid] = {
                "likes": _safe_int(value.get("likes", 0)),
                "comments": _safe_int(value.get("comments", 0)),
                "ts": value.get("ts", "") or "",
            }
        else:
            normalized[nid] = {"likes": 0, "comments": 0, "ts": ""}
    return normalized


def save_seen(seen_file: str, seen_data: dict) -> None:
    """Persist the seen data dict."""
    directory = os.path.dirname(seen_file)
    if directory:
        os.makedirs(directory, exist_ok=True)
    _atomic_write_json(seen_file, seen_data)


def should_refetch(card: dict, seen_data: dict,
                   parse_engagement,
                   likes_multiplier: float = 2.0,
                   likes_abs_threshold: int = 50) -> tuple[bool, bool]:
    """Decide whether to fetch detail for a card.

    Args:
        card: Card dict with at least 'note_id' and engagement data.
        seen_data: Dict mapping note_id -> {"likes": int, "comments": int}.
        parse_engagement: Callable to parse engagement strings to int
            (adapter.parse_engagement).
        likes_multiplier: Refetch if new likes >= old * multiplier.
        likes_abs_threshold: Refetch if likes increase >= threshold.

    Returns (should_fetch, is_trending):
      - should_fetch: True if we should click into this post
      - is_trending: True if this is a seen post with engagement spike
    """
    nid = card.get("note_id", "")
    if nid not in seen_data:
        return True, False  # unseen -> always fetch

    old = seen_data.get(nid, {})
    if not isinstance(old, dict):
        old = {}
    old_likes = old.get("likes", 0)
    new_likes = parse_engagement(card.get("likes_from_card", "0"))

    if old_likes == 0:
        # No baseline (migrated from old format) -> skip, can't compare
        return False, False

    if (new_likes >= old_likes * likes_multiplier or
            new_likes - old_likes >= likes_abs_threshold):
        return True, True  # fetch + trending

    return False, False  # seen + unchanged -> skip
