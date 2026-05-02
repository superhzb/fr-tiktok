from __future__ import annotations

import dataclasses
import json
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import or_

from ..config import Config
from ..models import (
    Channel,
    Comment,
    DeletedVideo,
    Job,
    Video,
    WatchProgress,
    get_session,
)
from ..video_retention import delete_video_and_files
from .subprocess import run_cli

logger = logging.getLogger(__name__)

_checker_log = logging.getLogger("tk_orchestrator.scheduler.channel_checker")
_comments_log = logging.getLogger("tk_orchestrator.scheduler.comments")


@dataclasses.dataclass
class PollResult:
    job_ids: list[int]
    reason: str
    channel_video_total: int
    total_video_total: int


async def _run_channel_checker_count(channel_url: str, count: int) -> list[dict]:
    try:
        stdout = await run_cli(
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


def _video_is_deleted(video_id: str) -> bool:
    with get_session() as s:
        return s.get(DeletedVideo, video_id) is not None


def _channel_video_count(channel_id: int) -> int:
    with get_session() as s:
        return s.query(Video).filter(Video.channel_id == channel_id).count()


def _total_video_count() -> int:
    with get_session() as s:
        return s.query(Video).count()


def _watched_video_count() -> int:
    with get_session() as s:
        return (
            s.query(Video)
            .join(WatchProgress, Video.id == WatchProgress.video_id)
            .filter(
                or_(
                    WatchProgress.seen.is_(True),
                    WatchProgress.loop_count >= 1,
                )
            )
            .count()
        )


def _watched_ratio() -> float:
    total = _total_video_count()
    if total == 0:
        return 0.0
    return _watched_video_count() / total


def _select_retention_candidates(config: Config, limit: int) -> list[str]:
    with get_session() as s:
        watched_completed = (
            s.query(Video)
            .join(WatchProgress, Video.id == WatchProgress.video_id)
            .join(Job, Job.video_id == Video.id)
            .filter(Job.status == "completed")
            .filter(
                or_(
                    WatchProgress.seen.is_(True),
                    WatchProgress.loop_count >= 1,
                )
            )
            .distinct()
            .all()
        )

        channel_newest: dict[int, set[str]] = {}
        for v in watched_completed:
            newest_videos = (
                s.query(Video)
                .filter(Video.channel_id == v.channel_id)
                .order_by(Video.discovered_at.desc())
                .limit(config.retention_keep_newest_per_channel)
                .all()
            )
            channel_newest[v.channel_id] = {nv.id for nv in newest_videos}

        eligible = []
        for v in watched_completed:
            if v.id in channel_newest.get(v.channel_id, set()):
                continue
            if config.retention_min_age_hours > 0 and v.discovered_at:
                discovered = v.discovered_at
                if discovered.tzinfo is None:
                    discovered = discovered.replace(tzinfo=timezone.utc)
                age_hours = (
                    datetime.now(timezone.utc) - discovered
                ).total_seconds() / 3600
                if age_hours < config.retention_min_age_hours:
                    continue
            eligible.append(v)

        _NAIVE_MIN = datetime.min

        def _sort_key(v: Video):
            wp = v.watch_progress
            loops = -(wp.loop_count or 0) if wp else 0
            updated = wp.updated_at if wp and wp.updated_at else _NAIVE_MIN
            if updated.tzinfo is not None:
                updated = updated.replace(tzinfo=None)
            discovered = v.discovered_at or _NAIVE_MIN
            if discovered.tzinfo is not None:
                discovered = discovered.replace(tzinfo=None)
            return (loops, updated, discovered)

        eligible.sort(key=_sort_key)

        return [v.id for v in eligible[:limit]]


def _run_retention_if_needed(config: Config) -> int:
    if not config.retention_enabled:
        return 0

    total = _total_video_count()
    if total == 0:
        return 0

    watched = _watched_video_count()
    ratio = watched / total

    logger.info(
        "Retention evaluation: total=%d watched=%d ratio=%.2f threshold=%.2f",
        total,
        watched,
        ratio,
        config.retention_watched_ratio_threshold,
    )

    if ratio < config.retention_watched_ratio_threshold:
        logger.info(
            "Retention skipped: ratio %.2f below threshold %.2f",
            ratio,
            config.retention_watched_ratio_threshold,
        )
        return 0

    candidates = _select_retention_candidates(
        config, config.retention_delete_batch_size
    )
    logger.info("Retention candidates: %d", len(candidates))

    deleted = 0
    output_dir = config.output_dir.resolve()
    for video_id in candidates:
        if delete_video_and_files(video_id, output_dir):
            deleted += 1
            logger.info("Retention deleted video %s", video_id)

    logger.info("Retention completed: deleted=%d", deleted)
    return deleted


async def _find_new_videos(channel_url: str, config: Config) -> list[dict]:
    """Return up to ``videos_per_poll`` unseen videos, walking newest to oldest."""
    target_new_videos = max(config.videos_per_poll, 1)
    per_channel_limit = max(config.max_videos_per_channel, 1)
    total_scan_limit = max(config.max_videos_total, per_channel_limit)
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
            if not _video_exists(video_id) and not _video_is_deleted(video_id):
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
        stdout = await run_cli(
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
                "tk-batch-translate",
                "comments",
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

            await run_cli(cmd, _comments_log)
            return json.loads(output_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error("tk-comment-translator failed: %s", e)
        return comments


async def poll_channel(
    channel_id: int, username: str, channel_url: str, config: Config
) -> PollResult:
    """Poll one channel. Returns job IDs for newly discovered videos."""
    logger.info("Polling @%s", username)
    per_channel_limit = max(config.max_videos_per_channel, 1)
    total_video_limit = max(config.max_videos_total, per_channel_limit)
    channel_video_total = _channel_video_count(channel_id)
    total_video_total = _total_video_count()
    logger.info(
        "Channel state @%s: stored_channel_videos=%d/%d stored_total_videos=%d/%d videos_per_poll=%d",
        username,
        channel_video_total,
        per_channel_limit,
        total_video_total,
        total_video_limit,
        max(config.videos_per_poll, 1),
    )
    if channel_video_total >= per_channel_limit:
        logger.info(
            "Skipping @%s: channel has reached stored video limit (%d/%d)",
            username,
            channel_video_total,
            per_channel_limit,
        )
        return PollResult(
            [], "channel_limit_reached", channel_video_total, total_video_total
        )

    if total_video_total >= total_video_limit:
        logger.info(
            "Skipping @%s: global stored video limit reached (%d/%d)",
            username,
            total_video_total,
            total_video_limit,
        )
        return PollResult(
            [], "total_limit_reached", channel_video_total, total_video_total
        )

    videos = await _find_new_videos(channel_url, config)
    if not videos:
        logger.info(
            "No unseen videos discovered for @%s within this poll window",
            username,
        )
        return PollResult([], "no_new_videos", channel_video_total, total_video_total)

    new_job_ids: list[int] = []

    for v in videos:
        is_new = False
        new_job_id: int | None = None

        with get_session() as s:
            existing = s.get(Video, v["id"])
            deleted = s.get(DeletedVideo, v["id"])
            if existing:
                existing.views = v.get("views")
                existing.likes = v.get("likes")
                existing.comments_count = v.get("comments")
                existing.shares = v.get("shares")
            elif deleted:
                logger.info("Skipping deleted video %s (@%s)", v["id"], username)
            else:
                if channel_video_total >= per_channel_limit:
                    logger.info(
                        "Stopping @%s: channel stored video limit reached during poll (%d/%d)",
                        username,
                        channel_video_total,
                        per_channel_limit,
                    )
                    return PollResult(
                        new_job_ids,
                        "channel_limit_reached",
                        channel_video_total,
                        total_video_total,
                    )

                if total_video_total >= total_video_limit:
                    logger.info(
                        "Stopping @%s: global stored video limit reached during poll (%d/%d)",
                        username,
                        total_video_total,
                        total_video_limit,
                    )
                    return PollResult(
                        new_job_ids,
                        "total_limit_reached",
                        channel_video_total,
                        total_video_total,
                    )

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
                channel_video_total += 1
                total_video_total += 1
                logger.info(
                    "Stored new video %s for @%s and created job %d; stored_channel_videos=%d/%d stored_total_videos=%d/%d",
                    v["id"],
                    username,
                    new_job_id,
                    channel_video_total,
                    per_channel_limit,
                    total_video_total,
                    total_video_limit,
                )

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

    logger.info(
        "Poll result @%s: created_jobs=%d stored_channel_videos=%d/%d stored_total_videos=%d/%d",
        username,
        len(new_job_ids),
        channel_video_total,
        per_channel_limit,
        total_video_total,
        total_video_limit,
    )
    return PollResult(
        new_job_ids, "created_jobs", channel_video_total, total_video_total
    )


async def poll_all_channels(config: Config) -> None:
    """Check all active channels for new videos."""
    logger.info("Scheduler tick: polling channels")
    with get_session() as s:
        channels = s.query(Channel).filter(Channel.is_active == True).all()
        channel_infos = [(c.id, c.username, c.url) for c in channels]
        total_videos = s.query(Video).count()

    logger.info(
        "Scheduler state: active_channels=%d stored_total_videos=%d/%d videos_per_poll=%d",
        len(channel_infos),
        total_videos,
        max(config.max_videos_total, max(config.max_videos_per_channel, 1)),
        max(config.videos_per_poll, 1),
    )

    _run_retention_if_needed(config)

    for channel_id, username, channel_url in channel_infos:
        result = await poll_channel(channel_id, username, channel_url, config)
        logger.info(
            "Scheduler channel summary @%s: reason=%s enqueued_jobs=%d stored_channel_videos=%d stored_total_videos=%d",
            username,
            result.reason,
            len(result.job_ids),
            result.channel_video_total,
            result.total_video_total,
        )


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
