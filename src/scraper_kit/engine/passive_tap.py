"""Adapter-routed passive API response interceptor.

Listens to page.on("response") and routes intercepted responses through
the adapter's API route parsers. Zero extra network requests — captures
data from the site's own JS-triggered API calls.

Key differences from the XHS-specific PassiveTap:
- Route matching is adapter-driven (adapter.get_api_routes())
- note_id extraction is adapter-driven (adapter.extract_note_id_from_api())
- Bounded per-attempt buffers with stale-response guards
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlparse

log = logging.getLogger(__name__)

# Maximum entries per buffer to prevent memory leaks from unclaimed data.
_MAX_BUFFER_SIZE = 100


@dataclass
class WaitResult:
    """Result from PassiveTap.wait_for()."""
    feed: dict | None = None
    comments: list[dict] = field(default_factory=list)
    timed_out: bool = False
    elapsed: float = 0.0


class PassiveTap:
    """Intercept API responses passively via Playwright's response event.

    Adapter provides route matchers and parsers; the tap routes responses
    through them and stores parsed data keyed by note_id.
    """

    def __init__(self, page: Any, adapter: Any):
        self._page = page
        self._adapter = adapter
        self._routes = adapter.get_api_routes()
        self._feed_data: dict[str, dict] = {}      # note_id -> parsed post dict
        self._comment_data: dict[str, list] = {}    # note_id -> [comments]
        self._timestamps: dict[str, float] = {}     # note_id -> capture time
        self._listening = False

    def start(self):
        """Register page.on('response') listener."""
        if self._listening:
            return
        self._page.on("response", self._on_response)
        self._listening = True
        log.debug("PassiveTap started")

    def stop(self):
        """Remove listener."""
        if not self._listening:
            return
        try:
            self._page.remove_listener("response", self._on_response)
        except Exception:
            pass
        self._listening = False
        log.debug("PassiveTap stopped")

    def get_feed(self, note_id: str) -> dict | None:
        """Return captured feed data for note_id, or None."""
        feed = self._feed_data.get(note_id)
        return dict(feed) if isinstance(feed, dict) else None

    def get_comments(self, note_id: str) -> list[dict]:
        """Return captured comments for note_id."""
        comments = self._comment_data.get(note_id, [])
        return [dict(c) if isinstance(c, dict) else c for c in comments]

    def clear(self, note_id: str):
        """Clear captured data for a note_id (after consumption)."""
        self._feed_data.pop(note_id, None)
        self._comment_data.pop(note_id, None)
        self._timestamps.pop(note_id, None)

    def is_stale(self, note_id: str, max_age: float = 30.0) -> bool:
        """Check if captured data for note_id is stale (older than max_age seconds)."""
        ts = self._timestamps.get(note_id, 0)
        return (time.monotonic() - ts) > max_age if ts else False

    def wait_for(
        self,
        note_id: str,
        *,
        need_feed: bool = True,
        need_comments: bool = False,
        timeout: float = 2.0,
        poll_interval: int = 100,
    ) -> WaitResult:
        """Poll for passive API data, yielding to Playwright's event loop each tick.

        Uses page.wait_for_timeout() internally — this processes Playwright's
        event loop so _on_response callbacks fire. time.sleep() does NOT work.

        Returns WaitResult with captured data and timing info.
        """
        start = time.monotonic()
        deadline = start + timeout

        while time.monotonic() < deadline:
            # Check conditions
            feed = self.get_feed(note_id) if need_feed else None
            comments = self.get_comments(note_id) if need_comments else []
            feed_ok = (not need_feed) or (feed is not None)
            comments_ok = (not need_comments) or (len(comments) > 0)
            if feed_ok and comments_ok:
                return WaitResult(
                    feed=feed,
                    comments=comments,
                    timed_out=False,
                    elapsed=time.monotonic() - start,
                )
            # Yield to Playwright event loop, capping to remaining time
            remaining_ms = int((deadline - time.monotonic()) * 1000)
            try:
                self._page.wait_for_timeout(min(poll_interval, max(remaining_ms, 1)))
            except Exception:
                # Page may be closed/crashed — return best-effort data
                break

        # Final check after timeout (last tick may have delivered data)
        feed = self.get_feed(note_id) if need_feed else None
        comments = self.get_comments(note_id) if need_comments else []
        return WaitResult(
            feed=feed,
            comments=comments,
            timed_out=True,
            elapsed=time.monotonic() - start,
        )

    def _on_response(self, response):
        """Route intercepted responses to adapter-provided parsers."""
        try:
            url = response.url
            for pattern, parser in self._routes.items():
                if pattern in url:
                    self._handle_response(response, parser)
                    return
        except Exception as e:
            log.debug(f"PassiveTap listener error: {e}")

    def _handle_response(self, response, parser):
        """Parse response using adapter-provided parser and store results."""
        try:
            if response.status != 200:
                return
            body = response.json()
            if not isinstance(body, dict):
                return

            data_type, parsed = parser(body)
            if not parsed:
                return

            note_id = self._adapter.extract_note_id_from_api(data_type, parsed)
            if not note_id and data_type == "comments":
                note_id = self._extract_note_id_from_url(response.url)
            if not note_id:
                log.debug(f"PassiveTap: no note_id from {data_type} response")
                return

            now = time.monotonic()

            if data_type == "feed":
                # Enforce buffer size limit
                if len(self._feed_data) >= _MAX_BUFFER_SIZE:
                    self._evict_oldest(self._feed_data)
                self._feed_data[note_id] = parsed
                self._timestamps[note_id] = now
                log.debug(f"PassiveTap: captured feed for {note_id}")
            elif data_type == "comments":
                if len(self._comment_data) >= _MAX_BUFFER_SIZE:
                    self._evict_oldest(self._comment_data)
                existing = self._comment_data.get(note_id, [])
                self._comment_data[note_id] = self._merge_comments(existing, parsed)
                self._timestamps.setdefault(note_id, now)
                log.debug(f"PassiveTap: captured {len(parsed)} comments for {note_id}")
        except Exception as e:
            log.debug(f"PassiveTap: parse error: {e}")

    def _evict_oldest(self, data_dict: dict):
        """Remove the oldest entry from a buffer dict based on timestamps."""
        if not data_dict:
            return
        oldest_id = min(
            (nid for nid in data_dict if nid in self._timestamps),
            key=lambda nid: self._timestamps.get(nid, 0),
            default=next(iter(data_dict), None),
        )
        if oldest_id:
            data_dict.pop(oldest_id, None)
            self._timestamps.pop(oldest_id, None)

    @staticmethod
    def _extract_note_id_from_url(url: str) -> str:
        """Extract note_id from URL query params (fallback for comments)."""
        try:
            params = parse_qs(urlparse(url).query)
        except Exception:
            return ""
        for key in ("note_id", "aweme_id", "item_id"):
            values = params.get(key)
            if not values:
                continue
            for v in values:
                if v:
                    return str(v)
        return ""

    @staticmethod
    def _merge_comments(existing: list[dict], incoming: list) -> list[dict]:
        """Merge comment batches while avoiding duplicate IDs from retries."""
        merged = [c for c in existing if isinstance(c, dict)]
        seen = {c.get("id") for c in merged if c.get("id")}
        for c in incoming:
            if not isinstance(c, dict):
                continue
            cid = c.get("id")
            if cid and cid in seen:
                continue
            if cid:
                seen.add(cid)
            merged.append(c)
        return merged
