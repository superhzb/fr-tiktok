"""tk-comment-checker — fetch top TikTok comments sorted by likes.

Public API:
    get_comments(url, count=10) -> list[dict]
"""

import logging

from .validator import validate_video_url
from .cookies import obtain_cookies
from .scraper import scrape_comments

logger = logging.getLogger(__name__)


def get_comments(url: str, count: int = 10) -> list[dict]:
    """Fetch the top *count* comments from a TikTok video URL.

    Returns a list of dicts sorted by likes (descending), each containing:
        user     – display name
        username – @handle
        text     – comment body
        likes    – like count (int)
    """
    logger.debug("get_comments called: url=%s count=%d", url, count)
    validate_video_url(url)
    cookies = obtain_cookies(url)
    logger.debug("Obtained %d cookies", len(cookies))
    raw = scrape_comments(url, cookies)
    logger.debug("Scraped %d raw comments", len(raw))
    raw.sort(key=lambda c: c["likes"], reverse=True)
    result = raw[:count]
    logger.debug("Returning top %d comments", len(result))
    return result
