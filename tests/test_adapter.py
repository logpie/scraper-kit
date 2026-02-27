"""Tests for SiteAdapter protocol and post schema."""
from scraper_kit.adapter import SiteAdapter, REQUIRED_POST_KEYS, OPTIONAL_POST_KEYS


def test_required_keys():
    assert "note_id" in REQUIRED_POST_KEYS
    assert "url" in REQUIRED_POST_KEYS
    assert "content" in REQUIRED_POST_KEYS
    assert "likes" in REQUIRED_POST_KEYS


def test_optional_keys():
    assert "top_comments" in OPTIONAL_POST_KEYS
    assert "_data_source" in OPTIONAL_POST_KEYS
    assert "card_only" in OPTIONAL_POST_KEYS


class MockAdapter:
    """Minimal mock adapter for testing."""
    name = "mock"
    base_url = "https://example.com"

    def search(self, page, keyword): return f"https://example.com/search?q={keyword}"
    def apply_filters(self, page, sort, time_window): pass
    def extract_cards(self, page): return []
    def open_detail(self, page, card): return True
    def wait_for_detail(self, page, card, timeout=8000): return True
    def extract_detail(self, page, card): return {"content": "test", "likes": "10", "comments": "5"}
    def extract_comments(self, page, max_comments): return []
    def close_detail(self, page, card): pass
    def take_screenshot(self, page, card, screenshot_dir): return ""
    def get_api_routes(self): return {}
    def extract_note_id_from_api(self, data_type, data): return ""
    def has_captcha(self, page): return False
    def dismiss_captcha(self, page): return False
    def has_auth_evidence(self, page): return False
    def ensure_loaded(self, page): pass
    def parse_date_age_days(self, date_str): return None
    def parse_engagement(self, value): return int(value) if value.isdigit() else 0
    def build_post_url(self, note_id): return f"https://example.com/post/{note_id}"
    def get_cdp_args(self): return []
    def get_locale(self): return "en-US"
    def get_session_cookie_name(self): return "session_id"


def test_mock_adapter_is_site_adapter():
    adapter = MockAdapter()
    assert isinstance(adapter, SiteAdapter)


def test_mock_adapter_methods():
    adapter = MockAdapter()
    assert adapter.name == "mock"
    assert adapter.base_url == "https://example.com"
    assert adapter.build_post_url("123") == "https://example.com/post/123"
    assert adapter.parse_engagement("100") == 100
    assert adapter.parse_engagement("abc") == 0
    assert adapter.get_locale() == "en-US"
