# Module: Get Comments

## Overview

A stateless service that takes a TikTok video URL as input and returns the top N comments as JSON, sorted by most liked.

**Input:** `https://www.tiktok.com/@username/video/1234567890`
**Output:** JSON array of comment objects (sorted by likes descending, default top 10)

---

## How it works

```
Video URL
    │
    ▼
Validate URL ──► Regex check for /video/\d+ pattern
    │
    ▼
Obtain Cookies ──► Run yt-dlp subprocess to extract a valid TikTok session
    │
    ▼
Scrape ──► Launch headless Chromium (Playwright + stealth plugin)
    │        ├─ Inject session cookies into browser context
    │        ├─ Navigate to video page
    │        ├─ Intercept API responses (endpoint: comment/list?aweme_id=...)
    │        ├─ Dismiss overlays (login modals, floating UI)
    │        └─ Click comment icon to open comments panel
    │
    ▼
Parse ──► Transform raw TikTok API comment objects into clean dicts
    │
    ▼
Sort by likes (descending), slice to top N
    │
    ▼
Return JSON array
```

TikTok is a JS-heavy SPA — comment data lives in API responses, not in the page HTML. The scraper hooks into the browser's network layer (`page.on("response")`) and captures the JSON payload from TikTok's `comment/list` endpoint. This makes it resilient to HTML/CSS changes.

---

## Output schema

Each comment object:

| Field      | Type | Description                    |
|------------|------|--------------------------------|
| `user`     | str  | Display name (`user.nickname`) |
| `username` | str  | Handle (`user.unique_id`)      |
| `text`     | str  | Comment body                   |
| `likes`    | int  | Like count (`digg_count`)      |

Example:

```json
[
  {
    "user": "laquechii",
    "username": "laquechii",
    "text": "She's rich rich.",
    "likes": 127777
  },
  {
    "user": "Kcin0891",
    "username": "kcinm0891",
    "text": "\"It's just me\" and then Samira proceeds to document...",
    "likes": 97616
  }
]
```

---

## Key implementation details

### Cookie extraction via yt-dlp

TikTok requires a valid session to serve comments. Rather than managing auth manually, the service shells out to `yt-dlp --dump-json --skip-download <url>` to obtain session cookies. These cookies are injected into the Playwright browser context before navigating.

- Timeout: 30 seconds for the yt-dlp subprocess.
- Cookies are scoped to `.tiktok.com`.

### Stealth browser

- `playwright-stealth` patches browser fingerprints (WebDriver flag, navigator properties, etc.).
- Custom User-Agent mimics real Chrome on Windows.
- Launch args include `--disable-blink-features=AutomationControlled`.
- Viewport: 1280x900, locale: `en-US`.

### API interception over HTML parsing

Hooks `page.on("response")` and filters for URLs containing `comment/list` with an `aweme_id` parameter. Captures the JSON response directly — no DOM scraping.

### Page interaction sequence

1. Navigate to video URL (`wait_until="domcontentloaded"`, 30s timeout).
2. Wait 4 seconds for initial API activity.
3. Dismiss overlays — press Escape 3x, remove floating portal/modal elements via JS.
4. Click the comment icon (`[data-e2e="comment-icon"]`, `force=True`).
5. Wait 5 seconds for comment API responses to arrive.
6. Close browser. All intercepted comments are collected at this point.

### Sorting and limiting

Comments are sorted by `likes` descending and sliced to the requested count (default 10).

---

## Dependencies

```
playwright
playwright-stealth
yt-dlp
```

```bash
pip install playwright playwright-stealth yt-dlp
playwright install chromium
```

---

## Usage

```bash
python main.py comments <video_url> [--count N] [--output FILE]
```

```bash
# Example: get top 5 comments, save to file
python main.py comments https://www.tiktok.com/@uber.gooner/video/7601644767486823700 --count 5 --output comments.json
```

---

## Recreating as a stateless service

This module is already stateless — no database, no persistent sessions, no local cache. Each invocation is self-contained:

1. **Input:** Video URL + optional count.
2. **Process:** Extract cookies → launch browser → intercept API → parse → sort.
3. **Output:** JSON array of top N comments.

To wrap as an HTTP service, expose a single endpoint:

```
GET /comments?url=<video_url>&count=<n>
```

The core function signature is:

```python
def get_comments(url: str, count: int = 10) -> list[dict]:
```

**Considerations for production:**

- **Cold start:** Playwright browser launch + yt-dlp subprocess adds latency (~10-15s per request). Not suitable for low-latency use cases.
- **Concurrency:** Each request spawns its own browser instance. Limit concurrent requests to avoid memory exhaustion.
- **Chromium binary:** `playwright install chromium` must run at build/deploy time. Container images should include the binary.
- **yt-dlp updates:** TikTok frequently changes its anti-bot measures. Keep `yt-dlp` pinned to a recent version and update regularly.
- **No pagination:** Currently captures only the first page of comments loaded when the panel opens. For videos with thousands of comments, this is sufficient to get the top-liked ones since TikTok's default sort surfaces popular comments first.
