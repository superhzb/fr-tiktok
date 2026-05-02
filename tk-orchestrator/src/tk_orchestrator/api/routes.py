from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Path as FastAPIPath, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, StringConstraints, field_validator
from sqlalchemy import text
from sqlalchemy.orm import joinedload

from ..config import Config
from ..models import (
    Channel,
    Comment,
    Job,
    Video,
    WatchProgress,
    get_session,
    VideoResponse,
    VideoFilesResponse,
    FeedVideoResponse,
    WatchProgressRequest,
    WatchProgressResponse,
)
from ..video_retention import delete_video_and_files

app = FastAPI(title="tk-orchestrator", version="0.1.0")
logger = logging.getLogger(__name__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_config: Config | None = None


@app.middleware("http")
async def log_requests(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - started) * 1000
    logger.info(
        "API %s %s -> %d in %.1fms",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


def configure(config: Config) -> None:
    global _config
    _config = config
    output_dir = config.output_dir.resolve()
    if output_dir.is_dir():
        app.mount("/output", StaticFiles(directory=str(output_dir)), name="output")


def _output_dir() -> Path:
    if _config is None:
        return Path("./output").resolve()
    return _config.output_dir.resolve()


def _db_health() -> dict:
    try:
        with get_session() as session:
            session.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


VideoId = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^\d{1,32}$"),
]
Username = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^@?[A-Za-z0-9._-]{1,64}$"),
]
JobStatus = Literal["pending", "running", "interrupted", "completed", "failed"]


class VideoListQuery(BaseModel):
    channel: Username | None = None
    status: JobStatus | None = None

    @field_validator("channel")
    @classmethod
    def normalize_channel(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.lstrip("@")


def _serialize_channel(c: Channel) -> dict:
    return {
        "id": c.id,
        "username": c.username,
        "url": c.url,
        "added_at": c.added_at.isoformat() if c.added_at else None,
        "last_checked_at": c.last_checked_at.isoformat() if c.last_checked_at else None,
        "is_active": c.is_active,
    }


def _serialize_video(v: Video) -> dict:
    return {
        "id": v.id,
        "channel_id": v.channel_id,
        "description": v.description,
        "url": v.url,
        "duration": v.duration,
        "views": v.views,
        "likes": v.likes,
        "comments_count": v.comments_count,
        "shares": v.shares,
        "author": v.author,
        "author_nickname": v.author_nickname,
        "music_title": v.music_title,
        "created_at": v.created_at.isoformat() if v.created_at else None,
        "discovered_at": v.discovered_at.isoformat() if v.discovered_at else None,
    }


def _serialize_comment(c: Comment) -> dict:
    return {
        "id": c.id,
        "video_id": c.video_id,
        "user": c.user,
        "username": c.username,
        "text": c.text,
        "zh": c.zh,
        "likes": c.likes,
    }


def _serialize_job(j: Job) -> dict:
    return {
        "id": j.id,
        "video_id": j.video_id,
        "status": j.status,
        "current_step": j.current_step,
        "failed_step": j.failed_step,
        "error_message": j.error_message,
        "video_path": j.video_path,
        "srt_path": j.srt_path,
        "vtt_path": j.vtt_path,
        "created_at": j.created_at.isoformat() if j.created_at else None,
        "started_at": j.started_at.isoformat() if j.started_at else None,
        "completed_at": j.completed_at.isoformat() if j.completed_at else None,
    }


def _video_files(v: Video) -> dict:
    channel_username = v.channel.username if v.channel else v.author
    video_dir = _output_dir() / channel_username / v.id
    result: dict = {"video_url": None, "vtt_url": None, "srt_url": None}
    if not video_dir.is_dir():
        return result
    mp4 = next(video_dir.glob("*.mp4"), None)
    if mp4:
        result["video_url"] = f"/output/{channel_username}/{v.id}/{mp4.name}"
    vtt = video_dir / "subtitles.vtt"
    if vtt.exists():
        result["vtt_url"] = f"/output/{channel_username}/{v.id}/subtitles.vtt"
    srt = video_dir / "subtitles.srt"
    if srt.exists():
        result["srt_url"] = f"/output/{channel_username}/{v.id}/subtitles.srt"
    return result


@app.get("/health")
async def health_check():
    db = _db_health()
    status_code = 200 if db["status"] == "ok" else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ok" if db["status"] == "ok" else "error",
            "service": "tk-orchestrator",
            "database": db,
        },
    )


@app.get("/channels")
async def list_channels():
    with get_session() as s:
        channels = s.query(Channel).all()
        return [_serialize_channel(c) for c in channels]


@app.get("/channels/{username}")
async def get_channel(
    username: Annotated[
        Username,
        FastAPIPath(description="TikTok username, with or without a leading @"),
    ],
):
    username = username.lstrip("@")
    with get_session() as s:
        c = s.query(Channel).filter(Channel.username == username).first()
        if not c:
            raise HTTPException(404, "Channel not found")
        return _serialize_channel(c)


@app.get("/videos")
async def list_videos(filters: Annotated[VideoListQuery, Query()]):
    with get_session() as s:
        q = s.query(Video)
        if filters.channel:
            q = q.join(Channel).filter(Channel.username == filters.channel)
        if filters.status:
            q = q.join(Job).filter(Job.status == filters.status)
        videos = q.order_by(Video.created_at.desc()).all()
        result = []
        for v in videos:
            data = _serialize_video(v)
            data["files"] = _video_files(v)
            data["channel_username"] = v.channel.username if v.channel else None
            result.append(data)
        return result


@app.get("/videos/{video_id}")
async def get_video(
    video_id: Annotated[
        VideoId,
        FastAPIPath(description="Numeric TikTok video ID"),
    ],
):
    with get_session() as s:
        v = s.query(Video).filter(Video.id == video_id).first()
        if not v:
            raise HTTPException(404, "Video not found")
        data = _serialize_video(v)
        data["files"] = _video_files(v)
        data["channel_username"] = v.channel.username if v.channel else None
        return data


@app.get("/videos/{video_id}/comments")
async def get_video_comments(
    video_id: Annotated[
        VideoId,
        FastAPIPath(description="Numeric TikTok video ID"),
    ],
):
    with get_session() as s:
        v = s.query(Video).filter(Video.id == video_id).first()
        if not v:
            raise HTTPException(404, "Video not found")
        comments = (
            s.query(Comment)
            .filter(Comment.video_id == video_id)
            .order_by(Comment.likes.desc())
            .all()
        )
        return [_serialize_comment(c) for c in comments]


@app.get("/videos/{video_id}/subtitles")
async def get_video_subtitles(
    video_id: Annotated[
        VideoId,
        FastAPIPath(description="Numeric TikTok video ID"),
    ],
):
    with get_session() as s:
        v = s.query(Video).filter(Video.id == video_id).first()
        if not v:
            raise HTTPException(404, "Video not found")
        return _video_files(v)


@app.get("/jobs")
async def list_jobs():
    with get_session() as s:
        jobs = s.query(Job).order_by(Job.created_at.desc()).limit(50).all()
        return [_serialize_job(j) for j in jobs]


@app.get("/jobs/{job_id}")
async def get_job(job_id: int):
    with get_session() as s:
        j = s.query(Job).filter(Job.id == job_id).first()
        if not j:
            raise HTTPException(404, "Job not found")
        return _serialize_job(j)


@app.get("/feed")
async def feed(
    limit: Annotated[int | None, Query(ge=1, le=100)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    with get_session() as s:
        completed_video_ids = (
            s.query(Job.video_id)
            .filter(Job.status == "completed")
            .distinct()
            .subquery()
        )

        videos = (
            s.query(Video, WatchProgress)
            .options(joinedload(Video.channel))
            .filter(Video.id.in_(s.query(completed_video_ids.c.video_id)))
            .outerjoin(WatchProgress, Video.id == WatchProgress.video_id)
            .all()
        )

        result = []
        for v, wp in videos:
            data = _serialize_video(v)
            data["files"] = _video_files(v)
            data["channel_username"] = v.channel.username if v.channel else None
            data["watch_progress"] = (
                {
                    "video_id": wp.video_id,
                    "play_percentage": wp.play_percentage,
                    "loop_count": wp.loop_count,
                    "seen": wp.seen,
                    "saved_position": wp.saved_position,
                    "updated_at": wp.updated_at.isoformat() if wp.updated_at else None,
                }
                if wp
                else None
            )
            result.append(data)

        def feed_sort_key(item):
            wp = item.get("watch_progress")
            pct = wp["play_percentage"] if wp else 0
            loops = wp["loop_count"] if wp else 0

            if pct == 0:
                tier = 0
            elif loops == 0:
                tier = 1
            else:
                tier = 2

            if tier == 0:
                da = item.get("discovered_at")
                ts = datetime.fromisoformat(da).timestamp() if da else 0
                return (tier, ts)
            elif tier == 1:
                return (tier, pct)
            else:
                return (tier, loops)

        result.sort(key=feed_sort_key)
        if offset:
            result = result[offset:]
        if limit is not None:
            result = result[:limit]
        return result


@app.get("/progress")
async def list_progress():
    with get_session() as s:
        records = s.query(WatchProgress).all()
        return [
            {
                "video_id": wp.video_id,
                "play_percentage": wp.play_percentage,
                "loop_count": wp.loop_count,
                "seen": wp.seen,
                "saved_position": wp.saved_position,
                "updated_at": wp.updated_at.isoformat() if wp.updated_at else None,
            }
            for wp in records
        ]


@app.put("/videos/{video_id}/progress")
async def update_progress(
    video_id: Annotated[VideoId, FastAPIPath(description="Numeric TikTok video ID")],
    body: WatchProgressRequest,
):
    with get_session() as s:
        v = s.query(Video).filter(Video.id == video_id).first()
        if not v:
            raise HTTPException(404, "Video not found")

        wp = s.get(WatchProgress, video_id)
        if wp:
            wp.play_percentage = body.play_percentage
            wp.loop_count = body.loop_count
            wp.seen = body.seen
            wp.saved_position = body.saved_position
            wp.updated_at = datetime.now(timezone.utc)
        else:
            wp = WatchProgress(
                video_id=video_id,
                play_percentage=body.play_percentage,
                loop_count=body.loop_count,
                seen=body.seen,
                saved_position=body.saved_position,
                updated_at=datetime.now(timezone.utc),
            )
            s.add(wp)

    return {"status": "ok", "video_id": video_id}


@app.delete("/videos/{video_id}")
async def delete_video(
    video_id: Annotated[VideoId, FastAPIPath(description="Numeric TikTok video ID")],
):
    with get_session() as s:
        v = s.query(Video).filter(Video.id == video_id).first()
        if not v:
            raise HTTPException(404, "Video not found")

    deleted = delete_video_and_files(video_id, _output_dir())
    if not deleted:
        raise HTTPException(404, "Video not found")
    return {"status": "deleted", "video_id": video_id}
