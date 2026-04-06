from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Path as FastAPIPath, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, StringConstraints, field_validator
from sqlalchemy import text

from .config import Config
from .db import Channel, Comment, Job, Video, get_session

app = FastAPI(title="tk-orchestrator", version="0.1.0")
logger = logging.getLogger(__name__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_config: Config | None = None
_scheduler = None


@app.middleware("http")
async def log_requests(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - started) * 1000
    logger.info(
        'API %s %s -> %d in %.1fms',
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


def configure(config: Config) -> None:
    """Set config and mount static output directory."""
    global _config
    _config = config
    output_dir = config.output_dir.resolve()
    if output_dir.is_dir():
        app.mount("/output", StaticFiles(directory=str(output_dir)), name="output")


def register_scheduler(scheduler) -> None:
    """Expose the live scheduler instance to API endpoints."""
    global _scheduler
    _scheduler = scheduler


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


def _scheduler_state_name(state: int | None) -> str:
    if state == 1:
        return "running"
    if state == 2:
        return "paused"
    if state == 0:
        return "stopped"
    return "unknown"


def _scheduler_health() -> dict:
    if _scheduler is None:
        return {"status": "not_configured", "running": False, "jobs": 0}

    jobs = _scheduler.get_jobs()
    next_run_time = None
    if jobs:
        next_run = min((job.next_run_time for job in jobs if job.next_run_time), default=None)
        if next_run is not None:
            next_run_time = next_run.isoformat()

    return {
        "status": _scheduler_state_name(getattr(_scheduler, "state", None)),
        "running": bool(getattr(_scheduler, "running", False)),
        "jobs": len(jobs),
        "next_run_time": next_run_time,
    }


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


# ── helpers ──────────────────────────────────────────────────────────────────


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
    """Resolve output file paths for a video into API-serveable URLs."""
    channel_username = v.channel.username if v.channel else v.author
    video_dir = _output_dir() / channel_username / v.id
    result: dict = {"video_url": None, "vtt_url": None, "srt_url": None}
    if not video_dir.is_dir():
        return result
    mp4s = list(video_dir.glob("*.mp4"))
    if mp4s:
        result["video_url"] = f"/output/{channel_username}/{v.id}/{mp4s[0].name}"
    vtt = video_dir / "subtitles.vtt"
    if vtt.exists():
        result["vtt_url"] = f"/output/{channel_username}/{v.id}/subtitles.vtt"
    srt = video_dir / "subtitles.srt"
    if srt.exists():
        result["srt_url"] = f"/output/{channel_username}/{v.id}/subtitles.srt"
    return result


# ── channels ─────────────────────────────────────────────────────────────────


@app.get("/health")
async def health_check():
    db = _db_health()
    scheduler = _scheduler_health()
    if db["status"] != "ok":
        overall_status = "error"
        status_code = 503
    elif _scheduler is not None and not scheduler["running"]:
        overall_status = "degraded"
        status_code = 503
    else:
        overall_status = "ok"
        status_code = 200

    return JSONResponse(
        status_code=status_code,
        content={
            "status": overall_status,
            "service": "tk-orchestrator",
            "database": db,
            "scheduler": scheduler,
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
    ]
):
    username = username.lstrip("@")
    with get_session() as s:
        c = s.query(Channel).filter(Channel.username == username).first()
        if not c:
            raise HTTPException(404, "Channel not found")
        return _serialize_channel(c)


# ── videos ───────────────────────────────────────────────────────────────────


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
    ]
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
    ]
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
    ]
):
    with get_session() as s:
        v = s.query(Video).filter(Video.id == video_id).first()
        if not v:
            raise HTTPException(404, "Video not found")
        return _video_files(v)


# ── jobs ─────────────────────────────────────────────────────────────────────


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
