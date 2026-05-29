# Phase 1: `models/` Module (Shared Contract)

**Owner**: Architect / Lead  
**Blocks**: All other phases (API, Scheduler, Worker) depend on this  
**Estimated scope**: ~5 files, no logic changes, pure data-layer extraction

---

## Context

The orchestrator is a monolithic Python package (`tk_orchestrator/`) that manages
a TikTok video subtitle pipeline. It currently has a single `db.py` file
containing all ORM models and session management. We are splitting the codebase
into 4 independent modules (`models/`, `api/`, `scheduler/`, `worker/`) so
different people can work on them without stepping on each other.

`models/` is the **shared contract** — the only package that all other modules
import from. It defines:

1. SQLAlchemy ORM tables (the database schema)
2. Pydantic response schemas (the API response shapes)
3. Session management (how to talk to the database)

This phase also introduces a new `WatchProgress` table to support a feature
where the backend tracks how much of each video the user has watched.

---

## What You Are Building

### Directory structure

```
src/tk_orchestrator/models/
├── __init__.py       # re-exports everything
├── tables.py         # all ORM classes (moved from db.py + new WatchProgress)
├── session.py        # init_db, get_session, get_engine (moved from db.py)
└── schemas.py        # Pydantic response models (new)
```

---

## Step-by-step

### 1.1 Create `models/tables.py`

Copy all ORM classes from the current `db.py` (lines 1–96) into this file.
Classes to move: `Base`, `Channel`, `Video`, `Comment`, `Job`.

**Changes to make while moving:**

1. Add `ondelete="CASCADE"` to every `ForeignKey` referencing `videos.id`,
   so that deleting a video automatically removes its comments, jobs, and
   watch progress:

```python
# In Comment:
video_id = Column(String, ForeignKey("videos.id", ondelete="CASCADE"), nullable=False)

# In Job:
video_id = Column(String, ForeignKey("videos.id", ondelete="CASCADE"), nullable=False)
```

2. Add `cascade="all, delete-orphan"` to Video's relationships:

```python
class Video(Base):
    __tablename__ = "videos"
    # ... existing columns unchanged ...

    channel = relationship("Channel", back_populates="videos")
    comments = relationship("Comment", back_populates="video", cascade="all, delete-orphan")
    jobs = relationship("Job", back_populates="video", cascade="all, delete-orphan")
    watch_progress = relationship("WatchProgress", back_populates="video", uselist=False, cascade="all, delete-orphan")
```

`watch_progress` is intentionally one-to-one: `uselist=False` on the ORM side,
and `WatchProgress.video_id` is the table's primary key, which enforces one
row per video at the database level.

3. Add the new `WatchProgress` table:

```python
from sqlalchemy import CheckConstraint


class WatchProgress(Base):
    __tablename__ = "watch_progress"
    __table_args__ = (
        CheckConstraint("play_percentage >= 0 AND play_percentage <= 100", name="ck_watch_progress_play_percentage"),
    )

    video_id = Column(String, ForeignKey("videos.id", ondelete="CASCADE"), primary_key=True)
    play_percentage = Column(Integer, default=0)    # 0–100, furthest point reached
    loop_count = Column(Integer, default=0)         # times watched >= 95%
    seen = Column(Boolean, default=False)           # True once watched to >= 95%
    saved_position = Column(Integer, default=0)     # seconds, where user left off
    updated_at = Column(DateTime, nullable=True)

    video = relationship("Video", back_populates="watch_progress")
```

4. Add `last_completed_step` column to `Job` (for pipeline resume improvement):

```python
class Job(Base):
    __tablename__ = "jobs"
    # ... existing columns ...
    last_completed_step = Column(String, nullable=True)   # NEW
```

**Do NOT change:** Column names, types, or defaults of any existing column.
The only additions are cascade rules, `WatchProgress`, and `last_completed_step`.

### 1.2 Create `models/session.py`

Move session management from `db.py` (lines 98–138). The import path for
`Config` changes from `.config` to `..config`.

```python
# models/session.py
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from ..config import Config
from .tables import Base

_engine = None


def init_db(config: Config) -> None:
    global _engine
    db_url = f"sqlite:///{config.db_path.resolve()}"
    _engine = create_engine(db_url, connect_args={"check_same_thread": False})

    # Enable SQLite foreign key enforcement (required for ON DELETE CASCADE).
    # The connect-event callback receives the raw DB-API SQLite connection, so
    # this PRAGMA should remain a plain SQL string rather than sqlalchemy.text().
    from sqlalchemy import event
    event.listen(_engine, "connect", lambda conn, _: conn.execute("PRAGMA foreign_keys=ON"))

    Base.metadata.create_all(_engine)
    _run_migrations()


def _run_migrations() -> None:
    """Add columns that may not exist in older databases."""
    engine = get_engine()
    inspector = inspect(engine)

    # comments.zh column (legacy migration)
    if "comments" in inspector.get_table_names():
        columns = {col["name"] for col in inspector.get_columns("comments")}
        if "zh" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE comments ADD COLUMN zh TEXT"))

    # jobs.last_completed_step column
    if "jobs" in inspector.get_table_names():
        columns = {col["name"] for col in inspector.get_columns("jobs")}
        if "last_completed_step" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE jobs ADD COLUMN last_completed_step TEXT"))


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
```

This migration is intentionally one-way. It upgrades older databases created by
the previous `db.py` layout, but mixed-version operation is not a target: once
newer code has added `jobs.last_completed_step`, running older application code
against that database is unsupported.

### 1.3 Create `models/schemas.py`

These are Pydantic models that define the API response shapes. Currently `api.py`
uses `_serialize_*` helper functions that return raw dicts. These schemas become
the contract between the API module and any consumer (frontend, CLI, tests).

```python
# models/schemas.py
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
    play_percentage: int = Field(ge=0, le=100)   # 0–100
    loop_count: int
    seen: bool
    saved_position: int    # seconds


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
    """VideoResponse with watch progress attached. Used by GET /feed."""
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
```

### 1.4 Create `models/__init__.py`

Re-export everything so other modules can do `from ..models import Channel, get_session, VideoResponse`:

```python
# models/__init__.py
from .tables import Base, Channel, Comment, Job, Video, WatchProgress
from .session import get_engine, get_session, init_db
from .schemas import (
    ChannelResponse,
    CommentResponse,
    FeedVideoResponse,
    JobResponse,
    VideoFilesResponse,
    VideoResponse,
    WatchProgressRequest,
    WatchProgressResponse,
)
```

### 1.5 Update all existing imports

Every file that currently does `from .db import ...` must change to
`from .models import ...`. This includes test files that currently import
`tk_orchestrator.db`. **Do not change any logic — only change the import
lines.**

| File | Old import | New import |
|------|-----------|------------|
| `api.py` | `from .db import Channel, Comment, Job, Video, get_session` | `from .models import Channel, Comment, Job, Video, get_session` |
| `pipeline.py` | `from .db import Job, get_session` | `from .models import Job, get_session` |
| `scheduler.py` | `from .db import Channel, Comment, Job, Video, get_session` | `from .models import Channel, Comment, Job, Video, get_session` |
| `queue.py` | `from .db import Job, get_session` | `from .models import Job, get_session` |
| `cli.py` | `from .db import Channel, Job, Video, get_session, init_db` | `from .models import Channel, Job, Video, get_session, init_db` |

Also update any tests that import `tk_orchestrator.db`, for example:
`tests/conftest.py`, `tests/test_api_validation.py`,
`tests/test_default_channels.py`, and `tests/test_interrupted_recovery.py`.

### 1.6 Delete `db.py`

Once all imports are updated and tests pass, delete `src/tk_orchestrator/db.py`.

---

## Rules

- `models/` must NOT import from `api/`, `scheduler/`, `worker/`, `cli`, or
  `pipeline`. It may only import from `config.py` and standard library / third-party.
- Do not add any business logic (no HTTP handlers, no scheduling, no pipeline steps).
- Do not rename any existing column or table. Only add new things.

---

## Verification Criteria

Run all of these from the repo root. Every one must pass before this phase is
considered done.

### V1: Package imports work

```bash
uv run --package tk-orchestrator python -c "
from tk_orchestrator.models import (
    Base, Channel, Comment, Job, Video, WatchProgress,
    get_engine, get_session, init_db,
    ChannelResponse, CommentResponse, FeedVideoResponse, JobResponse,
    VideoFilesResponse, VideoResponse, WatchProgressRequest, WatchProgressResponse,
)
print('All imports OK')
"
```

### V2: Old `db.py` is gone

```bash
test ! -f src/tk_orchestrator/db.py && echo "db.py removed OK"
```

### V3: No remaining references to old db module

```bash
# Must return nothing:
grep -r "from \.db import" src/tk_orchestrator/ && echo "FAIL: old imports remain" || echo "OK: no old imports"
grep -r "from \.\.db import" src/tk_orchestrator/ && echo "FAIL: old imports remain" || echo "OK: no old imports"
```

### V4: Database tables are created correctly (including new ones)

```bash
uv run --package tk-orchestrator python -c "
from pathlib import Path
from tk_orchestrator.config import Config
from tk_orchestrator.models import init_db, get_engine
from sqlalchemy import inspect

config = Config(db_path=Path('/tmp/test_phase1.db'))
init_db(config)
inspector = inspect(get_engine())
tables = set(inspector.get_table_names())
expected = {'channels', 'videos', 'comments', 'jobs', 'watch_progress'}
assert expected.issubset(tables), f'Missing tables: {expected - tables}'

# Check cascade-related columns
job_cols = {c['name'] for c in inspector.get_columns('jobs')}
assert 'last_completed_step' in job_cols, 'Missing last_completed_step column'

wp_cols = {c['name'] for c in inspector.get_columns('watch_progress')}
assert 'play_percentage' in wp_cols, 'Missing play_percentage column'
assert 'saved_position' in wp_cols, 'Missing saved_position column'

print('All tables and columns OK')
"
rm -f /tmp/test_phase1.db
```

### V5: CASCADE delete works

```bash
uv run --package tk-orchestrator python -c "
from pathlib import Path
from tk_orchestrator.config import Config
from tk_orchestrator.models import (
    init_db, get_session, Channel, Video, Comment, Job, WatchProgress,
)

config = Config(db_path=Path('/tmp/test_phase1_cascade.db'))
init_db(config)

# Create test data
with get_session() as s:
    ch = Channel(username='testuser', url='https://tiktok.com/@testuser')
    s.add(ch)
    s.flush()
    v = Video(id='123', channel_id=ch.id, url='https://example.com')
    s.add(v)
    s.flush()
    s.add(Comment(video_id='123', text='hello'))
    s.add(Job(video_id='123', status='completed'))
    s.add(WatchProgress(video_id='123', play_percentage=50))

# Delete the video — cascades should remove comment, job, watch_progress
with get_session() as s:
    v = s.get(Video, '123')
    s.delete(v)

# Verify everything is gone
with get_session() as s:
    assert s.query(Comment).filter(Comment.video_id == '123').count() == 0
    assert s.query(Job).filter(Job.video_id == '123').count() == 0
    assert s.get(WatchProgress, '123') is None
    print('CASCADE delete OK')
"
rm -f /tmp/test_phase1_cascade.db
```

### V6: Pydantic schemas serialize correctly

```bash
uv run --package tk-orchestrator python -c "
from tk_orchestrator.models import (
    WatchProgressRequest, WatchProgressResponse, FeedVideoResponse, VideoFilesResponse,
)

# Test request validation
req = WatchProgressRequest(play_percentage=75, loop_count=2, seen=True, saved_position=30)
assert req.play_percentage == 75

# Test response serialization
resp = WatchProgressResponse(
    video_id='123', play_percentage=75, loop_count=2,
    seen=True, saved_position=30, updated_at=None,
)
d = resp.model_dump(mode='json')
assert d['video_id'] == '123'
assert d['play_percentage'] == 75

# Test FeedVideoResponse with nested watch_progress
feed = FeedVideoResponse(
    id='123', channel_id=1, channel_username='test', description=None,
    url=None, duration=60, views=100, likes=10, comments_count=5,
    shares=2, author='a', author_nickname='a', music_title=None,
    created_at=None, discovered_at=None,
    files=VideoFilesResponse(),
    watch_progress=resp,
)
d = feed.model_dump(mode='json')
assert d['watch_progress']['play_percentage'] == 75
print('Pydantic schemas OK')
"
```

### V7: Existing tests still pass

```bash
uv run --package tk-orchestrator pytest
```

### V8: Server starts and basic endpoints respond

```bash
# Start server in background, hit it, then kill
uv run --package tk-orchestrator tk-orch start &
SERVER_PID=$!
sleep 3
curl -sf http://localhost:19099/health | python3 -m json.tool
curl -sf http://localhost:19099/channels | python3 -m json.tool
curl -sf http://localhost:19099/videos | python3 -m json.tool
kill $SERVER_PID
```

---

## What Other Modules Will Depend On

After this phase, the other three modules will import exclusively from
`tk_orchestrator.models`. Here is what each needs:

| Consumer | Imports |
|----------|---------|
| **api/** | `Channel, Comment, Job, Video, WatchProgress, get_session` + all `*Response` and `*Request` schemas |
| **scheduler/** | `Channel, Comment, Job, Video, get_session` |
| **worker/** | `Job, get_session` |
| **cli.py** | `Channel, Job, Video, get_session, init_db` |
