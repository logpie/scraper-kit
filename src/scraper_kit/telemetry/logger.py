"""Structured JSONL event logging for fetch runs."""
import json
import logging
import os
import time

log = logging.getLogger(__name__)


class FetchEventLogger:
    """Writes one JSON line per event to a per-keyword JSONL file.

    All logging is best-effort — methods never raise exceptions.
    Supports context-manager protocol for automatic close.

    An optional ``site`` field is included in every event when provided.
    Defaults to ``None`` (omitted from output) for backward compatibility
    with existing JSONL consumers.
    """

    def __init__(self, run_id: str, keyword: str, log_dir: str = "data/logs/fetch_events",
                 site: str | None = None):
        self._run_id = run_id
        self._keyword = keyword
        self._site = site
        self._f = None
        try:
            os.makedirs(log_dir, exist_ok=True)
            safe_keyword = keyword.replace("/", "_").replace("\\", "_")
            path = os.path.join(log_dir, f"{safe_keyword}_{run_id}.jsonl")
            self._f = open(path, "a", encoding="utf-8")
        except Exception as e:
            log.warning(f"FetchEventLogger: failed to open log file: {e}")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _write(self, event: dict):
        if self._f is None:
            return
        try:
            event["ts"] = time.time()
            event["run_id"] = self._run_id
            event["keyword"] = self._keyword
            if self._site is not None:
                event["site"] = self._site
            self._f.write(json.dumps(event, ensure_ascii=False) + "\n")
            self._f.flush()
        except Exception as e:
            log.warning(f"FetchEventLogger: write failed: {e}")

    def log_search_start(self, search_term: str, is_related: bool, strategy: str, config: dict):
        self._write({
            "event": "search_start",
            "search_term": search_term,
            "is_related": is_related,
            "strategy": strategy,
            "config": config,
        })

    def log_card_attempt(self, note_id: str, title: str, card_index: int, page_num: int,
                         cards_on_page: int, cards_new: int, cards_skipped: int,
                         health_score: float, consecutive_failures: int, captcha_mode: bool):
        self._write({
            "event": "card_attempt",
            "search_term": self._current_search_term,
            "note_id": note_id,
            "title": title,
            "card_index": card_index,
            "page_num": page_num,
            "cards_on_page": cards_on_page,
            "cards_new": cards_new,
            "cards_skipped": cards_skipped,
            "health_score": health_score,
            "consecutive_failures": consecutive_failures,
            "captcha_mode": captcha_mode,
        })

    def log_card_result(self, note_id: str, data_source: str, content_len: int,
                        comments_count: int, has_images: bool, has_video: bool,
                        captcha: bool, card_only: bool, card_only_reason: str | None,
                        health_score: float, health_event: str,
                        delay_used: float | None, fetch_duration: float,
                        elapsed_run: float, post_index: int,
                        consecutive_failures: int):
        """Log final telemetry for one card.

        Valid ``health_event`` values:
        - ``ok``: detail fetch succeeded
        - ``empty``: detail opened but usable content was missing
        - ``captcha``: CAPTCHA blocked detail extraction
        - ``skip``: detail fetch intentionally skipped
        """
        self._write({
            "event": "card_result",
            "search_term": self._current_search_term,
            "note_id": note_id,
            "data_source": data_source,
            "content_len": content_len,
            "comments_count": comments_count,
            "has_images": has_images,
            "has_video": has_video,
            "captcha": captcha,
            "card_only": card_only,
            "card_only_reason": card_only_reason,
            "health_score": health_score,
            "health_event": health_event,
            "delay_used": delay_used,
            "fetch_duration": fetch_duration,
            "elapsed_run": elapsed_run,
            "post_index": post_index,
            "consecutive_failures": consecutive_failures,
        })

    def log_cards_skipped(self, search_term: str, page_num: int, count: int, reason: str):
        self._write({
            "event": "cards_skipped",
            "search_term": search_term,
            "page_num": page_num,
            "count": count,
            "reason": reason,
        })

    def log_search_end(self, search_term: str, stop_reason: str, pages_scrolled: int,
                       fetched: int, skipped: int, card_only: int, failed: int,
                       passive_api_count: int, dom_fallback_count: int,
                       health_final: float, health_events: dict, duration: float):
        self._write({
            "event": "search_end",
            "search_term": search_term,
            "stop_reason": stop_reason,
            "pages_scrolled": pages_scrolled,
            "fetched": fetched,
            "skipped": skipped,
            "card_only": card_only,
            "failed": failed,
            "passive_api_count": passive_api_count,
            "dom_fallback_count": dom_fallback_count,
            "health_final": health_final,
            "health_events": health_events,
            "duration": duration,
        })

    def log_run_end(self, search_terms: list[str], total_fetched: int, total_skipped: int,
                    total_failed: int, total_analyzed: int, total_seen: int,
                    duration: float, git: str = "", status: str = "ok"):
        # total_skipped = all skipped candidates in this run.
        # total_seen = subset skipped specifically due to seen/dedup checks.
        # They are currently equal in run_daily, but kept separate by design.
        self._write({
            "event": "run_end",
            "search_terms": search_terms,
            "total_fetched": total_fetched,
            "total_skipped": total_skipped,
            "total_failed": total_failed,
            "total_analyzed": total_analyzed,
            "total_seen": total_seen,
            "duration": duration,
            "git": git,
            "status": status,
        })

    def set_search_term(self, search_term: str):
        """Set current search term for card_attempt/card_result events."""
        self._current_search_term = search_term

    def close(self):
        if self._f is not None:
            try:
                self._f.flush()
                self._f.close()
            except Exception:
                pass
            self._f = None

    # Allow attribute access for _current_search_term even if not set
    _current_search_term = ""
