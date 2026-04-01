"""Main download orchestration."""
import logging
from pathlib import Path

from .resolver import resolve_url, extract_post_id, is_tiktok_url
from .browser import download_via_browser
from .http_fallback import download_via_http

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = Path.home() / "Public" / "Tiktok"


def _find_existing(post_id: str, output_dir: Path) -> Path | None:
    """Return the path of an already-downloaded file for this post ID, or None."""
    if not output_dir.is_dir():
        return None
    for f in output_dir.iterdir():
        if post_id in f.name:
            logger.debug("Duplicate found: %s", f)
            return f
    return None


def download(url: str, output_dir: Path | None = None) -> Path:
    """
    Download a TikTok video to *output_dir* (default: ~/Public/Tiktok).

    Workflow:
    1. Validate as TikTok URL.
    2. Resolve redirects to canonical URL.
    3. Extract post ID — fail fast if missing.
    4. Return existing file if already downloaded (ID-based).
    5. Try Playwright browser flow (ssstik.io).
    6. Fall back to HTTP-only flow on browser failure.
    7. Save using the filename provided by ssstik.

    Returns the local Path of the saved file.
    """
    if output_dir is None:
        output_dir = DEFAULT_OUTPUT_DIR

    if not is_tiktok_url(url):
        raise ValueError(f"Not a TikTok URL: {url}")

    logger.debug("Input URL: %s", url)
    canonical = resolve_url(url)
    post_id = extract_post_id(canonical)
    logger.info("Post ID: %s", post_id)

    existing = _find_existing(post_id, output_dir)
    if existing:
        logger.info("Already downloaded: %s", existing)
        return existing

    output_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = output_dir / f"_tmp_{post_id}.mp4"

    # Browser-first
    try:
        logger.info("Attempting browser flow…")
        suggested = download_via_browser(canonical, tmp_path)
        logger.info("Browser flow succeeded")
    except Exception as browser_err:
        logger.warning("Browser flow failed (%s) — trying HTTP fallback", browser_err)
        tmp_path.unlink(missing_ok=True)
        try:
            suggested = download_via_http(canonical, tmp_path)
            logger.info("HTTP fallback succeeded")
        except Exception as http_err:
            tmp_path.unlink(missing_ok=True)
            raise RuntimeError(
                f"Both download flows failed.\n"
                f"  Browser: {browser_err}\n"
                f"  HTTP:    {http_err}"
            ) from http_err

    final_path = output_dir / suggested
    tmp_path.rename(final_path)
    logger.info("Saved → %s", final_path)
    return final_path
