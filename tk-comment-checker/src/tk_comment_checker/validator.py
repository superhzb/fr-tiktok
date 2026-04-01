"""URL validation for TikTok video links."""

import logging
import re

logger = logging.getLogger(__name__)


def validate_video_url(url: str) -> None:
    """Raise ValueError if the URL does not contain a TikTok video ID."""
    logger.debug("Validating URL: %s", url)
    if not re.search(r"/video/\d+", url):
        raise ValueError(f"Could not find a video ID in: {url}")
    logger.debug("URL is valid")
