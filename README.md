# scraper-kit

Adapter-based web scraping framework with built-in anti-bot evasion. Designed for sites that fight scrapers — CAPTCHAs, fingerprinting, rate limiting.

Write a site adapter, get human-like browsing, passive API interception, health monitoring, and failure diagnostics for free.

## Install

```bash
pip install git+https://github.com/logpie/scraper-kit.git
```

Then install browser binaries:

```bash
python -m patchright install chromium
```

## Quick Start

```python
from patchright.sync_api import sync_playwright
from scraper_kit.browser import find_system_chrome, launch_cdp_browser, setup_cdp_stealth
from scraper_kit.engine import fetch_posts, PassiveTap

# Your site adapter (see "Writing an Adapter" below)
from my_site import MySiteAdapter

adapter = MySiteAdapter()

with sync_playwright() as p:
    chrome_path = find_system_chrome()
    browser, proc = launch_cdp_browser(p, chrome_path, headed=False)
    context = browser.contexts[0]
    page = context.pages[0]
    setup_cdp_stealth(page, context, browser.version)

    posts = fetch_posts(
        adapter, "search keyword",
        page=page, context=context,
        max_posts=10,
        max_comments=5,
    )

    for post in posts:
        print(f"{post['user']}: {post['title'][:60]}")
        print(f"  likes={post['likes']} comments={post['comments']}")

    browser.close()
```

## What It Does

### Hybrid Fetch Strategy

Every post goes through: **UI click → passive API capture → DOM fallback**.

1. Click into a post via adapter-provided selectors
2. PassiveTap intercepts the site's own API responses (feed data, comments) — zero extra network requests
3. DOM extraction fills gaps if the API didn't fire
4. Merge: API data wins for structured fields, DOM fills the rest

### Anti-Bot Evasion

- **Stealth shims** — fixes fingerprint leaks that stealth.min.js misses: `outerWidth/outerHeight`, `navigator.permissions`, `navigator.connection`, WebGL parameters
- **Human-like behavior** — Bezier curve mouse movement with tremor, log-normal sleep distributions, inertial trackpad scrolling, random modal dismissal
- **Adaptive health monitoring** — backs off when the site pushes back, stops when the session is dead

### Passive API Interception

Sites load data via their own JS API calls. PassiveTap listens to `page.on("response")` and routes matches through adapter-provided parsers. You get structured data (likes, comments, dates, video URLs) without parsing DOM or making extra requests.

```python
# In your adapter:
def get_api_routes(self):
    return {
        "/api/v1/feed": self._parse_feed,
        "/api/v1/comments": self._parse_comments,
    }

def _parse_feed(self, body):
    post = body["data"]["post"]
    return "feed", {
        "note_id": post["id"],
        "content": post["text"],
        "likes": str(post["like_count"]),
    }
```

### Failure Bundles

When a detail fetch fails, capture a diagnostic snapshot:

```python
posts = fetch_posts(
    adapter, keyword,
    page=page, context=context,
    failure_bundle_verbosity="standard",  # off | minimal | standard | full
)
```

Bundles include: page URL/title/text, tap buffer state, timing, health score, adapter-specific extras. Saved to `data/logs/failures/{site}/{keyword}/`. Verbosity defaults to `"off"` — zero overhead in production.

## Writing an Adapter

Implement the `SiteAdapter` protocol. Here's a minimal example:

```python
from scraper_kit.adapter import SiteAdapter

class MySiteAdapter:
    name = "mysite"
    base_url = "https://www.example.com"

    # --- Search ---
    def search(self, page, keyword):
        page.goto(f"{self.base_url}/search?q={keyword}")
        page.wait_for_selector(".results", timeout=10000)
        return page.url

    def apply_filters(self, page, sort, time_window):
        pass  # Optional: click sort/filter buttons

    # --- Card extraction ---
    def extract_cards(self, page):
        cards = []
        for el in page.query_selector_all(".result-card"):
            cards.append({
                "note_id": el.get_attribute("data-id"),
                "title": el.query_selector("h3").inner_text(),
                "url": el.get_attribute("href"),
            })
        return cards

    # --- Detail view ---
    def open_detail(self, page, card):
        link = page.query_selector(f'[data-id="{card["note_id"]}"]')
        if not link:
            return False
        link.click()
        return True

    def wait_for_detail(self, page, card, timeout=8000):
        try:
            page.wait_for_selector(".post-content", timeout=timeout)
            return True
        except:
            return False

    def extract_detail(self, page, card):
        return {
            "content": page.query_selector(".post-content").inner_text(),
            "likes": page.query_selector(".likes").inner_text(),
            "comments": page.query_selector(".comment-count").inner_text(),
        }

    def extract_comments(self, page, max_comments=10):
        comments = []
        for el in page.query_selector_all(".comment")[:max_comments]:
            comments.append({
                "user": el.query_selector(".author").inner_text(),
                "text": el.query_selector(".text").inner_text(),
            })
        return comments

    def close_detail(self, page, card):
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

    def take_screenshot(self, page, card, screenshot_dir):
        return ""  # Optional

    # --- Passive API (optional but recommended) ---
    def get_api_routes(self):
        return {}  # No passive interception

    def extract_note_id_from_api(self, data_type, data):
        return ""

    # --- Anti-bot ---
    def has_captcha(self, page):
        return bool(page.query_selector(".captcha-wall"))

    def dismiss_captcha(self, page):
        return False

    def has_auth_evidence(self, page):
        return bool(page.query_selector(".login-prompt"))

    def ensure_loaded(self, page):
        page.goto(self.base_url, wait_until="domcontentloaded")

    # --- Parsing ---
    def parse_date_age_days(self, date_str):
        return None  # Optional: return age in days

    def parse_engagement(self, value):
        try:
            return int(value.replace(",", ""))
        except (ValueError, AttributeError):
            return 0

    def build_post_url(self, note_id):
        return f"{self.base_url}/post/{note_id}"

    # --- Browser config ---
    def get_cdp_args(self):
        return []

    def get_locale(self):
        return "en-US"

    def get_session_cookie_name(self):
        return "session"
```

## Architecture

```
scraper_kit/
├── adapter.py          # SiteAdapter Protocol definition
├── browser/            # Chrome launch, stealth, cookies, UA
│   ├── chrome.py       # find_system_chrome(), launch_cdp_browser()
│   ├── stealth.py      # build_stealth_shim(), setup_cdp_stealth()
│   ├── cookies.py      # migrate_cookies()
│   ├── session.py      # open_browser() context manager
│   └── ua.py           # User-Agent building
├── engine/             # Core scraping orchestration
│   ├── orchestrator.py # fetch_posts() entry point
│   ├── hybrid.py       # Hybrid strategy (UI + passive API)
│   ├── passive_tap.py  # PassiveTap, WaitResult, wait_for()
│   ├── health.py       # HealthMonitor (rolling-window scoring)
│   ├── failure_bundle.py # Diagnostic snapshots on failure
│   └── errors.py       # ScraperSignal, ScraperError
├── human/              # Human-like behavior
│   └── behavior.py     # Bezier mouse, inertial scroll, log-normal sleep
├── filtering/          # Dedup and seen-set management
│   ├── seen.py         # load_seen(), save_seen(), should_refetch()
│   ├── card_filter.py  # filter_cards()
│   └── counting.py     # fetch_count(), grind_count()
└── telemetry/          # Structured JSONL event logging
    └── logger.py       # FetchEventLogger
```

### Key Design Decisions

- **Adapter pattern** — all site-specific knowledge lives in the adapter. The engine never touches selectors, URLs, or API endpoints directly.
- **No browser lifecycle management** — framework receives an open page/context, never creates one. Your app controls the browser.
- **Passive over active** — intercept the site's own API calls instead of making new ones. Invisible to rate limiters.
- **Health-driven** — adaptive delays and auto-stop based on rolling success/failure window. No fixed retry counts.

## Telemetry

Every fetch run writes structured JSONL events:

```python
from scraper_kit.telemetry import FetchEventLogger

with FetchEventLogger("run_001", "keyword", site="mysite") as logger:
    posts = fetch_posts(
        adapter, "keyword",
        page=page, context=context,
        event_logger=logger,
    )
```

Events: `search_start`, `card_attempt`, `card_result`, `cards_skipped`, `search_end`, `failure_dump`, `run_end`. Each line includes timestamp, run ID, keyword, health score, and data source.

## Requirements

- Python 3.10+
- System Chrome or Chromium (for CDP mode) — or falls back to Playwright's bundled Chromium
- [patchright](https://github.com/nicezombie/patchright) (installed automatically)

## License

MIT
