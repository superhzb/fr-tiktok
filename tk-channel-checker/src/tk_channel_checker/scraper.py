"""Browser-based TikTok channel video scraping via Playwright."""

import logging

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

from .constants import DEFAULT_TOP_N, USER_AGENT, VIDEO_LIST_ENDPOINTS
from .parser import parse_videos
from .validator import validate_channel_url

log = logging.getLogger(__name__)


def scrape_channel(url: str, max_videos: int = DEFAULT_TOP_N) -> list[dict]:
    """Scrape video metadata from a TikTok channel page.

    Launches a headless Chromium browser, navigates to the channel, intercepts
    TikTok's internal API responses, and returns up to *max_videos* video
    metadata dicts sorted newest-first.

    Args:
        url: TikTok channel URL, e.g. ``https://www.tiktok.com/@username``
        max_videos: Maximum number of videos to return (default 10).

    Returns:
        List of video dicts matching the schema in channel_monitor.md.

    Raises:
        ValueError: If *url* is not a valid TikTok channel URL.
    """
    username = validate_channel_url(url)
    log.info("Scraping channel @%s (max %d videos)", username, max_videos)

    videos: list[dict] = []
    seen_ids: set[str] = set()

    def on_response(response):
        resp_url = response.url
        if not any(k in resp_url for k in VIDEO_LIST_ENDPOINTS):
            return
        log.debug("Intercepted API response: %s", resp_url)
        try:
            data = response.json()
        except Exception as exc:
            log.debug("Could not parse response JSON from %s: %s", resp_url, exc)
            return

        items = (
            data.get("itemList")
            or data.get("aweme_list")
            or data.get("items")
            or []
        )
        log.debug("API response contained %d item(s)", len(items))

        for v in parse_videos(items):
            if v["id"] and v["id"] not in seen_ids:
                seen_ids.add(v["id"])
                videos.append(v)
                log.debug("Collected video id=%s total=%d", v["id"], len(videos))

    with sync_playwright() as pw:
        log.debug("Launching headless Chromium")
        browser = pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 900},
            locale="en-US",
        )
        page = context.new_page()
        Stealth().apply_stealth_sync(page)
        page.on("response", on_response)

        log.info("Navigating to %s", url)
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(5_000)

        _dismiss_overlays(page)

        scrolls = 0
        max_scrolls = 10
        while len(videos) < max_videos and scrolls < max_scrolls:
            log.debug("Scroll %d/%d — videos so far: %d", scrolls + 1, max_scrolls, len(videos))
            page.evaluate("window.scrollBy(0, window.innerHeight)")
            page.wait_for_timeout(2_000)
            scrolls += 1

        log.debug("Closing browser after %d scroll(s)", scrolls)
        browser.close()

    videos.sort(key=lambda v: v["create_time"], reverse=True)
    result = videos[:max_videos]
    log.info("Returning %d video(s) for @%s", len(result), username)
    return result


def _dismiss_overlays(page) -> None:
    """Close login prompts and floating modals that block the page."""
    log.debug("Dismissing overlays")
    for _ in range(3):
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
    page.evaluate("""() => {
        document.querySelectorAll('[data-floating-ui-portal], [class*="Modal-overlay"]')
            .forEach(el => el.remove());
    }""")
    page.wait_for_timeout(500)
