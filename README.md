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
from scraper_kit.engine import fetch_posts

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

## How It Works

The framework runs a loop: **search → extract cards → open each card → capture data → close → next card**. For each card, it tries to get data from the site's own API calls first (passive interception), then falls back to DOM scraping.

```
adapter.search(page, keyword)
adapter.apply_filters(page, sort, time_window)
│
│  ┌─── Page loop (up to max_pages) ─────────────────────────┐
│  │                                                          │
│  │  adapter.extract_cards(page) → list of card dicts        │
│  │  │                                                       │
│  │  │  ┌─── Card loop (for each card) ──────────────────┐   │
│  │  │  │                                                 │   │
│  │  │  │  adapter.open_detail(page, card)                │   │
│  │  │  │  adapter.has_captcha(page)                      │   │
│  │  │  │  adapter.wait_for_detail(page, card, timeout)   │   │
│  │  │  │                                                 │   │
│  │  │  │  ┌─ Data merge (API wins, DOM fills gaps) ──┐   │   │
│  │  │  │  │  PassiveTap buffer (from get_api_routes)  │   │   │
│  │  │  │  │  adapter.extract_detail(page, card)       │   │   │
│  │  │  │  │  adapter.extract_comments(page, max)      │   │   │
│  │  │  │  └──────────────────────────────────────────┘   │   │
│  │  │  │                                                 │   │
│  │  │  │  adapter.take_screenshot(page, card, dir)       │   │
│  │  │  │  adapter.close_detail(page, card)               │   │
│  │  │  └─────────────────────────────────────────────────┘   │
│  │  │                                                        │
│  │  scroll down, repeat                                      │
│  └───────────────────────────────────────────────────────────┘
```

Your adapter controls all site-specific behavior. The engine handles timing, health monitoring, dedup, and retry logic.

### Passive API Interception

Most sites load data through internal API calls when you click into a post. PassiveTap listens to `page.on("response")` and captures these automatically — zero extra network requests, invisible to rate limiters.

You tell the framework which URLs to watch and how to parse them:

```python
def get_api_routes(self):
    return {
        "/api/v1/post/detail": self._parse_feed,      # URL substring to match
        "/api/v1/comment/list": self._parse_comments,
    }

def _parse_feed(self, body):
    post = body["data"]
    return "feed", {                    # must return ("feed", post_dict)
        "note_id": post["id"],
        "title": post["title"],
        "content": post["text"],
        "likes": str(post["like_count"]),
        "comments": str(post["comment_count"]),
        "date": post["created_at"],
    }

def _parse_comments(self, body):
    comments = [{"user": c["user"]["name"], "text": c["text"]}
                for c in body["data"]["comments"]]
    return "comments", comments         # must return ("comments", list)

def extract_note_id_from_api(self, data_type, data):
    if data_type == "feed":
        return data.get("note_id", "")
    return ""                           # framework falls back to URL parsing
```

When the engine opens a card and the site fires its own API calls, PassiveTap captures the response, parses it through your handler, and merges it with any DOM data. API data wins for structured fields; DOM fills gaps.

If you skip passive interception (`get_api_routes` returns `{}`), the framework still works — it just relies entirely on `extract_detail()` and `extract_comments()` for DOM scraping.

### Anti-Bot Evasion

Built in, not something you configure:

- **Stealth shims** — fixes fingerprint leaks: `outerWidth/outerHeight`, `navigator.permissions`, `navigator.connection`, WebGL parameters, Error stack traces
- **Human-like behavior** — Bezier curve mouse movement with tremor, log-normal sleep distributions, inertial trackpad scrolling
- **Adaptive health monitoring** — backs off when the site pushes back, stops when the session is dead

### Failure Bundles

Diagnostic snapshots when a detail fetch fails:

```python
posts = fetch_posts(
    adapter, keyword,
    page=page, context=context,
    failure_bundle_verbosity="standard",  # off | minimal | standard | full
)
```

Bundles include: page URL/title/text, tap buffer state, timing, health score. Saved to `data/logs/failures/{site}/{keyword}/`. Defaults to `"off"`.

## Writing an Adapter

### The Approach

You don't write an adapter by reading the protocol definition and filling in stubs. You write it by exploring the site in Chrome DevTools and translating what you see into adapter methods. Here's the workflow:

**Step 1: Recon the site in DevTools** (30 minutes)

Open the site in Chrome. Search for a keyword. Open DevTools → Network tab (filter by XHR/Fetch). Click into a post and watch what API calls fire.

You're looking for:
- **Search results**: Which endpoint returns the list of posts? What fields does it have?
- **Post detail**: When you click a post, does an API call return the full content? Or is it all server-rendered HTML?
- **Comments**: Separate API call, or embedded in the page?

Write down the URL patterns and look at the response JSON structure.

**Step 2: Figure out the UI model**

Two common patterns:
- **Modal** (like XHS): Clicking a search result opens an overlay. The search results stay in the DOM underneath. To close: press Escape or click outside.
- **Navigation** (like Douyin): Clicking a result navigates to a new page. To go back: `page.go_back()`.

This determines how you implement `open_detail()` and `close_detail()`.

**Step 3: Find stable selectors**

In DevTools → Elements, inspect the search results and post detail. Look for:
- `data-*` attributes (e.g., `data-e2e="search-card"`) — survive redesigns
- Semantic class names (e.g., `.note-item`, `.comment-list`) — moderately stable
- Obfuscated class names (e.g., `.css-1a2b3c`) — **avoid**, change on every deploy

If the site obfuscates everything, `data-*` attributes or structural selectors (`a[href*="/video/"]`) are your only option.

**Step 4: Write the adapter incrementally**

Don't implement all 18 methods at once. Start with the 4 that matter most:

```python
class MySiteAdapter:
    name = "mysite"
    base_url = "https://www.example.com"

    def search(self, page, keyword): ...
    def extract_cards(self, page): ...
    def open_detail(self, page, card): ...
    def extract_detail(self, page, card): ...
```

Test each one interactively before moving on (`headed=True`, step through with print statements). Then add the rest.

### Complete Adapter Example

This is a realistic adapter with commentary explaining each decision. Real adapters use `page.evaluate()` with JS blocks for extraction (faster, fewer round-trips) rather than `page.query_selector()` chains.

```python
from scraper_kit.adapter import SiteAdapter

class MySiteAdapter:
    name = "mysite"
    base_url = "https://www.example.com"

    # ── Search ───────────────────────────────────────────────

    def search(self, page, keyword):
        """Navigate to search results. Return the search URL."""
        page.goto(f"{self.base_url}/search?q={keyword}",
                  wait_until="domcontentloaded", timeout=30000)
        # Wait for results to render — pick a selector that proves
        # the results are loaded, not just the page shell.
        page.wait_for_selector(".result-list", timeout=15000)
        return page.url

    def apply_filters(self, page, sort, time_window):
        """Click filter buttons in the UI.

        sort values: "general", "latest", "most-liked", "most-commented"
        time_window values: "day", "week", "half-year", "any"
        Map these to your site's filter labels.
        """
        if sort == "general" and time_window == "any":
            return  # defaults, nothing to click

        labels = {"latest": "最新", "most-liked": "最多点赞"}
        label = labels.get(sort)
        if label:
            page.evaluate(f"""() => {{
                const btn = [...document.querySelectorAll('button, span')]
                    .find(el => el.textContent.trim() === '{label}');
                if (btn) btn.click();
            }}""")

    # ── Card extraction ──────────────────────────────────────

    def extract_cards(self, page):
        """Extract card dicts from search results.

        Must return at least 'note_id' per card. Include anything
        cheap to grab (title, author, likes) — the engine uses these
        for dedup and seen-set comparison.
        """
        return page.evaluate("""() => {
            const cards = [];
            const seen = new Set();
            document.querySelectorAll('.result-card').forEach(el => {
                const id = el.dataset.postId;
                if (!id || seen.has(id)) return;
                seen.add(id);
                cards.push({
                    note_id: id,
                    url: el.querySelector('a')?.href || '',
                    title: el.querySelector('h3')?.textContent?.trim() || '',
                    user: el.querySelector('.author')?.textContent?.trim() || '',
                    likes_from_card: el.querySelector('.likes')?.textContent?.trim() || '0',
                });
            });
            return cards;
        }""")

    # ── Detail view ──────────────────────────────────────────

    def open_detail(self, page, card):
        """Open the post. Return True if the click worked.

        For modal sites: click the card element.
        For navigation sites: click the link.
        """
        el = page.query_selector(f'[data-post-id="{card["note_id"]}"]')
        if not el:
            return False
        el.click()
        return True

    def wait_for_detail(self, page, card, timeout=8000):
        """Wait for the post content to appear.

        Pick a selector that means "content is loaded", not just
        "the modal/page shell appeared". If the content loads via
        a separate API call, wait for the text container.
        """
        try:
            page.wait_for_selector(".post-body", timeout=timeout)
            return True
        except Exception:
            return False

    def extract_detail(self, page, card):
        """Scrape post data from the DOM.

        The framework merges this with passive API data (if any).
        Return as many REQUIRED_POST_KEYS as you can. Missing keys
        fall back to card data.
        """
        return page.evaluate("""() => {
            const content = document.querySelector('.post-body')?.innerText?.trim() || '';
            const likes = document.querySelector('.detail .like-count')?.textContent?.trim() || '';
            const comments = document.querySelector('.detail .comment-count')?.textContent?.trim() || '';
            const date = document.querySelector('.post-date')?.textContent?.trim() || '';
            const video = document.querySelector('video[src]');
            const video_url = (video && !video.src.startsWith('blob:')) ? video.src : '';
            return { content, likes, comments, date, video_url };
        }""")

    def extract_comments(self, page, max_comments=10):
        """Scrape comments from the DOM.

        Scroll the comment container to load more. Use stale-round
        detection to stop when no new comments appear.
        """
        # Scroll to load comments
        for _ in range(max_comments):
            page.evaluate("() => document.querySelector('.comments')?.scrollBy(0, 500)")
            page.wait_for_timeout(500)

        return page.evaluate("""(max) => {
            return [...document.querySelectorAll('.comment-item')].slice(0, max).map(el => ({
                user: el.querySelector('.author')?.textContent?.trim() || '',
                text: el.querySelector('.text')?.textContent?.trim() || '',
                likes: el.querySelector('.likes')?.textContent?.trim() || '0',
            }));
        }""", max_comments)

    def close_detail(self, page, card):
        """Dismiss the detail view and get back to search results.

        CRITICAL CONTRACT: after this returns, extract_cards() must
        work again. If it doesn't, the page loop stalls.

        Modal sites: press Escape or click the close button.
        Navigation sites: page.go_back() + wait for search results.
        """
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        # Verify search results are visible again
        page.wait_for_selector(".result-list", timeout=5000)

    def take_screenshot(self, page, card, screenshot_dir):
        """Optional. Return file path or empty string."""
        return ""

    # ── Passive API interception ─────────────────────────────
    # Skip if the site doesn't have useful API calls, or implement
    # later once basic DOM scraping works.

    def get_api_routes(self):
        return {}

    def extract_note_id_from_api(self, data_type, data):
        return ""

    # ── Anti-bot ─────────────────────────────────────────────

    def has_captcha(self, page):
        """Check for CAPTCHA/bot-detection overlays.

        IMPORTANT: Match on structural elements, not text content.
        Generic text like "验证" appears in normal UI (e.g., "已验证"
        in user profiles). False positives cause the engine to bail
        on healthy sessions.
        """
        return page.evaluate("""() => {
            const wall = document.querySelector('.captcha-overlay, .captcha-modal');
            return !!(wall && wall.offsetHeight > 0);
        }""")

    def dismiss_captcha(self, page):
        return False  # Manual intervention needed

    def has_auth_evidence(self, page):
        """Check if the session expired (login wall visible)."""
        return bool(page.query_selector(".login-modal, .auth-required"))

    def ensure_loaded(self, page):
        """Called once after browser opens. Navigate to the site and
        verify it's ready — e.g., wait for a JS function to exist,
        or for the main content area to render."""
        page.goto(self.base_url, wait_until="domcontentloaded")

    # ── Content parsing ──────────────────────────────────────

    def parse_date_age_days(self, date_str):
        """Parse site-specific date strings to age in days.

        Used by the filtering layer to apply time-window filters.
        Return None if unparseable — the post will be included
        regardless of time window.
        """
        return None

    def parse_engagement(self, value):
        """Parse engagement strings like "1.2k", "3.5万", "1,234".

        Used by the filtering layer for trending detection (comparing
        current engagement against a previous snapshot).
        """
        if not value:
            return 0
        s = str(value).strip().lower()
        if s.endswith("k"):
            try: return int(float(s[:-1]) * 1000)
            except: return 0
        if s.endswith("万"):
            try: return int(float(s[:-1]) * 10000)
            except: return 0
        try:
            return int(s.replace(",", ""))
        except (ValueError, AttributeError):
            return 0

    def build_post_url(self, note_id):
        """Canonical URL for a post. Used as fallback if card/detail
        didn't provide one."""
        return f"{self.base_url}/post/{note_id}"

    # ── Browser config ───────────────────────────────────────

    def get_cdp_args(self):
        """Extra Chrome flags. Usually empty."""
        return []

    def get_locale(self):
        """Browser locale. Match the site's language."""
        return "en-US"

    def get_session_cookie_name(self):
        """The cookie that proves the session is alive.
        Used by the framework to detect expiring sessions."""
        return "session_id"
```

### Post Schema

`extract_detail()` must return (or contribute to, after merge with card + API data) these keys:

```python
REQUIRED_POST_KEYS = {
    "note_id",   # unique identifier — the card already provides this
    "url",       # canonical URL — card or build_post_url() fallback
    "title",     # post title (can be "")
    "content",   # body text
    "user",      # author name
    "likes",     # string — e.g., "1.2万", "350"
    "comments",  # string
    "date",      # display date — e.g., "2天前", "2025-01-15"
}
```

Optional: `collects`, `shares`, `tags`, `cover_url`, `video_url`, `image_urls`, `top_comments`, `screenshot`.

You don't need to return every required key from every method. The engine merges data from three sources (card → API → DOM), and each fills in what it can.

### Testing Incrementally

Test with a headed browser so you can see what's happening:

```python
from patchright.sync_api import sync_playwright
from scraper_kit.browser import find_system_chrome, launch_cdp_browser, setup_cdp_stealth

adapter = MySiteAdapter()

with sync_playwright() as p:
    browser, proc = launch_cdp_browser(p, find_system_chrome(), headed=True)
    context = browser.contexts[0]
    page = context.pages[0]
    setup_cdp_stealth(page, context, browser.version)

    # Test search
    adapter.ensure_loaded(page)
    url = adapter.search(page, "test keyword")
    print(f"Search URL: {url}")

    # Test card extraction
    cards = adapter.extract_cards(page)
    print(f"Found {len(cards)} cards")
    for c in cards[:3]:
        print(f"  {c['note_id']}: {c.get('title', '')[:50]}")

    # Test detail fetch on the first card
    if cards:
        card = cards[0]
        opened = adapter.open_detail(page, card)
        print(f"Opened: {opened}")

        loaded = adapter.wait_for_detail(page, card)
        print(f"Loaded: {loaded}")

        detail = adapter.extract_detail(page, card)
        print(f"Detail: {detail}")

        adapter.close_detail(page, card)
        print("Closed, back to search results")

    input("Press Enter to close browser...")
    browser.close()
```

For automated tests, verify protocol compliance:

```python
from scraper_kit.adapter import SiteAdapter, REQUIRED_POST_KEYS

def test_implements_protocol():
    assert isinstance(MySiteAdapter(), SiteAdapter)

def test_extract_detail_has_required_keys():
    detail = parse_detail_api_response(sample_response)  # unit-test your parser
    missing = REQUIRED_POST_KEYS - detail.keys()
    assert not missing, f"Missing: {missing}"
```

### Common Mistakes

| Mistake | What happens | Fix |
|---------|-------------|-----|
| `close_detail` doesn't restore search results | Page loop stalls — `extract_cards` returns `[]` on next page | After dismiss, `wait_for_selector` on a search-results element |
| `has_captcha` matches normal UI text | Engine bails on healthy sessions | Match on structural overlay elements, not text like "验证" |
| `extract_cards` returns duplicates | Engine wastes time re-fetching seen posts | Deduplicate by `note_id` before returning |
| `wait_for_detail` uses wrong selector | Returns `True` before content loads, detail extraction gets empty strings | Wait for the content container, not the page shell |
| `extract_detail` uses `page.query_selector` chains | Slow (many round-trips to browser) | Use single `page.evaluate()` with JS block |
| `parse_engagement` doesn't handle locale suffixes | Seen-set comparison breaks, trending detection fails | Handle `k`, `万`, `w`, commas |
| `get_api_routes` parser raises on unexpected response | Crashes PassiveTap listener, all subsequent captures fail | Wrap parser body in try/except, return `None` on failure |

## `fetch_posts()` Reference

```python
from scraper_kit.engine import fetch_posts

posts = fetch_posts(
    adapter,                       # your SiteAdapter instance
    "keyword",                     # search keyword
    page=page,                     # open Playwright page
    context=context,               # Playwright browser context
    max_pages=20,                  # pages of search results to scroll
    max_posts=10,                  # stop after this many posts
    max_comments=5,                # max comments per post
    sort="latest",                 # passed to adapter.apply_filters()
    analysis_window="week",        # passed to adapter.apply_filters()
    seen_data={"note_id": {...}},  # previously seen posts (for dedup/trending)
    grind=False,                   # True = extra cooldown rounds instead of stopping
    event_logger=logger,           # optional FetchEventLogger
    failure_bundle_verbosity="off", # off | minimal | standard | full
)
```

Returns a list of post dicts. The framework handles dedup, health-based stopping, and adaptive delays internally.

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
