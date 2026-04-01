# Module: Channel Monitor

## Overview

A service that takes a TikTok channel URL as input and returns an array of video metadata as JSON.

**Input:** `https://www.tiktok.com/@username`
**Output:** JSON array of video objects (newest first, limited to top N — default 10)

---

## How it works

```
Channel URL
    │
    ▼
Validate URL ──► Extract username via regex: tiktok\.com/@([\w.]+)
    │
    ▼
Scrape ──► Launch headless Chromium (Playwright + stealth plugin)
    │        ├─ Navigate to channel page
    │        ├─ Intercept API responses (endpoints: api/post/item_list, aweme/post)
    │        └─ Scroll page to load more videos (up to top N)
    │
    ▼
Parse ──► Transform raw TikTok API objects into clean video dicts
    │
    ▼
Return JSON array
```

TikTok is a JS-heavy SPA — raw HTML doesn't contain video data. Instead, the scraper hooks into the browser's network layer (`page.on("response")`) and captures the same JSON payloads that TikTok's own frontend consumes. This makes it resilient to HTML/CSS changes.

---

## Output schema

Each video object:

| Field             | Type | Description              |
|-------------------|------|--------------------------|
| `id`              | str  | Video ID                 |
| `desc`            | str  | Caption                  |
| `create_time`     | int  | Unix timestamp           |
| `create_date`     | str  | ISO 8601 date (UTC)      |
| `author`          | str  | Username                 |
| `author_nickname`  | str  | Display name             |
| `music_title`     | str  | Audio track title        |
| `duration`        | int  | Length in seconds         |
| `views`           | int  | Play count               |
| `likes`           | int  | Like count               |
| `comments`        | int  | Comment count            |
| `shares`          | int  | Share count              |
| `url`             | str  | Direct link to video     |

Example:

```json
{
  "id": "7622066678553152788",
  "desc": "Video description...",
  "create_time": 1774650707,
  "create_date": "2026-03-27T22:31:47+00:00",
  "author": "radio.canada.toronto",
  "author_nickname": "Radio-Canada Toronto",
  "music_title": "son original - Radio-Canada Toronto",
  "duration": 133,
  "views": 894,
  "likes": 41,
  "comments": 0,
  "shares": 2,
  "url": "https://www.tiktok.com/@radio.canada.toronto/video/7622066678553152788"
}
```

---

## Key implementation details

- **Stealth browser:** `playwright-stealth` patches browser fingerprints to avoid bot detection. Custom User-Agent mimics real Chrome.
- **API interception over HTML parsing:** Hooks `page.on("response")` to capture TikTok's internal API JSON, not DOM scraping.
- **Top N limit:** Returns at most N videos (default 10), sorted newest-first. Stops scrolling once enough videos are collected.
- **Auto-scroll:** Scrolls the page up to 10 times to trigger lazy-loading of more videos.
- **Overlay dismissal:** Presses Escape and removes floating modals (login prompts) that block the page.
- **Multi-format parsing:** Handles variant field names across TikTok API versions (`playCount` vs `play_count`, `itemList` vs `aweme_list`).
- **Deduplication:** Tracks seen video IDs during a scrape to avoid duplicates from multiple API calls.

---

## Dependencies

```
playwright
playwright-stealth
```

```bash
pip install playwright playwright-stealth
playwright install chromium
```
