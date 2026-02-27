"""Normalized error signals for scraping engines.

Adapters map site-specific exceptions into these signals so the engine's
retry/backoff/health logic works uniformly across sites.
"""
from enum import Enum


class ScraperSignal(Enum):
    """Normalized error signals that adapters must map site-specific exceptions into."""
    CAPTCHA = "captcha"           # bot detection wall
    AUTH_EXPIRED = "auth_expired" # session/login invalid
    RATE_LIMITED = "rate_limited" # too many requests
    TRANSIENT = "transient"       # temporary failure, worth retrying
    FATAL = "fatal"               # unrecoverable, bail out


class ScraperError(Exception):
    """Exception carrying a normalized ScraperSignal for engine error handling."""

    def __init__(self, signal: ScraperSignal, message: str = ""):
        self.signal = signal
        super().__init__(message or signal.value)
