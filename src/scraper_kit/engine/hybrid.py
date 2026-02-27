"""Generic hybrid strategy: UI-driven detail fetch + passive API interception.

Adapter calls replace all site-specific interactions. This module never touches
site-specific selectors, URLs, or API endpoints — all of that comes through
the adapter protocol.

Requires injected page/context — never opens a browser.
"""
import logging
import os
import time

from ..human.behavior import human_click, human_sleep, human_scroll, scroll_count
from ..filtering.card_filter import filter_cards
from ..filtering.counting import fetch_count, count_for_limit, SKIP_REASONS
from .passive_tap import PassiveTap
from .health import HealthMonitor

log = logging.getLogger(__name__)


def build_post_from_card(card: dict, adapter) -> dict:
    """Build a post dict from card info only (fallback when detail fails)."""
    return {
        "note_id": card.get("note_id", ""),
        "url": card.get("url") or adapter.build_post_url(card.get("note_id", "")),
        "title": card.get("title") or "",
        "content": "",
        "user": card.get("user") or "",
        "likes": card.get("likes_from_card", "0"),
        "comments": "0",
        "date": card.get("time_text", ""),
        "top_comments": [],
    }


def _fetch_post_detail_hybrid(page, card, tap, adapter, screenshot_dir,
                               max_comments=10, search_url=""):
    """Open detail → capture passive API data → DOM fallback → close detail.

    Returns (post_dict, is_captcha).
    Uses PassiveTap to intercept API responses the site's own JS fires,
    then falls back to adapter DOM extraction for missing fields.
    """
    note_id = card["note_id"]
    tap.clear(note_id)
    captcha = False

    try:
        # Open detail via adapter
        if not adapter.open_detail(page, card):
            post = build_post_from_card(card, adapter)
            post["card_only"] = True
            post["card_only_reason"] = "link_not_found"
            return post, False

        human_sleep(1.5, 3.0)  # wait for detail + API calls to fire

        # Dismiss CAPTCHA if present
        if adapter.has_captcha(page):
            log.info(f"    CAPTCHA popup for {note_id}, dismissing...")
            adapter.dismiss_captcha(page)
            human_sleep(1.0, 2.0)
            captcha = adapter.has_captcha(page)

        # Wait for detail content
        detail_loaded = adapter.wait_for_detail(page, card, timeout=8000)
        if not detail_loaded:
            log.warning(f"    Detail content did not appear for {note_id}")

        human_sleep(0.5, 1.0)

        # --- Passive API data ---
        feed = tap.get_feed(note_id)
        api_comments = tap.get_comments(note_id)
        if not feed and not api_comments:
            deadline = time.monotonic() + 1.2
            while time.monotonic() < deadline:
                time.sleep(0.1)
                feed = tap.get_feed(note_id)
                api_comments = tap.get_comments(note_id)
                if feed or api_comments:
                    break
        if feed and not api_comments:
            deadline = time.monotonic() + 0.8
            while time.monotonic() < deadline and not api_comments:
                time.sleep(0.1)
                api_comments = tap.get_comments(note_id)

        # --- DOM extraction as fallback ---
        dom_data = adapter.extract_detail(page, card)
        dom_comments = (
            adapter.extract_comments(page, max_comments=max_comments)
            if not api_comments else []
        )

        # Screenshot
        screenshot_path = adapter.take_screenshot(page, card, screenshot_dir)

        # Close detail
        adapter.close_detail(page, card)

        # --- Merge: API data wins for structured fields ---
        if feed:
            post = dict(feed)
            if not post.get("content") and dom_data.get("content"):
                post["content"] = dom_data["content"]
            post["top_comments"] = (api_comments or dom_comments)[:max_comments]
            if not post.get("cover_url"):
                post["screenshot"] = screenshot_path
            # Prefer DOM engagement data if API returned "0"
            for field in ("likes", "comments", "collects"):
                if post.get(field) in ("0", "", None) and dom_data.get(field):
                    post[field] = dom_data[field]
            post["_data_source"] = "passive_api"
            log.info(f"    {note_id}: passive API data ({len(post.get('content', ''))} chars, "
                     f"{len(api_comments)} comments)")
        else:
            # Pure DOM fallback
            post = {
                "note_id": note_id,
                "url": card.get("url") or adapter.build_post_url(note_id),
                "title": card.get("title") or dom_data.get("title", ""),
                "content": dom_data.get("content", ""),
                "user": card.get("user") or dom_data.get("user", ""),
                "likes": dom_data.get("likes") or card.get("likes_from_card", "0"),
                "comments": dom_data.get("comments", "0"),
                "collects": dom_data.get("collects", "0"),
                "tags": dom_data.get("tags", []),
                "date": dom_data.get("date") or card.get("time_text", ""),
                "top_comments": (api_comments or dom_comments)[:max_comments],
                "screenshot": screenshot_path,
                "video_url": dom_data.get("video_url", ""),
            }
            post["_data_source"] = "dom_fallback"
            content = post["content"]
            if not content:
                post["card_only"] = True
                post["card_only_reason"] = "empty_content" if detail_loaded else "modal_timeout"
            log.info(f"    {note_id}: DOM fallback ({len(content)} chars)")

        return post, captcha

    except Exception as e:
        captcha = adapter.has_captcha(page)
        log.warning(f"    Hybrid detail failed for {note_id}: {e}")
        try:
            adapter.close_detail(page, card)
        except Exception:
            pass
        if search_url:
            try:
                page.goto(search_url, wait_until="networkidle", timeout=30000)
                human_sleep(3, 5)
            except Exception:
                pass
        post = build_post_from_card(card, adapter)
        post["card_only"] = True
        reason = "" if captcha else ("modal_timeout" if "Timeout" in str(e) else "empty_content")
        post["card_only_reason"] = reason
        return post, captcha


def strategy_hybrid(page, context, adapter, keyword, max_pages, sort,
                    screenshot_dir, max_posts, max_comments, seen_data,
                    grind=False, max_age_days=99999, analysis_window="any",
                    event_logger=None):
    """Generic hybrid strategy: UI-driven clicks + passive API response interception.

    Adapter provides all site-specific interactions. The engine handles:
    - Page loop with scroll pagination
    - Card filtering and dedup
    - Health monitoring and adaptive delays
    - Telemetry event logging
    """
    if grind:
        max_pages = max_pages * 3

    tap = PassiveTap(page, adapter)
    health = HealthMonitor()
    all_posts = []
    session_seen = set()
    n_skipped = 0
    empty_pages = 0
    captcha_mode = False
    consecutive_captchas = 0
    consecutive_failures = 0
    n_card_only = 0
    stop_reason = "max_pages"

    log.info(f"  Hybrid strategy: searching for '{keyword}'...")
    tap.start()

    # Telemetry tracking
    _search_start_time = time.time()
    _post_index = 0
    _source_passive_api_count = 0
    _source_dom_fallback_count = 0
    _source_card_only_count = 0
    _n_failed = 0
    _health_events = {}
    page_num = -1

    if event_logger:
        event_logger.set_search_term(keyword)

    try:
        search_url = adapter.search(page, keyword)
        adapter.apply_filters(page, sort, analysis_window)

        for page_num in range(max_pages):
            if health.should_stop:
                stop_reason = "health_stop"
                log.warning(f"  Health monitor: should_stop triggered (score={health.score:.2f}), "
                            f"stopping after {len(all_posts)} posts")
                break

            card_infos = adapter.extract_cards(page)
            fetch_cards, seen_cards, skipped = filter_cards(
                card_infos, session_seen, seen_data, adapter.parse_engagement,
            )
            n_skipped += skipped

            if event_logger and skipped > 0:
                event_logger.log_cards_skipped(
                    search_term=keyword, page_num=page_num,
                    count=skipped, reason="seen",
                )

            for sc in seen_cards:
                post = build_post_from_card(sc, adapter)
                post["card_only"] = True
                post["card_only_reason"] = "seen"
                all_posts.append(post)

            if not fetch_cards:
                empty_pages += 1
                if empty_pages >= 2:
                    stop_reason = "empty_pages"
                    break
                if page_num < max_pages - 1:
                    for _ in range(scroll_count()):
                        human_scroll(page, 3000)
                        human_sleep(0.5, 1.0)
                    human_sleep(2, 4)
                continue

            empty_pages = 0
            for i, card in enumerate(fetch_cards):
                if max_posts:
                    n = count_for_limit(all_posts, grind, max_age_days)
                    if n >= max_posts:
                        stop_reason = "max_posts"
                        break

                if health.should_stop:
                    stop_reason = "health_stop"
                    log.warning(f"  Health hard-stop mid-page")
                    break

                trending_label = " [TRENDING]" if card.get("_trending") else ""

                if event_logger:
                    event_logger.log_card_attempt(
                        note_id=card.get("note_id", ""),
                        title=card.get("title", "")[:80],
                        card_index=i,
                        page_num=page_num,
                        cards_on_page=len(card_infos),
                        cards_new=len(fetch_cards),
                        cards_skipped=skipped,
                        health_score=round(health.score, 2),
                        consecutive_failures=consecutive_failures,
                        captcha_mode=captcha_mode,
                    )

                _card_start = time.time()
                _card_elapsed = 0.0
                _health_event = "skip"

                if captcha_mode or card.get("_skip_detail"):
                    post = build_post_from_card(card, adapter)
                    post["card_only"] = True
                    post["card_only_reason"] = "skipped" if card.get("_skip_detail") else "captcha"
                    n_card_only += 1
                    if captcha_mode and not card.get("_skip_detail"):
                        consecutive_failures += 1
                        health.record("captcha")
                        _health_event = "captcha"
                        _n_failed += 1
                    log.info(f"  [{i+1}/{len(fetch_cards)}]{trending_label} "
                             f"{card.get('title', '')[:40]} [skipped]")
                    _card_elapsed = time.time() - _card_start
                else:
                    post, is_captcha = _fetch_post_detail_hybrid(
                        page, card, tap, adapter, screenshot_dir,
                        max_comments, search_url,
                    )
                    _card_elapsed = time.time() - _card_start
                    if is_captcha:
                        consecutive_captchas += 1
                        consecutive_failures += 1
                        health.record("captcha")
                        _health_event = "captcha"
                        _n_failed += 1
                        if post:
                            post["card_only"] = True
                            post["card_only_reason"] = "captcha"
                            n_card_only += 1
                        if consecutive_captchas >= 2:
                            captcha_mode = True
                    elif post and not post.get("content") and \
                            post.get("_data_source") != "passive_api":
                        fail_reason = post.pop("_card_only_reason", None) or post.get("card_only_reason") or "empty_content"
                        instant_ui_fail = (
                            round(_card_elapsed, 1) == 0.0
                            and fail_reason in {"link_not_found", "modal_timeout"}
                        )
                        post["card_only"] = True
                        post["card_only_reason"] = fail_reason
                        n_card_only += 1
                        consecutive_captchas = 0

                        if instant_ui_fail:
                            health.record("empty")
                            _health_event = "empty"
                            log.warning(f"    Instant card failure ({fail_reason}) for {card.get('note_id', '')}; recovering")
                            if search_url:
                                try:
                                    page.goto(search_url, wait_until="networkidle", timeout=30000)
                                    human_sleep(2, 4)
                                except Exception as rec_err:
                                    log.warning(f"    Recovery navigation failed: {rec_err}")
                        else:
                            consecutive_failures += 1
                            health.record("empty")
                            _health_event = "empty"
                            _n_failed += 1
                    else:
                        consecutive_captchas = 0
                        consecutive_failures = 0
                        health.record("ok")
                        _health_event = "ok"

                    log.info(f"  [{i+1}/{len(fetch_cards)}]{trending_label} "
                             f"{card.get('title', '')[:40]} "
                             f"[health={health.score:.2f}]")

                if consecutive_failures >= 5:
                    if adapter.has_auth_evidence(page):
                        health.record("auth_expired")
                        log.warning("  5 consecutive failures with auth evidence — recording auth_expired")
                    else:
                        health.record("empty")
                        log.warning("  5 consecutive failures without auth evidence — recording empty")

                if post:
                    if card.get("_trending"):
                        post["trending"] = True
                    all_posts.append(post)
                    nid = post.get("note_id")
                    if nid:
                        session_seen.add(nid)

                    # Track source buckets for telemetry
                    _ds = post.get("_data_source", "")
                    _is_card_only = bool(post.get("card_only"))
                    _reason = post.get("card_only_reason")
                    _is_skip_only = _is_card_only and _reason in SKIP_REASONS
                    if not _is_skip_only:
                        if _is_card_only:
                            _source_card_only_count += 1
                        elif _ds == "passive_api":
                            _source_passive_api_count += 1
                        else:
                            _source_dom_fallback_count += 1
                    _post_index += 1

                _health_events[_health_event] = _health_events.get(_health_event, 0) + 1

                # Adaptive delay
                _delay_start = time.monotonic()
                if health.should_backoff:
                    human_sleep(4, 8)
                else:
                    human_sleep(2, 5)
                _delay_used = round(time.monotonic() - _delay_start, 1)

                # Log card result
                if event_logger and post:
                    event_logger.log_card_result(
                        note_id=post.get("note_id", ""),
                        data_source=(
                            "card_only" if post.get("card_only")
                            else post.get("_data_source", "dom_fallback")
                        ),
                        content_len=len(post.get("content") or ""),
                        comments_count=len(post.get("top_comments") or []),
                        has_images=bool(post.get("cover_url") or post.get("image_list")),
                        has_video=bool(post.get("video_url")),
                        captcha=bool(post.get("card_only_reason") == "captcha"),
                        card_only=bool(post.get("card_only")),
                        card_only_reason=post.get("card_only_reason"),
                        health_score=round(health.score, 2),
                        health_event=_health_event,
                        delay_used=_delay_used,
                        fetch_duration=round(_card_elapsed, 1),
                        elapsed_run=round(time.time() - _search_start_time, 1),
                        post_index=_post_index,
                        consecutive_failures=consecutive_failures,
                    )

            # Scroll for next page
            if page_num < max_pages - 1:
                for _ in range(scroll_count()):
                    human_scroll(page, 3000)
                    human_sleep(0.5, 1.0)
                human_sleep(2, 4)

    finally:
        tap.stop()

        n_fetched = fetch_count(all_posts)
        if event_logger:
            event_logger.log_search_end(
                search_term=keyword,
                stop_reason=stop_reason,
                pages_scrolled=page_num + 1 if max_pages > 0 else 0,
                fetched=n_fetched,
                skipped=n_skipped,
                card_only=_source_card_only_count,
                failed=_n_failed,
                passive_api_count=_source_passive_api_count,
                dom_fallback_count=_source_dom_fallback_count,
                health_final=round(health.score, 2),
                health_events=_health_events,
                duration=round(time.time() - _search_start_time, 1),
            )

    n_fetched = fetch_count(all_posts)
    log.info(f"  Hybrid strategy done: {n_fetched} fetched, {n_skipped} skipped, "
             f"{n_card_only} card-only, stop={stop_reason}, "
             f"health={health.stats}")

    return all_posts
