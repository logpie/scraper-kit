"""Card filtering: dedup within session + smart skip for seen posts."""
import logging

from .seen_set import should_refetch

log = logging.getLogger(__name__)


def filter_cards(card_infos: list[dict], session_seen: set,
                 seen_data: dict | None, parse_engagement) -> tuple[list, list, int]:
    """Filter cards: dedup within session + smart skip for seen posts.

    Args:
        card_infos: List of card dicts from adapter.extract_cards().
        session_seen: Set of note_ids already processed in this session.
        seen_data: Persisted seen data dict, or None to skip seen-check.
        parse_engagement: Callable to parse engagement strings
            (adapter.parse_engagement).

    Returns (fetch_cards, skipped_cards, n_skipped).
    Seen posts are returned in skipped_cards so they can appear in reports.
    """
    fetch_cards = []
    skipped_cards = []
    n_skipped = 0
    for c in card_infos:
        nid = c.get("note_id")
        if not nid or nid in session_seen:
            continue
        if seen_data is not None:
            do_fetch, is_trending = should_refetch(c, seen_data, parse_engagement)
            c["_trending"] = is_trending
            if not do_fetch:
                session_seen.add(nid)
                c["_skip_detail"] = True
                skipped_cards.append(c)
                n_skipped += 1
                continue
        fetch_cards.append(c)
    return fetch_cards, skipped_cards, n_skipped
