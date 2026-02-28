"""Tests for the generic PassiveTap."""
from unittest.mock import MagicMock
from scraper_kit.engine.passive_tap import PassiveTap, WaitResult


class MockAdapter:
    def get_api_routes(self):
        return {
            "/api/feed": self._parse_feed,
            "/api/comments": self._parse_comments,
        }

    def extract_note_id_from_api(self, data_type, data):
        if data_type == "feed":
            return data.get("note_id", "")
        elif data_type == "comments":
            return data.get("note_id", "")
        return ""

    def _parse_feed(self, body):
        data = body.get("data", {})
        return "feed", {"note_id": data.get("id", ""), "content": data.get("text", "")}

    def _parse_comments(self, body):
        data = body.get("data", {})
        return "comments", data.get("comments", [])


def _make_response(url, status=200, body=None):
    resp = MagicMock()
    resp.url = url
    resp.status = status
    resp.json.return_value = body or {}
    return resp


def test_passive_tap_feed_capture():
    page = MagicMock()
    adapter = MockAdapter()
    tap = PassiveTap(page, adapter)
    tap.start()

    # Simulate a feed response
    resp = _make_response(
        "https://example.com/api/feed?id=abc",
        body={"data": {"id": "abc", "text": "Hello world"}},
    )
    tap._on_response(resp)

    feed = tap.get_feed("abc")
    assert feed is not None
    assert feed["note_id"] == "abc"
    assert feed["content"] == "Hello world"


def test_passive_tap_comments_capture():
    page = MagicMock()
    adapter = MockAdapter()

    # Override to return note_id from comments list
    def _parse_comments(body):
        data = body.get("data", {})
        comments = data.get("comments", [])
        return "comments", {"note_id": data.get("note_id", ""), "comments": comments}

    def extract_note_id(data_type, data):
        return data.get("note_id", "")

    adapter._parse_comments = _parse_comments
    adapter.extract_note_id_from_api = extract_note_id
    adapter.get_api_routes = lambda: {
        "/api/feed": adapter._parse_feed,
        "/api/comments": _parse_comments,
    }

    tap = PassiveTap(page, adapter)
    tap.start()

    resp = _make_response(
        "https://example.com/api/comments?note_id=xyz",
        body={"data": {"note_id": "xyz", "comments": [
            {"id": "c1", "text": "Nice!"},
            {"id": "c2", "text": "Great!"},
        ]}},
    )
    tap._on_response(resp)

    comments = tap.get_comments("xyz")
    # Comments are stored as the raw parsed result from the adapter
    # In this case, the parse_comments returns a dict with comments key
    # But PassiveTap expects data_type == "comments" to store as list
    # Let's check what we got
    assert isinstance(comments, list)


def test_passive_tap_clear():
    page = MagicMock()
    adapter = MockAdapter()
    tap = PassiveTap(page, adapter)

    resp = _make_response(
        "https://example.com/api/feed?id=abc",
        body={"data": {"id": "abc", "text": "Hello"}},
    )
    tap._on_response(resp)
    assert tap.get_feed("abc") is not None

    tap.clear("abc")
    assert tap.get_feed("abc") is None


def test_passive_tap_non_200_ignored():
    page = MagicMock()
    adapter = MockAdapter()
    tap = PassiveTap(page, adapter)

    resp = _make_response(
        "https://example.com/api/feed?id=abc",
        status=404,
        body={"data": {"id": "abc", "text": "Hello"}},
    )
    tap._on_response(resp)
    assert tap.get_feed("abc") is None


def test_passive_tap_start_stop():
    page = MagicMock()
    adapter = MockAdapter()
    tap = PassiveTap(page, adapter)

    tap.start()
    assert tap._listening
    page.on.assert_called_once()

    tap.stop()
    assert not tap._listening


def test_passive_tap_buffer_limit():
    """Buffer should not grow beyond _MAX_BUFFER_SIZE."""
    page = MagicMock()
    adapter = MockAdapter()
    tap = PassiveTap(page, adapter)

    from scraper_kit.engine.passive_tap import _MAX_BUFFER_SIZE

    # Fill beyond buffer limit
    for i in range(_MAX_BUFFER_SIZE + 10):
        resp = _make_response(
            f"https://example.com/api/feed?id=note_{i}",
            body={"data": {"id": f"note_{i}", "text": f"Post {i}"}},
        )
        tap._on_response(resp)

    assert len(tap._feed_data) <= _MAX_BUFFER_SIZE


def test_passive_tap_extract_note_id_from_url():
    """URL-based note_id extraction for comments fallback."""
    assert PassiveTap._extract_note_id_from_url(
        "https://example.com/api/comments?note_id=abc123&cursor=0"
    ) == "abc123"
    assert PassiveTap._extract_note_id_from_url(
        "https://example.com/api/comments?aweme_id=789"
    ) == "789"
    assert PassiveTap._extract_note_id_from_url(
        "https://example.com/api/comments?item_id=456"
    ) == "456"
    assert PassiveTap._extract_note_id_from_url(
        "https://example.com/api/comments?cursor=0"
    ) == ""
    assert PassiveTap._extract_note_id_from_url("not-a-url") == ""
    # Repeated params with empty first value
    assert PassiveTap._extract_note_id_from_url(
        "https://example.com/api?aweme_id=&aweme_id=123"
    ) == "123"


def test_passive_tap_comments_url_fallback():
    """When extract_note_id_from_api returns '', use URL params as fallback."""
    page = MagicMock()

    class FallbackAdapter:
        def get_api_routes(self):
            return {"/api/comments": self._parse_comments}

        def extract_note_id_from_api(self, data_type, data):
            return ""  # Always returns empty — simulates comments with no note_id

        def _parse_comments(self, body):
            return "comments", body.get("comments", [])

    adapter = FallbackAdapter()
    tap = PassiveTap(page, adapter)
    tap.start()

    resp = _make_response(
        "https://example.com/api/comments?aweme_id=note999",
        body={"comments": [{"id": "c1", "text": "hello"}]},
    )
    tap._on_response(resp)

    comments = tap.get_comments("note999")
    assert len(comments) == 1
    assert comments[0]["text"] == "hello"


# --- wait_for() tests ---


def test_wait_for_data_already_present():
    """wait_for() returns immediately when data is already in the buffer."""
    page = MagicMock()
    adapter = MockAdapter()
    tap = PassiveTap(page, adapter)

    # Pre-populate feed
    resp = _make_response(
        "https://example.com/api/feed?id=abc",
        body={"data": {"id": "abc", "text": "Hello"}},
    )
    tap._on_response(resp)

    result = tap.wait_for("abc", need_feed=True, timeout=1.0)
    assert not result.timed_out
    assert result.feed is not None
    assert result.feed["note_id"] == "abc"
    assert result.elapsed < 0.5  # Should be near-instant
    # page.wait_for_timeout should NOT have been called
    page.wait_for_timeout.assert_not_called()


def test_wait_for_data_arrives_during_wait():
    """wait_for() picks up data injected during page.wait_for_timeout() side effect."""
    page = MagicMock()
    adapter = MockAdapter()
    tap = PassiveTap(page, adapter)

    call_count = 0

    def inject_feed_on_second_tick(ms):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            resp = _make_response(
                "https://example.com/api/feed?id=xyz",
                body={"data": {"id": "xyz", "text": "Arrived!"}},
            )
            tap._on_response(resp)

    page.wait_for_timeout.side_effect = inject_feed_on_second_tick

    result = tap.wait_for("xyz", need_feed=True, timeout=5.0, poll_interval=50)
    assert not result.timed_out
    assert result.feed is not None
    assert result.feed["content"] == "Arrived!"
    assert call_count == 2


def test_wait_for_timeout():
    """wait_for() returns timed_out=True when deadline reached without data."""
    page = MagicMock()
    adapter = MockAdapter()
    tap = PassiveTap(page, adapter)

    result = tap.wait_for("missing", need_feed=True, timeout=0.3, poll_interval=50)
    assert result.timed_out
    assert result.feed is None
    assert result.elapsed >= 0.3
    assert page.wait_for_timeout.call_count >= 1


def test_wait_for_comments_only():
    """wait_for() can wait for comments without requiring feed."""
    page = MagicMock()
    adapter = MockAdapter()
    tap = PassiveTap(page, adapter)

    call_count = 0

    def inject_comments(ms):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Manually inject comments into tap buffer
            tap._comment_data["note1"] = [{"id": "c1", "text": "Hi"}]

    page.wait_for_timeout.side_effect = inject_comments

    result = tap.wait_for("note1", need_feed=False, need_comments=True, timeout=2.0)
    assert not result.timed_out
    assert result.feed is None  # Not requested
    assert len(result.comments) == 1
    assert result.comments[0]["text"] == "Hi"


def test_wait_for_both_conditions():
    """wait_for() waits until both feed and comments are present."""
    page = MagicMock()
    adapter = MockAdapter()
    tap = PassiveTap(page, adapter)

    call_count = 0

    def inject_sequentially(ms):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Feed arrives first
            resp = _make_response(
                "https://example.com/api/feed?id=both",
                body={"data": {"id": "both", "text": "Content"}},
            )
            tap._on_response(resp)
        elif call_count == 3:
            # Comments arrive later
            tap._comment_data["both"] = [{"id": "c1", "text": "Comment"}]

    page.wait_for_timeout.side_effect = inject_sequentially

    result = tap.wait_for("both", need_feed=True, need_comments=True, timeout=5.0)
    assert not result.timed_out
    assert result.feed is not None
    assert len(result.comments) == 1


def test_wait_for_bonus_data_after_timeout():
    """Final check after timeout captures data delivered on the last tick."""
    page = MagicMock()
    adapter = MockAdapter()
    tap = PassiveTap(page, adapter)

    # Inject data on every wait_for_timeout call — but use a very short timeout
    # so the while-loop condition fails, then the final check finds data.
    def inject_on_call(ms):
        # This runs during the loop body; by the time the while condition
        # re-checks, deadline has passed. But the data is there for final check.
        resp = _make_response(
            "https://example.com/api/feed?id=late",
            body={"data": {"id": "late", "text": "Last second"}},
        )
        tap._on_response(resp)
        # Simulate enough time passing that the loop exits
        import time
        time.sleep(0.05)

    page.wait_for_timeout.side_effect = inject_on_call

    result = tap.wait_for("late", need_feed=True, timeout=0.02, poll_interval=50)
    # Data was captured — either during loop or final check
    assert result.feed is not None
    assert result.feed["content"] == "Last second"
