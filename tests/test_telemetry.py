"""Tests for FetchEventLogger — telemetry contract tests."""
import json
import os
import tempfile

from scraper_kit.telemetry.logger import FetchEventLogger


def test_basic_event_logging():
    """Events are written to JSONL with correct fields."""
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = FetchEventLogger("run123", "test_keyword", log_dir=tmpdir)
        logger.log_search_start("test_keyword", False, "hybrid", {"max_posts": 10})
        logger.close()

        files = os.listdir(tmpdir)
        assert len(files) == 1
        assert files[0].endswith(".jsonl")

        with open(os.path.join(tmpdir, files[0])) as f:
            lines = f.readlines()
        assert len(lines) == 1

        event = json.loads(lines[0])
        assert event["event"] == "search_start"
        assert event["run_id"] == "run123"
        assert event["keyword"] == "test_keyword"
        assert "ts" in event
        assert event["search_term"] == "test_keyword"
        assert event["strategy"] == "hybrid"


def test_site_field_included_when_provided():
    """When site is provided, it appears in every event."""
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = FetchEventLogger("run456", "kw", log_dir=tmpdir, site="douyin")
        logger.log_search_start("kw", False, "hybrid", {})
        logger.close()

        files = os.listdir(tmpdir)
        with open(os.path.join(tmpdir, files[0])) as f:
            event = json.loads(f.readline())
        assert event["site"] == "douyin"


def test_site_field_omitted_when_not_provided():
    """Backward compat: no site field when not provided."""
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = FetchEventLogger("run789", "kw", log_dir=tmpdir)
        logger.log_search_start("kw", False, "hybrid", {})
        logger.close()

        files = os.listdir(tmpdir)
        with open(os.path.join(tmpdir, files[0])) as f:
            event = json.loads(f.readline())
        assert "site" not in event


def test_context_manager():
    """FetchEventLogger works as context manager."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with FetchEventLogger("run_cm", "kw", log_dir=tmpdir) as logger:
            logger.log_search_start("kw", False, "hybrid", {})
        # File should be closed
        files = os.listdir(tmpdir)
        assert len(files) == 1


def test_golden_roundtrip():
    """Golden JSONL roundtrip: write events, read back, verify structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with FetchEventLogger("golden", "test", log_dir=tmpdir, site="xhs") as logger:
            logger.set_search_term("test")
            logger.log_search_start("test", False, "hybrid", {"max_posts": 5})
            logger.log_card_attempt(
                note_id="abc123", title="Test Post", card_index=0, page_num=1,
                cards_on_page=10, cards_new=8, cards_skipped=2,
                health_score=0.95, consecutive_failures=0, captcha_mode=False,
            )
            logger.log_card_result(
                note_id="abc123", data_source="passive_api", content_len=500,
                comments_count=3, has_images=True, has_video=False,
                captcha=False, card_only=False, card_only_reason=None,
                health_score=0.95, health_event="ok",
                delay_used=1.5, fetch_duration=2.3,
                elapsed_run=10.0, post_index=1,
                consecutive_failures=0,
            )
            logger.log_search_end(
                search_term="test", stop_reason="max_posts",
                pages_scrolled=2, fetched=5, skipped=2, card_only=0, failed=0,
                passive_api_count=5, dom_fallback_count=0,
                health_final=0.95, health_events={"ok": 5}, duration=30.0,
            )
            logger.log_run_end(
                search_terms=["test"], total_fetched=5, total_skipped=2,
                total_failed=0, total_analyzed=5, total_seen=2,
                duration=35.0, git="abc1234", status="ok",
            )

        files = os.listdir(tmpdir)
        with open(os.path.join(tmpdir, files[0])) as f:
            events = [json.loads(line) for line in f]

        assert len(events) == 5
        event_types = [e["event"] for e in events]
        assert event_types == [
            "search_start", "card_attempt", "card_result", "search_end", "run_end",
        ]

        # All events have site field
        for e in events:
            assert e["site"] == "xhs"
            assert "ts" in e
            assert "run_id" in e
