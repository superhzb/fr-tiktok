from __future__ import annotations

import json
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .config import Config
from .db import Channel, Comment, Job, Video, get_session
from .pipeline import run_cmd
from .queue import enqueue

logger = logging.getLogger(__name__)

_checker_log = logging.getLogger("tk_orchestrator.scheduler.channel_checker")
_comments_log = logging.getLogger("tk_orchestrator.scheduler.comments")


async def _run_channel_checker_count(channel_url: str, count: int) -> list[dict]:
    try:
        stdout = await run_cmd(
            ["tk-channel-checker", channel_url, "--count", str(count)],
            _checker_log,
        )
        return json.loads(stdout)
    except Exception as e:
        logger.error("tk-channel-checker failed for %s: %s", channel_url, e)
        return []


def _video_exists(video_id: str) -> bool:
    with get_session() as s:
        return s.get(Video, video_id) is not None


async def _find_new_videos(channel_url: str, config: Config) -> list[dict]:
    """Return up to ``video_count`` unseen videos, walking newest to oldest."""
    target_new_videos = max(config.video_count, 1)
    per_channel_limit = max(config.channel_fetch_limit, 1)
    total_scan_limit = max(config.channel_scan_limit, per_channel_limit)
    batch_size = max(target_new_videos, per_channel_limit)
    discovered_new_videos: list[dict] = []
    seen_ids: set[str] = set()
    requested_count = batch_size

    while requested_count <= total_scan_limit:
        videos = await _run_channel_checker_count(channel_url, requested_count)
        if not videos:
            return discovered_new_videos

        for video in videos:
            video_id = video["id"]
            if video_id in seen_ids:
                continue
            seen_ids.add(video_id)
            if not _video_exists(video_id):
                discovered_new_videos.append(video)
                if len(discovered_new_videos) >= target_new_videos:
                    return discovered_new_videos

        if len(videos) < requested_count:
            return discovered_new_videos

        requested_count += batch_size

    logger.warning(
        "Reached scan cap while checking %s for up to %d unseen videos (per_fetch=%d total=%d)",
        channel_url,
        target_new_videos,
        per_channel_limit,
        total_scan_limit,
    )
    return discovered_new_videos


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


async def _translate_comments(
    comments: list[dict],
    video_description: str | None,
    config: Config,
) -> list[dict]:
    if not comments:
        return comments

    try:
        with tempfile.TemporaryDirectory(prefix="tk-orch-comments-") as tmpdir:
            tmp_path = Path(tmpdir)
            input_path = tmp_path / "comments.json"
            output_path = tmp_path / "comments.translated.json"
            input_path.write_text(
                json.dumps(comments, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            cmd = [
                "tk-comment-translator",
                str(input_path),
                "--output",
                str(output_path),
                "--model",
                config.translate_model,
                "--batch-size",
                str(config.translate_batch_size),
            ]

            if video_description:
                description_path = tmp_path / "description.txt"
                description_path.write_text(video_description, encoding="utf-8")
                cmd.extend(["--description", str(description_path)])

            await run_cmd(cmd, _comments_log)
            return json.loads(output_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error("tk-comment-translator failed: %s", e)
        return comments


async def poll_channel(
    channel_id: int, username: str, channel_url: str, config: Config
) -> list[int]:
    """Poll one channel. Returns job IDs for newly discovered videos."""
    logger.info("Polling @%s", username)
    videos = await _find_new_videos(channel_url, config)
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
            comments = await _translate_comments(comments, v.get("desc"), config)
            with get_session() as s:
                for c in comments:
                    s.add(
                        Comment(
                            video_id=v["id"],
                            user=c.get("user"),
                            username=c.get("username"),
                            text=c.get("text"),
                            zh=c.get("zh"),
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
