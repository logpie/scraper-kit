"""Session health monitor for web scraping.

Tracks a rolling window of events (ok, captcha, auth_expired, timeout, empty)
and computes a health score. Used by scraping strategies to adaptively increase
delays or hard-stop when the session is dying.
"""
import collections
import time

# Event weights: positive events add, negative events subtract
_WEIGHTS = {
    "ok": 1.0,
    "captcha": -0.5,
    "timeout": -0.3,
    "empty": -0.1,
    "auth_expired": -1.0,
}


class HealthMonitor:
    """Rolling-window health scorer for browser session."""

    def __init__(self, window: int = 20):
        self._events: collections.deque[tuple[float, str]] = collections.deque(maxlen=window)
        self._window = window

    def record(self, event: str):
        """Record an event. Known events: ok, captcha, auth_expired, timeout, empty."""
        self._events.append((time.monotonic(), event))

    @property
    def score(self) -> float:
        """Health score from 0.0 (dead) to 1.0 (healthy).

        Recent events are weighted 2x compared to older ones.
        Score is normalized to [0, 1] range.
        """
        if not self._events:
            return 1.0

        n = len(self._events)
        midpoint = n // 2
        total_weight = 0.0
        total_possible = 0.0

        for i, (_ts, event) in enumerate(self._events):
            recency = 2.0 if i >= midpoint else 1.0
            w = _WEIGHTS.get(event, 0.0)
            total_weight += w * recency
            total_possible += 1.0 * recency  # max possible (all "ok")

        if total_possible == 0:
            return 1.0

        # Normalize: total_weight ranges from -total_possible to +total_possible
        # Map to 0..1
        raw = (total_weight + total_possible) / (2 * total_possible)
        return max(0.0, min(1.0, raw))

    @property
    def should_stop(self) -> bool:
        """True if session is dead — 3+ auth_expired events or score < 0.3."""
        n_auth = sum(1 for _, ev in self._events if ev == "auth_expired")
        if n_auth >= 3:
            return True
        return self.score < 0.3

    @property
    def should_backoff(self) -> bool:
        """True if session is degraded — score < 0.6. Caller should increase delays."""
        return self.score < 0.6

    @property
    def stats(self) -> dict:
        """Return event counts for logging."""
        counts: dict[str, int] = {}
        for _, ev in self._events:
            counts[ev] = counts.get(ev, 0) + 1
        return {"score": round(self.score, 2), "events": counts, "total": len(self._events)}
