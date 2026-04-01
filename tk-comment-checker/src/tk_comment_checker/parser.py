"""Parse raw TikTok API comment responses into clean dicts."""

import logging

logger = logging.getLogger(__name__)


def parse_comments(raw_comments: list[dict]) -> list[dict]:
    """Extract user, username, text, and likes from raw API comment objects."""
    parsed = []
    for c in raw_comments:
        parsed.append({
            "user": c.get("user", {}).get("nickname", "Unknown"),
            "username": c.get("user", {}).get("unique_id", ""),
            "text": c.get("text", ""),
            "likes": c.get("digg_count", 0),
        })
    logger.debug("Parsed %d comments from raw API objects", len(parsed))
    return parsed
