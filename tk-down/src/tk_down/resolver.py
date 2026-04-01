"""URL resolution and TikTok post ID extraction."""
import re
import logging
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

_REDIRECT_HOSTS = {"vm.tiktok.com", "vt.tiktok.com", "www.tiktok.com", "m.tiktok.com"}

_POST_ID_PATTERNS = [
    r"/@[^/]+/video/(\d+)",
    r"/v/(\d+)",
    r"/video/(\d+)",
]


def is_tiktok_url(url: str) -> bool:
    host = urlparse(url).netloc
    return host.endswith("tiktok.com")


def resolve_url(url: str) -> str:
    """Follow redirects to get the canonical TikTok post URL."""
    host = urlparse(url).netloc
    if any(h in host for h in _REDIRECT_HOSTS):
        logger.debug("Resolving redirects for %s", url)
        with httpx.Client(
            follow_redirects=True,
            headers={"User-Agent": BROWSER_UA},
            timeout=15,
        ) as client:
            resp = client.get(url)
            final = str(resp.url)
        logger.debug("Resolved to %s", final)
        return final
    return url


def extract_post_id(url: str) -> str:
    """Extract the numeric TikTok post ID from a canonical URL."""
    for pattern in _POST_ID_PATTERNS:
        m = re.search(pattern, url)
        if m:
            logger.debug("Extracted post ID %s from %s", m.group(1), url)
            return m.group(1)
    raise ValueError(f"No TikTok post ID found in URL: {url}")
