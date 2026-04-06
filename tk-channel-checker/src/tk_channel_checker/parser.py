"""Parse raw TikTok API video responses into clean metadata dicts."""

import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)


def parse_video(item: dict) -> dict:
    """Extract metadata from a single raw TikTok video/aweme object."""
    stats = item.get("stats") or item.get("statistics") or {}
    author = item.get("author") or {}
    music = item.get("music") or {}
    video = item.get("video") or {}

    create_time = item.get("createTime") or item.get("create_time", 0)
    try:
        create_time = int(create_time)
    except (ValueError, TypeError):
        create_time = 0

    video_id = str(item.get("id") or item.get("aweme_id", ""))
    unique_id = author.get("uniqueId") or author.get("unique_id", "")

    parsed = {
        "id": video_id,
        "desc": item.get("desc", ""),
        "create_time": create_time,
        "create_date": (
            datetime.fromtimestamp(create_time, tz=timezone.utc).isoformat()
            if create_time
            else ""
        ),
        "author": unique_id,
        "author_nickname": author.get("nickname", ""),
        "music_title": music.get("title", ""),
        "duration": video.get("duration", 0),
        "views": stats.get("playCount") or stats.get("play_count", 0),
        "likes": stats.get("diggCount") or stats.get("digg_count", 0),
        "comments": stats.get("commentCount") or stats.get("comment_count", 0),
        "shares": stats.get("shareCount") or stats.get("share_count", 0),
        "url": f"https://www.tiktok.com/@{unique_id}/video/{video_id}",
    }
    log.debug("Parsed video id=%s author=%s views=%s", video_id, unique_id, parsed["views"])
    return parsed


def parse_videos(raw_items: list[dict]) -> list[dict]:
    """Parse a list of raw video items. Skips empty/null entries."""
    return [parse_video(item) for item in raw_items if item]
