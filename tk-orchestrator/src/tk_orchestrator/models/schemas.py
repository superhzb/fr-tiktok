from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ChannelResponse(BaseModel):
    id: int
    username: str
    url: str
    added_at: datetime | None
    last_checked_at: datetime | None
    is_active: bool

    class Config:
        from_attributes = True


class VideoFilesResponse(BaseModel):
    video_url: str | None = None
    vtt_url: str | None = None
    srt_url: str | None = None


class WatchProgressResponse(BaseModel):
    video_id: str
    play_percentage: int
    loop_count: int
    seen: bool
    saved_position: int
    updated_at: datetime | None

    class Config:
        from_attributes = True


class WatchProgressRequest(BaseModel):
    play_percentage: int = Field(ge=0, le=100)
    loop_count: int
    seen: bool
    saved_position: int


class VideoResponse(BaseModel):
    id: str
    channel_id: int
    channel_username: str | None
    description: str | None
    url: str | None
    duration: int | None
    views: int | None
    likes: int | None
    comments_count: int | None
    shares: int | None
    author: str | None
    author_nickname: str | None
    music_title: str | None
    created_at: datetime | None
    discovered_at: datetime | None
    files: VideoFilesResponse

    class Config:
        from_attributes = True


class FeedVideoResponse(VideoResponse):
    watch_progress: WatchProgressResponse | None = None


class CommentResponse(BaseModel):
    id: int
    video_id: str
    user: str | None
    username: str | None
    text: str | None
    zh: str | None
    likes: int | None

    class Config:
        from_attributes = True


class JobResponse(BaseModel):
    id: int
    video_id: str
    status: str
    current_step: str | None
    last_completed_step: str | None
    failed_step: str | None
    error_message: str | None
    video_path: str | None
    srt_path: str | None
    vtt_path: str | None
    created_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None

    class Config:
        from_attributes = True
