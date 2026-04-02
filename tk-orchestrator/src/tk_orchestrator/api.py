from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="tk-orchestrator", version="0.1.0")

_NOT_IMPLEMENTED = {"status": "not implemented"}


@app.get("/channels")
async def list_channels():
    return _NOT_IMPLEMENTED


@app.get("/channels/{username}")
async def get_channel(username: str):
    return _NOT_IMPLEMENTED


@app.get("/videos")
async def list_videos(channel: str | None = None, status: str | None = None):
    return _NOT_IMPLEMENTED


@app.get("/videos/{video_id}")
async def get_video(video_id: str):
    return _NOT_IMPLEMENTED


@app.get("/videos/{video_id}/comments")
async def get_video_comments(video_id: str):
    return _NOT_IMPLEMENTED


@app.get("/videos/{video_id}/subtitles")
async def get_video_subtitles(video_id: str):
    return _NOT_IMPLEMENTED


@app.get("/jobs")
async def list_jobs():
    return _NOT_IMPLEMENTED


@app.get("/jobs/{job_id}")
async def get_job(job_id: int):
    return _NOT_IMPLEMENTED
