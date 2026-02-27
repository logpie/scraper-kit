# Douyin (抖音) Web Scraping Surface Research

**Date**: 2026-02-27
**Purpose**: Understand Douyin's web scraping surface for building a site adapter in scraper-kit.

---

## 1. Search Page Structure

### URL Pattern

```
https://www.douyin.com/search/{keyword}
https://www.douyin.com/search/{keyword}?type=video
https://www.douyin.com/search/{keyword}?type=user
https://www.douyin.com/search/{keyword}?type=live
```

The keyword is URL-encoded (e.g., `/search/%E6%90%9E%E7%AC%91` for `搞笑`).

### UI Framework

Douyin's web frontend is built with **React** and uses **Semi Design** (`@douyinfe/semi-ui`), ByteDance's own component library maintained by DouyinFE. CSS classes follow the `semi-` prefix convention (e.g., `semi-input`, `semi-button`). However, Douyin also uses **hashed/obfuscated CSS class names** for many custom components, making static CSS selectors fragile. Class names like `eis84Pxw` or `B3AsdZT9` are common and change between deployments.

### Search Results DOM

Specific CSS selectors are **not publicly documented** and are known to change frequently due to obfuscated class names. Key observations from reverse engineering efforts:

- **`data-e2e` attributes**: Douyin uses `data-e2e` attributes for testing/tracking (e.g., `data-e2e="feed-active-video"`, `data-e2e-vid="{aweme_id}"`). These are more stable than class names.
- **Video cards**: Search results are rendered as a list/grid of video cards. Each card contains a thumbnail, title/description, author info, and engagement metrics.
- **Infinite scroll**: Results load via infinite scroll, not traditional pagination.

### Important: API-First Strategy

The **recommended approach** is NOT to parse the DOM but to **intercept API responses** triggered by the search page. The search page fires XHR requests to structured JSON endpoints (see Section 2). This is the approach used by MediaCrawler, the most mature open-source Douyin scraper.

---

## 2. API Endpoints

Douyin's web app communicates with a set of internal API endpoints under the `/aweme/v1/web/` path. These are the same APIs the React frontend calls via XHR/fetch.

### 2.1 Search Results

**Endpoint**: `GET https://www.douyin.com/aweme/v1/web/general/search/single/`

**Parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `search_channel` | string | `"aweme_general"` (general), `"aweme_video_web"` (video), `"aweme_user_web"` (user), `"aweme_live"` (live) |
| `keyword` | string | Search term |
| `offset` | int | Pagination offset (0, 10, 20, ...) |
| `count` | int | Results per page (typically 10) |
| `search_id` | string | Search session ID (from previous response or empty) |
| `sort_type` | int | `0` = comprehensive, `1` = most likes, `2` = latest |
| `publish_time` | int | `0` = unlimited, `1` = within 1 day, `7` = within 1 week, `180` = within 6 months |
| `filter_selected` | string | Additional filters |
| `device_platform` | string | `"webapp"` |
| `aid` | int | `6383` (app ID) |
| `channel` | string | `"channel_pc_web"` |
| `webid` | string | Random 19-digit ID |
| `msToken` | string | Token from localStorage `xmst` key |
| `a_bogus` | string | **NOT required for search endpoint** (per MediaCrawler source) |

**Response shape** (JSON):

```json
{
  "status_code": 0,
  "data": [
    {
      "type": 1,
      "aweme_info": {
        "aweme_id": "7525082444551310602",
        "desc": "Video description text",
        "create_time": 1709000000,
        "author": {
          "uid": "...",
          "sec_uid": "MS4wLjABAAAA...",
          "nickname": "作者名",
          "avatar_thumb": { "url_list": ["..."] },
          "custom_verify": "认证信息"
        },
        "statistics": {
          "digg_count": 12500,
          "comment_count": 340,
          "share_count": 89,
          "collect_count": 560,
          "download_count": 20,
          "forward_count": 15,
          "play_count": 980000
        },
        "video": {
          "cover": { "url_list": ["..."] },
          "play_addr": { "url_list": ["..."], "uri": "..." },
          "duration": 15000
        },
        "text_extra": [
          { "hashtag_name": "搞笑", "hashtag_id": "..." }
        ]
      },
      "aweme_mix_info": null
    }
  ],
  "has_more": 1,
  "cursor": 10,
  "extra": { "search_request_id": "..." }
}
```

**Key note**: The `a_bogus` signature is **excluded from the search endpoint** in MediaCrawler's implementation. This makes search the easiest endpoint to hit.

### 2.2 Video Detail

**Endpoint**: `GET https://www.douyin.com/aweme/v1/web/aweme/detail/`

**Parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `aweme_id` | string | Video ID (numeric string) |
| `device_platform` | string | `"webapp"` |
| `aid` | int | `6383` |
| `channel` | string | `"channel_pc_web"` |
| `webid` | string | Random 19-digit ID |
| `msToken` | string | From localStorage |
| `a_bogus` | string | **Required** - computed signature |

**Response shape** (JSON):

```json
{
  "status_code": 0,
  "aweme_detail": {
    "aweme_id": "7525082444551310602",
    "desc": "Full video description #hashtag",
    "create_time": 1709000000,
    "author": {
      "uid": "...",
      "sec_uid": "MS4wLjABAAAA...",
      "nickname": "作者名",
      "signature": "Author bio",
      "avatar_thumb": { "url_list": ["..."] }
    },
    "statistics": {
      "digg_count": 12500,
      "comment_count": 340,
      "share_count": 89,
      "collect_count": 560,
      "play_count": 980000
    },
    "video": {
      "play_addr": {
        "url_list": ["https://v26-web.douyinvod.com/..."],
        "uri": "v0300fg..."
      },
      "cover": { "url_list": ["..."] },
      "origin_cover": { "url_list": ["..."] },
      "dynamic_cover": { "url_list": ["..."] },
      "duration": 15000,
      "bit_rate": [
        {
          "bit_rate": 1500000,
          "gear_name": "normal_1080_0",
          "quality_type": 2,
          "is_h265": 0,
          "height": 1920,
          "width": 1080
        }
      ]
    },
    "music": {
      "title": "原声",
      "author": "...",
      "play_url": { "url_list": ["..."] }
    },
    "text_extra": [...],
    "image_post_info": null
  }
}
```

### 2.3 Comments List

**Endpoint**: `GET https://www.douyin.com/aweme/v1/web/comment/list/`

**Parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `aweme_id` | string | Video ID |
| `cursor` | int | Pagination cursor (0-based, from previous `cursor` response) |
| `count` | int | Comments per page (typically 20) |
| `device_platform` | string | `"webapp"` |
| `aid` | int | `6383` |
| `webid` | string | Random ID |
| `msToken` | string | Required |
| `a_bogus` | string | **Required** |

**Response shape** (JSON):

```json
{
  "status_code": 0,
  "comments": [
    {
      "cid": "7525...",
      "text": "Comment text content",
      "create_time": 1709001000,
      "digg_count": 45,
      "reply_comment_total": 3,
      "user": {
        "uid": "...",
        "sec_uid": "MS4wLjABAAAA...",
        "nickname": "评论者",
        "avatar_thumb": { "url_list": ["..."] }
      },
      "reply_to_reply_id": "0",
      "reply_id": "0",
      "label_list": null
    }
  ],
  "cursor": 20,
  "has_more": 1,
  "total": 340
}
```

### 2.4 Comment Replies (Sub-comments)

**Endpoint**: `GET https://www.douyin.com/aweme/v1/web/comment/list/reply/`

**Parameters**: Same as comment list, plus `item_id` (the parent comment's `cid`).

### 2.5 User Profile

**Endpoint**: `GET https://www.douyin.com/aweme/v1/web/user/profile/other/`

**Parameters**: `sec_user_id` + standard common params.

### 2.6 User Posts

**Endpoint**: `GET https://www.douyin.com/aweme/v1/web/aweme/post/`

**Parameters**: `sec_user_id`, `max_cursor`, `count` + standard common params.

### Common Parameters (added to ALL requests)

```python
{
    "device_platform": "webapp",
    "aid": "6383",
    "channel": "channel_pc_web",
    "webid": "<random_19_digit>",
}
```

---

## 3. Video Detail Page

### URL Patterns

Douyin has **two distinct URL patterns** for viewing videos:

1. **Direct video page**: `https://www.douyin.com/video/{aweme_id}`
   - Full page navigation, dedicated route
   - Contains SSR data in `<script id="RENDER_DATA">` tag

2. **Modal overlay**: `https://www.douyin.com/discover?modal_id={aweme_id}`
   - Video opens as a modal/overlay on the discover feed
   - URL updates via pushState without full page reload
   - Also used from search: `https://www.douyin.com/search/{keyword}?modal_id={aweme_id}`

3. **Short links**: `https://v.douyin.com/{short_code}`
   - Redirects (302) to one of the above patterns

### SSR RENDER_DATA

Video detail pages include server-side rendered data in a `<script>` tag:

```html
<script id="RENDER_DATA" type="application/json">%7B%2243%22%3A%7B%22aweme%22...</script>
```

- Content is **URL-encoded JSON** -- must be decoded with `urllib.parse.unquote()` or `decodeURIComponent()`
- Structure: `RENDER_DATA['43']['aweme']['detail']` contains the full `aweme_detail` object
- The `'43'` key is a **page/route identifier** that may change between Douyin deployments
- **Caveat**: Douyin has been known to set the `aweme` key to `null` in RENDER_DATA as an anti-scraping measure, forcing fallback to the API endpoint

### Engagement Selectors (CSS -- fragile)

Since class names are obfuscated/hashed, the recommended approach is:

- Use `data-e2e` attributes where available
- Use `data-e2e-vid` to identify the active video element
- Intercept the API response JSON instead of parsing the DOM

---

## 4. Anti-Bot Measures

Douyin employs multiple layers of anti-bot protection. This is the most complex part of building a Douyin adapter.

### 4.1 Cookie Chain

| Cookie | Purpose | How to Obtain |
|--------|---------|---------------|
| `ttwid` | Guest/session tracking ID | POST to `https://ttwid.bytedance.com/ttwid/union/register/` with empty JSON body; returned in `Set-Cookie` header |
| `msToken` | Request authentication token | ~128 chars, generated by Douyin's JS during page load; stored in `localStorage['xmst']` |
| `s_v_web_id` | Verification session cookie | Set by Douyin's verification challenge (captcha); required for API access |
| `__ac_nonce` | Anti-crawl nonce | Server-returned value, must be echoed back |
| `__ac_signature` | Anti-crawl signature | Computed client-side from `__ac_nonce` |
| `odin_tt` | Device fingerprint | Generated during first visit |
| `passport_csrf_token` | CSRF protection | Standard CSRF token from auth flow |
| `sessionid` / `sid_guard` | Login session (if authenticated) | Login flow |

### 4.2 URL Signature Parameters

#### a_bogus (current, replaces X-Bogus)

- **Purpose**: Request-level URL signature to prove the request originated from a real browser
- **Algorithm**: JSVMP (JavaScript Virtual Machine Protection) -- the signing logic is wrapped in a custom bytecode VM that runs in the browser
- **Inputs**: Full URL query string + User-Agent + timestamp
- **Generation method in MediaCrawler**: Uses `execjs` to run a pre-extracted `libs/douyin.js` file:
  ```python
  douyin_sign_obj = execjs.compile(open('libs/douyin.js').read())
  a_bogus = douyin_sign_obj.call('sign_datail', params, user_agent)
  # For reply comments: call('sign_reply', params, user_agent)
  ```
- **Alternative**: Execute signing within Playwright browser context via `page.evaluate()`:
  ```python
  a_bogus = await page.evaluate(
      "([params, post_data, ua]) => window.bdms.init._v[2].p[42]"
      ".apply(null, [0, 1, 8, params, post_data, ua])",
      [params, post_data, user_agent]
  )
  ```
- **Key insight**: The search endpoint (`/general/search/single/`) does **NOT** require `a_bogus`. Comment and detail endpoints do.

#### X-Bogus (legacy, still accepted)

- Predecessor to `a_bogus`, similar purpose
- Multi-stage algorithm: hashing + custom ciphers + data manipulation from URL + UA + timestamp
- Some endpoints still accept it

#### webid

- Random 19-digit numeric string, generated client-side
- Algorithm: UUID-like generation with XOR operations, truncated to 19 digits
- Included in all API requests

### 4.3 JSVMP Code Virtualization

Douyin's critical client-side logic (signature generation, fingerprinting) is protected by **JSVMP** (Virtual Machine based code Protection for JavaScript):

- Target JavaScript code is compiled to custom bytecodes
- A custom VM interpreter runs these bytecodes in the browser
- This makes reverse-engineering significantly harder than standard JS obfuscation
- The VM entry point is accessible at `window.bdms.init._v[2].p[42]` (may change)

### 4.4 Rate Limiting

- Aggressive rate limiting on all API endpoints
- Logged-in cookies yield better results; guest access is more restricted
- Comments endpoint: typically limited to 50 per request, requires throttling
- Search: 10 results per page with pagination
- IP-based rate limiting observed; proxy rotation recommended for volume scraping

### 4.5 Stealth Requirements

- `stealth.min.js` injection needed to pass basic browser fingerprinting checks
- User-Agent must be consistent between cookie acquisition and API requests
- `Referer` header must match the current page URL pattern
- `Host`, `Origin` headers must be set to `www.douyin.com`

---

## 5. Passive API Interception Viability

### Verdict: HIGHLY VIABLE -- This is the recommended approach

The Playwright `page.on('response')` / `page.route()` pattern is the **gold standard** for Douyin scraping. This is exactly what MediaCrawler does, and it avoids the need to reverse-engineer signature algorithms.

### How It Works

1. **Launch browser with persistent context** (preserves login cookies)
2. **Navigate to search page** (`https://www.douyin.com/search/{keyword}`)
3. **Intercept API responses** via `page.on('response', callback)`:
   ```python
   async def on_response(response):
       url = response.url
       if '/aweme/v1/web/general/search/single/' in url:
           data = await response.json()
           # data['data'] contains list of aweme_info objects
       elif '/aweme/v1/web/comment/list/' in url:
           data = await response.json()
           # data['comments'] contains comment objects
   ```
4. **Scroll page** to trigger infinite scroll loading (fires more API requests)
5. **Click video cards** to trigger detail/comment API calls
6. **Collect structured JSON** from intercepted responses

### What the JSON Contains

All API responses contain **fully structured JSON** with:
- `aweme_id` (unique video identifier)
- `desc` (video title/description)
- `author.nickname`, `author.sec_uid`
- `statistics.digg_count` (likes), `statistics.comment_count`, `statistics.share_count`, `statistics.collect_count`, `statistics.play_count`
- `comments[].text` (comment content), `comments[].user.nickname`, `comments[].digg_count`
- `video.cover.url_list`, `video.play_addr.url_list`
- Pagination: `has_more`, `cursor`

### Advantages of Passive Interception

1. **No signature computation needed**: The browser handles all `a_bogus`/`msToken` generation natively
2. **Cookie management is automatic**: Browser context handles `ttwid`, `s_v_web_id`, etc.
3. **Resilient to algorithm changes**: If Douyin updates `a_bogus` generation, the browser still works
4. **Identical to MediaCrawler's approach**: Proven at scale in the most popular open-source scraper
5. **Clean structured data**: JSON responses are well-structured, no HTML parsing needed

### Limitations

1. **Slower than direct API calls**: Must render full pages
2. **Browser resource overhead**: Chromium instance required
3. **Login may be required**: Guest access is increasingly restricted; QR code login recommended
4. **Captcha/verification**: `s_v_web_id` cookie may require solving a verification challenge on first visit

---

## 6. Reference Implementations

### MediaCrawler (NanmiCoder/MediaCrawler)
- **Stars**: ~10k+, most mature multi-platform scraper
- **Approach**: Playwright persistent context + page.evaluate() for signatures + API interception
- **Douyin files**: `media_platform/douyin/core.py`, `client.py`, `field.py`, `help.py`
- **Key pattern**: Uses `execjs` to run extracted `libs/douyin.js` for `a_bogus` generation; also supports `page.evaluate()` fallback via `window.bdms.init._v[2].p[42]`
- **License**: Non-commercial learning license
- **URL**: https://github.com/NanmiCoder/MediaCrawler

### DouYin_Spider (cv-cat/DouYin_Spider)
- **Approach**: Direct API calls with cookie-based auth
- **Requires**: Logged-in cookies from `www.douyin.com` and `live.douyin.com`
- **URL**: https://github.com/cv-cat/DouYin_Spider

### Tiktok_Signature (5ime/Tiktok_Signature)
- **Approach**: Node.js service generating X-Bogus, msToken, ttwid
- **API**: POST with `url` + `userAgent` -> returns `xbogus`, `mstoken`, `ttwid`
- **Caveat**: "algorithms may update anytime, so this tool may stop working"
- **URL**: https://github.com/5ime/Tiktok_Signature

### F2 Framework
- **Approach**: Python library wrapping Douyin API endpoints with signature generation
- **Docs**: https://f2.wiki/en/guide/apps/douyin/overview

### yt-dlp DouyinIE Extractor
- **Approach**: RENDER_DATA parsing + API fallback
- **File**: `yt_dlp/extractor/tiktok.py` (DouyinIE class)
- **URL regex**: `https?://(?:www\.)?douyin\.com/video/(?P<id>[0-9]+)`
- **Key lesson**: RENDER_DATA approach has been unreliable since 2024 (Douyin nulls out aweme key periodically)
- **URL**: https://github.com/yt-dlp/yt-dlp

---

## 7. Recommended Approach for DouyinSiteAdapter

Based on this research, the recommended implementation strategy mirrors what works for XHS in Murmur:

### Primary Strategy: Passive API Interception via Playwright

```
1. Launch Chromium with persistent context (reuse login session)
2. Inject stealth.min.js
3. Register page.on('response') handlers for:
   - /aweme/v1/web/general/search/single/  (search results)
   - /aweme/v1/web/comment/list/           (comments)
   - /aweme/v1/web/aweme/detail/           (video detail, optional)
4. Navigate to https://www.douyin.com/search/{keyword}
5. Scroll to trigger infinite scroll (loads more search results)
6. For each video card found, click to open detail view
7. Collect intercepted JSON responses
8. Parse aweme_info objects -> map to scraper-kit Post model
9. Parse comments -> map to scraper-kit Comment model
```

### Fallback Strategy: RENDER_DATA Parsing

For video detail pages, if API interception misses data:
```python
script = await page.query_selector('script#RENDER_DATA')
if script:
    raw = await script.inner_text()
    data = json.loads(urllib.parse.unquote(raw))
    # Navigate: data['43']['aweme']['detail']
    # Warning: '43' key may change; aweme may be null
```

### Key Differences from XHS Adapter

| Aspect | XHS | Douyin |
|--------|-----|--------|
| Content type | Image posts + text | Short videos |
| Search API | /api/sns/web/v1/search/notes | /aweme/v1/web/general/search/single/ |
| Comment API | /api/sns/web/v2/comment/page | /aweme/v1/web/comment/list/ |
| Signature | X-s, X-t headers | a_bogus URL parameter |
| Video detail | Modal overlay | Modal overlay OR /video/{id} page |
| Engagement fields | liked_count, comment_count | digg_count, comment_count, share_count, collect_count, play_count |
| Rate limiting | Moderate | Aggressive |
| Login requirement | Recommended | Increasingly required |

### Data Mapping (Douyin -> scraper-kit Post)

```python
{
    "id": aweme_info["aweme_id"],
    "title": aweme_info["desc"],
    "author": aweme_info["author"]["nickname"],
    "author_id": aweme_info["author"]["sec_uid"],
    "url": f"https://www.douyin.com/video/{aweme_info['aweme_id']}",
    "created_at": datetime.fromtimestamp(aweme_info["create_time"]),
    "likes": aweme_info["statistics"]["digg_count"],
    "comments_count": aweme_info["statistics"]["comment_count"],
    "shares": aweme_info["statistics"]["share_count"],
    "collects": aweme_info["statistics"]["collect_count"],
    "plays": aweme_info["statistics"]["play_count"],
    "cover_url": aweme_info["video"]["cover"]["url_list"][0],
    "hashtags": [t["hashtag_name"] for t in aweme_info.get("text_extra", []) if t.get("hashtag_name")],
}
```

---

## 8. Open Questions

1. **Login flow**: How to handle initial login? MediaCrawler uses QR code. Can we reuse a persistent browser session like we do for XHS?
2. **a_bogus stability**: How often does the JSVMP bytecode change? Is `libs/douyin.js` extraction a maintenance burden vs. pure passive interception?
3. **Guest access limits**: What can we access without login? Search seems to work guest; comments may not.
4. **Geo restrictions**: Does Douyin web require a China IP? Or does it work globally with the right cookies?
5. **RENDER_DATA '43' key**: Is this constant or does it change per deployment? Need to handle dynamic key discovery.
6. **Video vs. image posts**: Douyin supports image carousel posts (`image_post_info`). How common are these in search results?
