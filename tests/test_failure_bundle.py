"""Tests for failure bundle capture and save."""
import json
import os
import tempfile
from unittest.mock import MagicMock, PropertyMock

from scraper_kit.engine.failure_bundle import (
    BundleVerbosity,
    FailureBundle,
    capture_failure_bundle,
    save_failure_bundle,
)


def _make_page(url="https://example.com/post/123", title="Test Post"):
    page = MagicMock()
    type(page).url = PropertyMock(return_value=url)
    page.title.return_value = title
    page.evaluate.return_value = "Page body text content here"
    return page


def _make_tap(has_feed=False, has_comments=False):
    tap = MagicMock()
    tap.get_feed.return_value = {"note_id": "abc", "content": "hello"} if has_feed else None
    tap.get_comments.return_value = [{"id": "c1"}] if has_comments else []
    return tap


def _make_adapter(site_name="douyin"):
    adapter = MagicMock()
    adapter.SITE_NAME = site_name
    # No get_failure_diagnostics by default
    del adapter.get_failure_diagnostics
    return adapter


def test_capture_minimal():
    """MINIMAL verbosity captures only tap state + timing."""
    page = _make_page()
    tap = _make_tap(has_feed=True, has_comments=False)
    adapter = _make_adapter()

    bundle = capture_failure_bundle(
        page, tap, adapter, "note1", "empty_content",
        keyword="test", verbosity=BundleVerbosity.MINIMAL,
    )

    assert bundle.note_id == "note1"
    assert bundle.reason == "empty_content"
    assert bundle.site == "douyin"
    assert bundle.keyword == "test"
    assert bundle.tap_has_feed is True
    assert bundle.tap_has_comments is False
    assert "note_id" in bundle.tap_feed_keys
    # MINIMAL should NOT access page URL/title/text
    page.title.assert_not_called()
    page.evaluate.assert_not_called()


def test_capture_standard():
    """STANDARD verbosity captures page URL, title, and text snippet."""
    page = _make_page()
    tap = _make_tap()
    adapter = _make_adapter()

    bundle = capture_failure_bundle(
        page, tap, adapter, "note2", "modal_timeout",
        verbosity=BundleVerbosity.STANDARD,
    )

    assert bundle.page_url == "https://example.com/post/123"
    assert bundle.page_title == "Test Post"
    assert bundle.page_text_snippet == "Page body text content here"


def test_capture_full_with_screenshot():
    """FULL verbosity takes a screenshot."""
    page = _make_page()
    tap = _make_tap()
    adapter = _make_adapter()

    with tempfile.TemporaryDirectory() as tmpdir:
        bundle = capture_failure_bundle(
            page, tap, adapter, "note3", "link_not_found",
            verbosity=BundleVerbosity.FULL,
            screenshot_dir=tmpdir,
        )
        # Screenshot method was called
        page.screenshot.assert_called_once()
        assert bundle.screenshot_path.endswith(".png")


def test_capture_never_raises():
    """capture_failure_bundle should never raise, even with broken page/tap."""
    page = MagicMock()
    type(page).url = PropertyMock(side_effect=RuntimeError("detached"))
    page.title.side_effect = RuntimeError("detached")
    page.evaluate.side_effect = RuntimeError("detached")

    tap = MagicMock()
    tap.get_feed.side_effect = RuntimeError("broken")
    tap.get_comments.side_effect = RuntimeError("broken")

    adapter = _make_adapter()

    # Should not raise
    bundle = capture_failure_bundle(
        page, tap, adapter, "broken_note", "exception",
        verbosity=BundleVerbosity.FULL,
    )
    assert bundle.note_id == "broken_note"
    assert bundle.reason == "exception"


def test_save_and_load():
    """save_failure_bundle writes valid JSON."""
    bundle = FailureBundle(
        note_id="save_test",
        reason="empty_content",
        site="xhs",
        keyword="test_kw",
        tap_has_feed=True,
        tap_comment_count=3,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        path = save_failure_bundle(bundle, base_dir=tmpdir)
        assert path.endswith(".json")
        assert os.path.exists(path)

        with open(path) as f:
            data = json.load(f)

        assert data["note_id"] == "save_test"
        assert data["reason"] == "empty_content"
        assert data["site"] == "xhs"
        assert data["keyword"] == "test_kw"
        assert data["tap_has_feed"] is True
        assert data["tap_comment_count"] == 3
        assert "timestamp" in data


def test_to_dict():
    """to_dict() returns a plain dict with all fields."""
    bundle = FailureBundle(
        note_id="dict_test", reason="timeout",
        site="douyin", keyword="kw",
    )
    d = bundle.to_dict()
    assert isinstance(d, dict)
    assert d["note_id"] == "dict_test"
    assert d["reason"] == "timeout"
    assert "phase_timings" in d
    assert "adapter_extras" in d


def test_adapter_extras_duck_typing():
    """Adapter with get_failure_diagnostics() gets extras captured."""
    page = _make_page()
    tap = _make_tap()
    adapter = _make_adapter()
    # Add the optional method
    adapter.get_failure_diagnostics = MagicMock(
        return_value={"video_state": "paused", "player_error": None}
    )

    bundle = capture_failure_bundle(
        page, tap, adapter, "note_extras", "empty_content",
        verbosity=BundleVerbosity.MINIMAL,
    )

    assert bundle.adapter_extras["video_state"] == "paused"
    adapter.get_failure_diagnostics.assert_called_once_with(page, "note_extras")
