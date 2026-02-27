"""Tests for filtering modules: seen_set, card_filter, counting."""
import json
import os
import tempfile

from scraper_kit.filtering.seen_set import load_seen, save_seen, should_refetch
from scraper_kit.filtering.card_filter import filter_cards
from scraper_kit.filtering.counting import fetch_count, grind_count, count_for_limit


def _parse_engagement(value):
    """Simple engagement parser for tests."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def test_load_seen_missing_file():
    assert load_seen("/nonexistent/path.json") == {}


def test_load_save_seen_roundtrip():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "seen.json")
        data = {"abc": {"likes": 10, "comments": 5, "ts": "2026-01-01"}}
        save_seen(path, data)

        loaded = load_seen(path)
        assert loaded["abc"]["likes"] == 10
        assert loaded["abc"]["comments"] == 5


def test_load_seen_old_list_format():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "seen.json")
        with open(path, "w") as f:
            json.dump(["id1", "id2", "id3"], f)

        loaded = load_seen(path)
        assert "id1" in loaded
        assert loaded["id1"]["likes"] == 0


def test_should_refetch_unseen():
    card = {"note_id": "new_id", "likes_from_card": "100"}
    seen_data = {}
    should, trending = should_refetch(card, seen_data, _parse_engagement)
    assert should is True
    assert trending is False


def test_should_refetch_unchanged():
    card = {"note_id": "old_id", "likes_from_card": "100"}
    seen_data = {"old_id": {"likes": 100, "comments": 10}}
    should, trending = should_refetch(card, seen_data, _parse_engagement)
    assert should is False
    assert trending is False


def test_should_refetch_trending():
    card = {"note_id": "old_id", "likes_from_card": "500"}
    seen_data = {"old_id": {"likes": 100, "comments": 10}}
    should, trending = should_refetch(card, seen_data, _parse_engagement)
    assert should is True
    assert trending is True


def test_filter_cards_dedup():
    cards = [
        {"note_id": "a", "title": "Post A"},
        {"note_id": "b", "title": "Post B"},
    ]
    session_seen = {"a"}
    fetch, skipped, n_skipped = filter_cards(cards, session_seen, None, _parse_engagement)
    assert len(fetch) == 1
    assert fetch[0]["note_id"] == "b"
    assert n_skipped == 0


def test_filter_cards_with_seen_data():
    cards = [
        {"note_id": "a", "likes_from_card": "10"},
        {"note_id": "b", "likes_from_card": "20"},
    ]
    seen_data = {"a": {"likes": 10, "comments": 5}}
    session_seen = set()

    fetch, skipped, n_skipped = filter_cards(cards, session_seen, seen_data, _parse_engagement)
    assert len(fetch) == 1  # "a" skipped (unchanged), "b" fetched (unseen)
    assert fetch[0]["note_id"] == "b"
    assert len(skipped) == 1
    assert skipped[0]["note_id"] == "a"
    assert n_skipped == 1


def test_fetch_count():
    posts = [
        {"note_id": "1"},
        {"note_id": "2", "card_only": True, "card_only_reason": "seen"},
        {"note_id": "3", "card_only": True, "card_only_reason": "captcha"},
        {"note_id": "4"},
    ]
    assert fetch_count(posts) == 3  # 1, 3, 4 (skipped "seen" excluded)


def test_grind_count():
    import time as _time
    now = _time.time()
    posts = [
        {"note_id": "1", "time": now * 1000},  # recent, in milliseconds
        {"note_id": "2", "time": (now - 86400 * 10) * 1000},  # 10 days ago
        {"note_id": "3", "card_only": True},  # card-only excluded
        {"note_id": "4", "time": 0},  # unknown -> benefit of doubt
    ]
    assert grind_count(posts, 7) == 2  # 1 (recent) + 4 (unknown)


def test_count_for_limit():
    posts = [
        {"note_id": "1"},
        {"note_id": "2", "card_only": True, "card_only_reason": "seen"},
    ]
    assert count_for_limit(posts, grind=False, max_age_days=99999) == 1
