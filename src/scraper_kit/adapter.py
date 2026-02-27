"""SiteAdapter Protocol — minimal interface each site adapter must implement.

Methods, not config dicts — each adapter owns its DOM interaction fully.
The framework calls these methods; it never touches site-specific selectors
or URLs directly.
"""
from typing import Any, Callable, Protocol, runtime_checkable


@runtime_checkable
class SiteAdapter(Protocol):
    """Protocol that site adapters must implement.

    Each site (XHS, Douyin, Weibo, etc.) provides a concrete class
    implementing this interface. The framework engine calls these methods
    to drive scraping without any site-specific knowledge.
    """

    name: str           # "xhs", "douyin"
    base_url: str       # "https://www.xiaohongshu.com"

    # ── Search ──────────────────────────────────────────────────────────────

    def search(self, page: Any, keyword: str) -> str:
        """Navigate to search results for keyword. Returns the search URL."""
        ...

    def apply_filters(self, page: Any, sort: str, time_window: str) -> None:
        """Apply sort/time filters on the search results page."""
        ...

    # ── Card extraction ─────────────────────────────────────────────────────

    def extract_cards(self, page: Any) -> list[dict]:
        """Extract search result cards from the current page.

        Each card dict must include at least 'note_id' (unique post identifier).
        """
        ...

    # ── Detail fetch ────────────────────────────────────────────────────────
    # Modal or page navigation — adapter decides the approach.

    def open_detail(self, page: Any, card: dict) -> bool:
        """Open the detail view for a card. Returns True if successful.

        For modal-based sites (XHS): clicks the card to open an overlay.
        For navigation-based sites (Douyin): navigates to the video page.
        """
        ...

    def wait_for_detail(self, page: Any, card: dict, timeout: int = 8000) -> bool:
        """Wait for detail content to become visible. Returns True if loaded."""
        ...

    def extract_detail(self, page: Any, card: dict) -> dict:
        """Extract post data from the detail view.

        Must return a dict containing at least REQUIRED_POST_KEYS.
        """
        ...

    def extract_comments(self, page: Any, max_comments: int) -> list[dict]:
        """Extract comments from the detail view."""
        ...

    def close_detail(self, page: Any, card: dict) -> None:
        """Close the detail view and restore the page to search results.

        Contract: after close_detail(), extract_cards() must work again
        (search results visible, scroll position preserved or recoverable).
        For modals: dismiss the overlay.
        For navigation: page.go_back() + wait for search results.
        """
        ...

    def take_screenshot(self, page: Any, card: dict, screenshot_dir: str) -> str:
        """Take a screenshot of the detail view. Returns the file path."""
        ...

    # ── API interception (PassiveTap) ───────────────────────────────────────

    def get_api_routes(self) -> dict[str, Callable]:
        """Return URL pattern -> parser mapping for passive API interception.

        Keys are URL substrings to match against response URLs.
        Values are callables: (response_body: dict) -> (data_type: str, parsed_data: Any)
        where data_type is "feed" or "comments".
        """
        ...

    def extract_note_id_from_api(self, data_type: str, data: Any) -> str:
        """Extract the note_id from a parsed API response.

        data_type is the string returned by the route parser (e.g. "feed", "comments").
        data is the parsed data returned by the route parser.
        """
        ...

    # ── Auth / anti-bot ─────────────────────────────────────────────────────

    def has_captcha(self, page: Any) -> bool:
        """Check if a CAPTCHA/bot-detection wall is present."""
        ...

    def dismiss_captcha(self, page: Any) -> bool:
        """Try to dismiss the CAPTCHA. Returns True if successful."""
        ...

    def has_auth_evidence(self, page: Any) -> bool:
        """Check if the page shows auth/login evidence (session expired)."""
        ...

    def ensure_loaded(self, page: Any) -> None:
        """Ensure the site is loaded and ready (e.g. navigate to homepage)."""
        ...

    # ── Content parsing ─────────────────────────────────────────────────────

    def parse_date_age_days(self, date_str: str) -> int | None:
        """Parse a site-specific date string and return age in days.

        Returns None if unparseable.
        """
        ...

    def parse_engagement(self, value: str) -> int:
        """Parse a site-specific engagement string (likes, comments) to int.

        Handles locale-specific formatting (e.g. '1.2万' -> 12000).
        """
        ...

    def build_post_url(self, note_id: str) -> str:
        """Build a canonical post URL from a note_id."""
        ...

    # ── Browser config ──────────────────────────────────────────────────────

    def get_cdp_args(self) -> list[str]:
        """Return extra CDP arguments for browser launch."""
        ...

    def get_locale(self) -> str:
        """Return the locale for the browser context (e.g. 'zh-CN')."""
        ...

    def get_session_cookie_name(self) -> str:
        """Return the name of the session cookie to monitor for expiry."""
        ...


# ── Post Schema ─────────────────────────────────────────────────────────────

REQUIRED_POST_KEYS = {
    "note_id",      # unique post identifier
    "url",          # canonical post URL
    "title",        # post title (may be empty)
    "content",      # post body text
    "user",         # author name
    "likes",        # engagement count (string)
    "comments",     # engagement count (string)
    "date",         # display date string (site-specific format)
}

OPTIONAL_POST_KEYS = {
    "collects", "shares", "tags", "cover_url", "video_url",
    "image_urls", "top_comments", "screenshot",
    "card_only", "card_only_reason",    # failure markers
    "_data_source",                      # passive_api/dom_fallback/card_only
    "_seen", "_fresh", "_trending",      # filtering tags (set by app layer)
    "search_keyword",                    # which search term found this
}
