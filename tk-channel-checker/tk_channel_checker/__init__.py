"""tk-channel-checker — Fetch TikTok channel video metadata.

Public API:
    scrape_channel(url, max_videos=10) -> list[dict]
    validate_channel_url(url)          -> str (username)
"""

from .scraper import scrape_channel
from .validator import validate_channel_url

__all__ = ["scrape_channel", "validate_channel_url"]
