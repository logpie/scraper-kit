"""scraper-kit — reusable web scraping framework with adapter-based multi-site support.

Provides browser automation primitives, human-like behavior simulation,
structured event logging, health monitoring, and a site-adapter protocol
for building multi-site scrapers.
"""
from .adapter import SiteAdapter, REQUIRED_POST_KEYS, OPTIONAL_POST_KEYS  # noqa: F401
from .engine.errors import ScraperSignal, ScraperError  # noqa: F401
from .engine.orchestrator import fetch_posts  # noqa: F401
