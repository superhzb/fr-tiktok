"""URL validation for TikTok channel links."""

import logging
import re

log = logging.getLogger(__name__)

_CHANNEL_RE = re.compile(r"tiktok\.com/@([\w.]+)")


def validate_channel_url(url: str) -> str:
    """Validate and extract the username from a TikTok channel URL.

    Accepts:
        https://www.tiktok.com/@username
        https://tiktok.com/@username
        https://www.tiktok.com/@username?lang=en

    Returns the username (without @).
    Raises ValueError for invalid URLs.
    """
    log.debug("Validating URL: %s", url)
    match = _CHANNEL_RE.search(url)
    if not match:
        raise ValueError(f"Not a valid TikTok channel URL: {url!r}")
    username = match.group(1)
    log.debug("Extracted username: %s", username)
    return username
