"""Orchestrator — entry point for scraper-kit fetch operations.

Requires injected page/context — never auto-opens a browser.
The app layer (e.g. murmur's fetcher/__init__.py) manages browser lifecycle
and calls this with an already-open page.
"""
import logging

from .hybrid import strategy_hybrid

log = logging.getLogger(__name__)


def fetch_posts(adapter, keyword: str, *,
                page, context,
                max_pages: int = 20,
                sort: str = "latest",
                screenshot_dir: str = "",
                max_posts: int = 0,
                max_comments: int = 10,
                seen_data: dict | None = None,
                grind: bool = False,
                max_age_days: int = 99999,
                analysis_window: str = "any",
                strategy: str = "hybrid",
                event_logger=None,
                failure_bundle_verbosity: str = "off") -> list[dict]:
    """Fetch posts using the given adapter and browser session.

    This is the scraper-kit layer entry point. It requires an already-open
    page/context — it never creates a browser session.

    Args:
        adapter: SiteAdapter implementation for the target site.
        keyword: Search keyword.
        page: Playwright page object.
        context: Playwright browser context.
        max_pages: Maximum search result pages to scroll through.
        sort: Sort order (site-specific, e.g. "latest", "general").
        screenshot_dir: Directory for post screenshots.
        max_posts: Maximum posts to fetch (0 = unlimited).
        max_comments: Maximum comments per post.
        seen_data: Persisted seen data dict for dedup.
        grind: When True, only successfully fetched + in-window posts count.
        max_age_days: Maximum post age in days for grind counting.
        analysis_window: Time window label for grind counting.
        strategy: Strategy name ("hybrid" is the default and recommended).
        event_logger: Optional FetchEventLogger for telemetry.

    Returns:
        List of post dicts, each containing at least REQUIRED_POST_KEYS.
    """
    if strategy == "hybrid":
        posts = strategy_hybrid(
            page, context, adapter, keyword, max_pages, sort,
            screenshot_dir, max_posts, max_comments, seen_data,
            grind=grind, max_age_days=max_age_days,
            analysis_window=analysis_window,
            event_logger=event_logger,
            failure_bundle_verbosity=failure_bundle_verbosity,
        )
    else:
        # Other strategies can be added here. For now, hybrid is the
        # generic strategy provided by scraper-kit. Site-specific
        # strategies (e.g. XHS api-first) stay in the adapter.
        log.warning(f"Unknown strategy '{strategy}' for scraper-kit, falling back to hybrid")
        posts = strategy_hybrid(
            page, context, adapter, keyword, max_pages, sort,
            screenshot_dir, max_posts, max_comments, seen_data,
            grind=grind, max_age_days=max_age_days,
            analysis_window=analysis_window,
            event_logger=event_logger,
            failure_bundle_verbosity=failure_bundle_verbosity,
        )

    # Tag all posts with strategy
    for p in posts:
        p.setdefault("_strategy", strategy)

    return posts
