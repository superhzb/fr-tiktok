from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Channel(Base):
    __tablename__ = "channels"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, unique=True, nullable=False)
    url = Column(Text, nullable=False)
    added_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_checked_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    videos = relationship("Video", back_populates="channel")


class Video(Base):
    __tablename__ = "videos"

    id = Column(String, primary_key=True)
    channel_id = Column(Integer, ForeignKey("channels.id"), nullable=False)
    description = Column(Text)
    url = Column(Text)
    duration = Column(Integer)
    views = Column(Integer)
    likes = Column(Integer)
    comments_count = Column(Integer)
    shares = Column(Integer)
    author = Column(String)
    author_nickname = Column(String)
    music_title = Column(String)
    created_at = Column(DateTime)
    discovered_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    channel = relationship("Channel", back_populates="videos")
    comments = relationship(
        "Comment", back_populates="video", cascade="all, delete-orphan"
    )
    jobs = relationship("Job", back_populates="video", cascade="all, delete-orphan")
    watch_progress = relationship(
        "WatchProgress",
        back_populates="video",
        uselist=False,
        cascade="all, delete-orphan",
    )


class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(
        String, ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    user = Column(String)
    username = Column(String)
    text = Column(Text)
    zh = Column(Text)
    likes = Column(Integer)
    fetched_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    video = relationship("Video", back_populates="comments")


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(
        String, ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    status = Column(String, default="pending")
    current_step = Column(String, nullable=True)
    failed_step = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    video_path = Column(Text, nullable=True)
    srt_path = Column(Text, nullable=True)
    vtt_path = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    last_completed_step = Column(String, nullable=True)

    video = relationship("Video", back_populates="jobs")


class WatchProgress(Base):
    __tablename__ = "watch_progress"
    __table_args__ = (
        CheckConstraint(
            "play_percentage >= 0 AND play_percentage <= 100",
            name="ck_watch_progress_play_percentage",
        ),
    )

    video_id = Column(
        String, ForeignKey("videos.id", ondelete="CASCADE"), primary_key=True
    )
    play_percentage = Column(Integer, default=0)
    loop_count = Column(Integer, default=0)
    seen = Column(Boolean, default=False)
    saved_position = Column(Integer, default=0)
    updated_at = Column(DateTime, nullable=True)

    video = relationship("Video", back_populates="watch_progress")
