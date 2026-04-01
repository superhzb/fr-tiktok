"""Browser-based TikTok comment scraping via Playwright."""

import logging

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

from .constants import USER_AGENT
from .parser import parse_comments

logger = logging.getLogger(__name__)


def scrape_comments(url: str, cookies: list[dict]) -> list[dict]:
    """Open the TikTok page in a headless browser and intercept comment API responses."""
    comments: list[dict] = []

    def on_response(response):
        if "comment/list" not in response.url or "aweme_id" not in response.url:
            return
        logger.debug("Intercepted comment/list response: %s", response.url)
        try:
            raw = response.json().get("comments", [])
            logger.debug("Raw comments in response: %d", len(raw))
            comments.extend(parse_comments(raw))
        except Exception as exc:
            logger.warning("Failed to parse comment/list response: %s", exc)

    logger.debug("Launching headless Chromium")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 900},
            locale="en-US",
        )
        # Note: yt-dlp cookies cause TikTok to serve a blank page when injected
        # directly into Playwright. The page renders correctly without them.
        logger.debug("Browser context created (cookies not injected)")

        page = context.new_page()
        Stealth().apply_stealth_sync(page)
        page.on("response", on_response)

        logger.debug("Navigating to: %s", url)
        try:
            page.goto(url, wait_until="networkidle", timeout=45000)
        except Exception:
            # networkidle can time out on heavy pages; proceed with what loaded
            logger.debug("networkidle timed out — continuing with current page state")
        page.wait_for_timeout(2000)

        _dismiss_overlays(page)

        _click_comment_icon(page)
        page.wait_for_timeout(5000)

        browser.close()
        logger.debug("Browser closed; total comments collected: %d", len(comments))

    return comments


def _click_comment_icon(page) -> None:
    """Try known selectors for the comment icon; warn if none found."""
    selectors = [
        '[data-e2e="comment-icon"]',
        '[data-e2e="browse-comment-icon"]',
        '[aria-label="Comment"]',
    ]
    for sel in selectors:
        try:
            logger.debug("Trying comment icon selector: %s", sel)
            page.locator(sel).first.click(force=True, timeout=8000)
            logger.debug("Clicked comment icon with selector: %s", sel)
            return
        except Exception:
            continue
    logger.warning("Could not find comment icon — will rely on auto-loaded comments")


def _dismiss_overlays(page) -> None:
    """Close login prompts, keyboard shortcut dialogs, etc."""
    logger.debug("Dismissing overlays")
    for _ in range(3):
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
    page.evaluate("""() => {
        document.querySelectorAll('[data-floating-ui-portal], [class*="Modal-overlay"]')
            .forEach(el => el.remove());
    }""")
    page.wait_for_timeout(500)
