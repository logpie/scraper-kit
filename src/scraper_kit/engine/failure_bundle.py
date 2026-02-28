"""Diagnostic snapshot capture on fetch failures.

Captures page state, tap buffer info, and timing data when a post detail
fetch fails. Designed for zero overhead when disabled (verbosity="off").
"""
import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Any

log = logging.getLogger(__name__)


class BundleVerbosity:
    OFF = "off"             # No capture at all
    MINIMAL = "minimal"     # tap state + timing only (~0ms overhead)
    STANDARD = "standard"   # + page URL/title/text snippet (~10ms)
    FULL = "full"           # + screenshot (~200-500ms)


@dataclass
class FailureBundle:
    note_id: str
    reason: str
    site: str
    keyword: str
    page_url: str = ""
    page_title: str = ""
    page_text_snippet: str = ""
    tap_has_feed: bool = False
    tap_has_comments: bool = False
    tap_feed_keys: list[str] = field(default_factory=list)
    tap_comment_count: int = 0
    phase_timings: dict[str, float] = field(default_factory=dict)
    total_elapsed: float = 0.0
    health_score: float = -1.0
    adapter_extras: dict[str, Any] = field(default_factory=dict)
    screenshot_path: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)


def capture_failure_bundle(
    page,
    tap,
    adapter,
    note_id: str,
    reason: str,
    keyword: str = "",
    phase_timings: dict | None = None,
    total_elapsed: float = 0.0,
    health_score: float = -1.0,
    verbosity: str = BundleVerbosity.STANDARD,
    screenshot_dir: str = "",
) -> FailureBundle:
    """Best-effort capture of failure diagnostics. Never raises."""
    bundle = FailureBundle(
        note_id=note_id,
        reason=reason,
        site=getattr(adapter, "SITE_NAME", "unknown"),
        keyword=keyword,
        phase_timings=phase_timings or {},
        total_elapsed=total_elapsed,
        health_score=health_score,
    )

    try:
        # Tap state (always captured — zero overhead)
        feed = tap.get_feed(note_id) if tap else None
        comments = tap.get_comments(note_id) if tap else []
        bundle.tap_has_feed = feed is not None
        bundle.tap_has_comments = len(comments) > 0
        bundle.tap_feed_keys = list(feed.keys()) if feed else []
        bundle.tap_comment_count = len(comments)
    except Exception:
        pass

    if verbosity in (BundleVerbosity.STANDARD, BundleVerbosity.FULL):
        try:
            bundle.page_url = page.url or ""
        except Exception:
            pass
        try:
            bundle.page_title = page.title() or ""
        except Exception:
            pass
        try:
            snippet = page.evaluate("() => document.body?.innerText?.slice(0, 2000) || ''")
            bundle.page_text_snippet = snippet or ""
        except Exception:
            pass

    if verbosity == BundleVerbosity.FULL and screenshot_dir:
        try:
            os.makedirs(screenshot_dir, exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S") + f"_{int(time.time() * 1000) % 1000:03d}"
            safe_id = note_id.replace("/", "_")[:50]
            path = os.path.join(screenshot_dir, f"fail_{ts}_{safe_id}.png")
            page.screenshot(path=path, full_page=False)
            bundle.screenshot_path = path
        except Exception:
            pass

    # Adapter extras (duck typing — no protocol change)
    try:
        if hasattr(adapter, "get_failure_diagnostics"):
            extras = adapter.get_failure_diagnostics(page, note_id)
            if isinstance(extras, dict):
                bundle.adapter_extras = extras
    except Exception:
        pass

    return bundle


def save_failure_bundle(bundle: FailureBundle, base_dir: str = "data/logs/failures") -> str:
    """Save bundle to JSON. Returns file path, or '' on failure."""
    try:
        site = bundle.site or "unknown"
        keyword = (bundle.keyword or "unknown").replace("/", "_").replace("\\", "_")
        out_dir = os.path.join(base_dir, site, keyword)
        os.makedirs(out_dir, exist_ok=True)

        ts = time.strftime("%Y%m%d_%H%M%S") + f"_{int(time.time() * 1000) % 1000:03d}"
        safe_id = bundle.note_id.replace("/", "_")[:50]
        path = os.path.join(out_dir, f"{ts}_{safe_id}.json")

        with open(path, "w", encoding="utf-8") as f:
            json.dump(bundle.to_dict(), f, ensure_ascii=False, indent=2, default=str)
        return path
    except Exception as e:
        log.debug(f"Failed to save failure bundle: {e}")
        return ""
