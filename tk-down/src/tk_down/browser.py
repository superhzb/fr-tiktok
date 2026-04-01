"""Playwright-based ssstik.io browser download flow."""
import logging
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

logger = logging.getLogger(__name__)

SSSTIK_URL = "https://ssstik.io/"
_INPUT_SEL = "#main_page_text"
_SUBMIT_SEL = "#_gcaptcha_pt"
_DESC_SEL = "p.maintext"
_LINK_SEL = "a.download_link"

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def _is_target_link(element) -> bool:
    """True when the element is the non-HD 'Without watermark' link."""
    classes = element.get_attribute("class") or ""
    text = element.inner_text().strip()
    return (
        text == "Without watermark"
        and "without_watermark" in classes
        and "quality-best" not in classes
        and "without_watermark_hd" not in classes
    )


def download_via_browser(tiktok_url: str, output_path: Path) -> str:
    """
    Open ssstik.io in a headless Chromium browser, submit the TikTok URL,
    click the non-HD watermark-free download link, and save the file.

    Returns the suggested filename from the browser download. Raises on any failure.
    """
    with sync_playwright() as p:
        logger.debug("Launching headless Chromium")
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=_UA, accept_downloads=True)
        page = context.new_page()

        try:
            logger.debug("Loading %s", SSSTIK_URL)
            page.goto(SSSTIK_URL, wait_until="domcontentloaded")

            logger.debug("Entering TikTok URL into form")
            page.fill(_INPUT_SEL, tiktok_url)

            logger.debug("Submitting form via requestSubmit()")
            page.evaluate(
                f'document.querySelector("{_SUBMIT_SEL}").closest("form").requestSubmit()'
            )

            logger.debug("Waiting for result (p.maintext)…")
            page.wait_for_selector(_DESC_SEL, timeout=30_000)

            links = page.locator(_LINK_SEL).all()
            logger.debug("Found %d download links", len(links))
            target = next((lnk for lnk in links if _is_target_link(lnk)), None)
            if target is None:
                raise RuntimeError("No non-HD 'Without watermark' download link found on page")

            logger.debug("Clicking download link")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with page.expect_download(timeout=60_000) as dl_info:
                target.click()

            dl = dl_info.value
            suggested = dl.suggested_filename
            logger.debug("Download started: %s", suggested)
            dl.save_as(output_path)

            if not output_path.exists() or output_path.stat().st_size == 0:
                raise RuntimeError("Downloaded file is empty or missing")

            logger.debug("Saved %d bytes to %s", output_path.stat().st_size, output_path)
            return suggested

        except PlaywrightTimeout as e:
            raise RuntimeError(f"Playwright timed out: {e}") from e
        finally:
            context.close()
            browser.close()
