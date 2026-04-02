from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .config import Config
from .db import Channel, Comment, Job, Video, get_session
from .pipeline import run_cmd
from .queue import enqueue

logger = logging.getLogger(__name__)

_checker_log = logging.getLogger("tk_orchestrator.scheduler.channel_checker")
_comments_log = logging.getLogger("tk_orchestrator.scheduler.comments")


async def _run_channel_checker(channel_url: str, config: Config) -> list[dict]:
    try:
        stdout = await run_cmd(
            ["tk-channel-checker", channel_url, "--count", str(config.video_count)],
            _checker_log,
        )
        return json.loads(stdout)
    except Exception as e:
        logger.error("tk-channel-checker failed for %s: %s", channel_url, e)
        return []


async def _run_comments(video_url: str, config: Config) -> list[dict]:
    try:
        stdout = await run_cmd(
            ["tk-comments", video_url, "--count", str(config.comment_count)],
            _comments_log,
        )
        return json.loads(stdout)
    except Exception as e:
        logger.error("tk-comments failed for %s: %s", video_url, e)
        return []


async def poll_channel(
    channel_id: int, username: str, channel_url: str, config: Config
) -> list[int]:
    """Poll one channel. Returns job IDs for newly discovered videos."""
    logger.info("Polling @%s", username)
    videos = await _run_channel_checker(channel_url, config)
    if not videos:
        return []

    new_job_ids: list[int] = []

    for v in videos:
        is_new = False
        new_job_id: int | None = None

        with get_session() as s:
            existing = s.get(Video, v["id"])
            if existing:
                existing.views = v.get("views")
                existing.likes = v.get("likes")
                existing.comments_count = v.get("comments")
                existing.shares = v.get("shares")
            else:
                is_new = True
                created_at = None
                if v.get("create_date"):
                    try:
                        created_at = datetime.fromisoformat(v["create_date"])
                    except ValueError:
                        pass

                video = Video(
                    id=v["id"],
                    channel_id=channel_id,
                    description=v.get("desc"),
                    url=v.get("url"),
                    duration=v.get("duration"),
                    views=v.get("views"),
                    likes=v.get("likes"),
                    comments_count=v.get("comments"),
                    shares=v.get("shares"),
                    author=v.get("author"),
                    author_nickname=v.get("author_nickname"),
                    music_title=v.get("music_title"),
                    created_at=created_at,
                )
                job = Job(video_id=v["id"], status="pending")
                s.add(video)
                s.add(job)
                s.flush()
                new_job_id = job.id

        if is_new and new_job_id is not None:
            logger.info("New video discovered: %s (@%s)", v["id"], username)
            comments = await _run_comments(v.get("url", ""), config)
            with get_session() as s:
                for c in comments:
                    s.add(
                        Comment(
                            video_id=v["id"],
                            user=c.get("user"),
                            username=c.get("username"),
                            text=c.get("text"),
                            likes=c.get("likes"),
                        )
                    )
            new_job_ids.append(new_job_id)

    with get_session() as s:
        ch = s.get(Channel, channel_id)
        if ch:
            ch.last_checked_at = datetime.now(timezone.utc)

    return new_job_ids


async def poll_all_channels(config: Config) -> None:
    """Check all active channels for new videos and enqueue jobs."""
    logger.info("Scheduler tick: polling channels")
    with get_session() as s:
        channels = s.query(Channel).filter(Channel.is_active == True).all()
        channel_infos = [(c.id, c.username, c.url) for c in channels]

    for channel_id, username, channel_url in channel_infos:
        job_ids = await poll_channel(channel_id, username, channel_url, config)
        for job_id in job_ids:
            enqueue(job_id)


def setup_scheduler(config: Config) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        poll_all_channels,
        "interval",
        seconds=config.poll_interval_seconds,
        args=[config],
        id="poll_channels",
        replace_existing=True,
    )
    return scheduler
