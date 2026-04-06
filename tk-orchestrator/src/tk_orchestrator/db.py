from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Generator

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    inspect,
    String,
    Text,
    create_engine,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship

from .config import Config


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
    comments = relationship("Comment", back_populates="video")
    jobs = relationship("Job", back_populates="video")


class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(String, ForeignKey("videos.id"), nullable=False)
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
    video_id = Column(String, ForeignKey("videos.id"), nullable=False)
    status = Column(String, default="pending")  # pending, running, interrupted, completed, failed
    current_step = Column(String, nullable=True)
    failed_step = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    video_path = Column(Text, nullable=True)
    srt_path = Column(Text, nullable=True)
    vtt_path = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    video = relationship("Video", back_populates="jobs")


_engine = None


def init_db(config: Config) -> None:
    global _engine
    db_url = f"sqlite:///{config.db_path.resolve()}"
    _engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(_engine)
    _ensure_comment_columns()


def _ensure_comment_columns() -> None:
    engine = get_engine()
    inspector = inspect(engine)
    if "comments" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("comments")}
    if "zh" not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE comments ADD COLUMN zh TEXT"))


def get_engine():
    if _engine is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _engine


@contextmanager
def get_session() -> Generator[Session, None, None]:
    session = Session(get_engine())
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
