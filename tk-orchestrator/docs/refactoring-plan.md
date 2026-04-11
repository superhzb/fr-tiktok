# tk-orchestrator Refactoring Plan (Overview)

> **This is the overview document.** Detailed, self-contained plans for each
> module are in separate files so they can be assigned to different people:
>
> | Phase | Doc | Owner | Blocks |
> |-------|-----|-------|--------|
> | 1. models/ | [phase1-models.md](phase1-models.md) | Architect / Lead | All other phases |
> | 2. api/ | [phase2-api.md](phase2-api.md) | API developer | — |
> | 3. scheduler/ | [phase3-scheduler.md](phase3-scheduler.md) | Scheduler developer | — |
> | 4. worker/ | [phase4-worker.md](phase4-worker.md) | Worker developer | — |
>
> Phases 2, 3, 4 can run **in parallel** once Phase 1 is complete.
>
> **New feature integrated**: The `watched_percent` feature
> ([feature_watched_percent.md](feature_watched_percent.md)) is incorporated
> into Phase 1 (new `WatchProgress` table + schemas) and Phase 2 (new API
> endpoints: `/feed`, `/progress`, `DELETE /videos/{id}`). Phases 3 and 4
> are unaffected by this feature.

## Goal

Split the current monolithic orchestrator into **4 internal modules** with clear
boundaries so each can be assigned to a different person. They share the same
package but never import each other — only `models/`.

```
tk-orchestrator/src/tk_orchestrator/
├── models/        ← shared contract (DB tables + Pydantic response schemas)
├── api/           ← HTTP server (reads DB, serves files)
├── scheduler/     ← channel polling + comment fetching (writes DB)
├── worker/        ← pipeline execution (reads/writes DB + filesystem)
├── cli.py         ← thin CLI that wires modules together
├── config.py      ← unchanged
└── logging_config.py  ← unchanged
```

**The rule**: `api/` never imports from `scheduler/` or `worker/`.
`scheduler/` never imports from `api/` or `worker/`. `worker/` never imports
from `api/` or `scheduler/`. All three import only from `models/` and `config`.

---

## Current Cross-Module Imports (What We're Untangling)

```
cli.py  ──→  config, db, logging_config, api, queue, scheduler, pipeline
api.py  ──→  config, db
             also holds reference to scheduler (for health check)
scheduler.py ──→  config, db, pipeline.run_cmd, queue.enqueue
queue.py     ──→  config, db, pipeline.run_pipeline
pipeline.py  ──→  config, db, logging_config
```

Problems:
- `scheduler.py` imports `pipeline.run_cmd` (just to call CLI subprocess)
- `scheduler.py` imports `queue.enqueue` (direct function call coupling)
- `queue.py` imports `pipeline.run_pipeline` (worker is fused with queue)
- `api.py` holds live `_scheduler` reference (for health endpoint)

---

## Phase 1: Extract `models/` (the shared contract)

**Why first**: Every other phase depends on this. Once `models/` exists with
Pydantic response schemas, all three modules can be developed independently
against the same contract.

### Step 1.1: Create the models directory

```
mkdir -p src/tk_orchestrator/models/
touch src/tk_orchestrator/models/__init__.py
```

### Step 1.2: Move ORM tables from `db.py` → `models/tables.py`

Create `models/tables.py` with these classes copied from `db.py`:

```python
# models/tables.py
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, String, Text, create_engine,
)
from sqlalchemy.orm import DeclarativeBase, relationship

class Base(DeclarativeBase):
    pass

class Channel(Base):     # exact copy from db.py
class Video(Base):       # exact copy from db.py
class Comment(Base):     # exact copy from db.py
class Job(Base):         # exact copy from db.py
```

### Step 1.3: Move session management from `db.py` → `models/session.py`

```python
# models/session.py
from contextlib import contextmanager
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
    Base.metadata.create_all(_engine)
    _ensure_comment_columns()

def _ensure_comment_columns() -> None:
    # exact copy from db.py
    ...

def get_engine():
    if _engine is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _engine

@contextmanager
def get_session() -> Generator[Session, None, None]:
    # exact copy from db.py
    ...
```

### Step 1.4: Create Pydantic response schemas in `models/schemas.py`

These are the API response shapes. Currently `api.py` uses `_serialize_*`
helper functions that return raw dicts. Replace those with explicit Pydantic
models:

```python
# models/schemas.py
from pydantic import BaseModel
from datetime import datetime

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
    video_url: str | None
    vtt_url: str | None
    srt_url: str | None

class VideoResponse(BaseModel):
    id: str
    channel_username: str
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
    files: VideoFilesResponse

    class Config:
        from_attributes = True

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

### Step 1.5: Re-export everything from `models/__init__.py`

```python
# models/__init__.py
from .tables import Base, Channel, Comment, Job, Video
from .session import get_engine, get_session, init_db
from .schemas import (
    ChannelResponse, CommentResponse, JobResponse,
    VideoFilesResponse, VideoResponse,
)
```

### Step 1.6: Delete old `db.py`, update all imports

Find every file that does `from .db import ...` and change to
`from .models import ...`. Files to update:

- `api.py` — change `from .db import Channel, Comment, Job, Video, get_session`
  → `from .models import Channel, Comment, Job, Video, get_session`
- `pipeline.py` — change `from .db import Job, get_session`
  → `from .models import Job, get_session`
- `scheduler.py` — change `from .db import Channel, Comment, Job, Video, get_session`
  → `from .models import Channel, Comment, Job, Video, get_session`
- `queue.py` — change `from .db import Job, get_session`
  → `from .models import Job, get_session`
- `cli.py` — change `from .db import Channel, Job, Video, get_session, init_db`
  → `from .models import Channel, Job, Video, get_session, init_db`

### Step 1.7: Verify

```bash
# Run from repo root
uv run --package tk-orchestrator python -c "from tk_orchestrator.models import Channel, Video, Job, Comment, get_session, init_db"

# Run existing tests
uv run --package tk-orchestrator pytest
```

**Checkpoint**: All existing behavior works exactly the same. We only moved
code and added Pydantic schemas. No logic changes.

---

## Phase 2: Extract `api/` module

### Step 2.1: Create directory

```
mkdir -p src/tk_orchestrator/api/
touch src/tk_orchestrator/api/__init__.py
```

### Step 2.2: Move `api.py` → `api/routes.py`

Copy the current `api.py` to `api/routes.py`. Then make these changes:

**Change all imports**:
```python
# OLD
from .config import Config
from .db import Channel, Comment, Job, Video, get_session

# NEW
from ..config import Config
from ..models import Channel, Comment, Job, Video, get_session
from ..models import (
    ChannelResponse, CommentResponse, JobResponse, VideoResponse,
    VideoFilesResponse,
)
```

**Replace `_serialize_*` functions with Pydantic models**:

Instead of `_serialize_video(v)` returning a hand-built dict, use:
```python
def _build_video_response(v: Video) -> dict:
    return VideoResponse(
        id=v.id,
        channel_username=v.channel.username if v.channel else "",
        description=v.description,
        url=v.url,
        duration=v.duration,
        views=v.views,
        likes=v.likes,
        comments_count=v.comments_count,
        shares=v.shares,
        author=v.author,
        author_nickname=v.author_nickname,
        music_title=v.music_title,
        created_at=v.created_at,
        files=_video_files(v),
    ).model_dump(mode="json")
```

Do the same for Channel, Comment, Job.

**Remove scheduler health check coupling**:

The current `_scheduler_health()` function accesses the live `_scheduler`
object. Replace this with a simple status endpoint that reads from the DB:

```python
# REMOVE these:
_scheduler = None
def register_scheduler(scheduler) -> None: ...
def _scheduler_health() -> dict: ...

# REPLACE the health endpoint with:
@app.get("/health")
async def health_check():
    db_ok = _db_health()
    return JSONResponse({"status": "ok" if db_ok["status"] == "ok" else "degraded",
                         "db": db_ok})
```

If you still want scheduler health info, add a `scheduler_heartbeat` column to
the config or a simple `heartbeat` table that the scheduler writes to every
cycle. The API reads that row — no live object reference needed.

### Step 2.3: Create `api/__init__.py`

```python
# api/__init__.py
from .routes import app, configure
```

### Step 2.4: Update `cli.py` imports

```python
# OLD
from .api import app, configure, register_scheduler

# NEW
from .api import app, configure
# remove register_scheduler call from _start_async()
```

### Step 2.5: Verify

```bash
uv run --package tk-orchestrator tk-orch start
# Hit http://localhost:8000/health
# Hit http://localhost:8000/videos
# Hit http://localhost:8000/channels
```

**Checkpoint**: API works the same, except `/health` no longer reports scheduler
state (we'll add a DB-based heartbeat in Phase 3).

---

## Phase 3: Extract `scheduler/` module

### Step 3.1: Create directory

```
mkdir -p src/tk_orchestrator/scheduler/
touch src/tk_orchestrator/scheduler/__init__.py
```

### Step 3.2: Move `scheduler.py` → `scheduler/polling.py`

Copy `scheduler.py` to `scheduler/polling.py`. Make these changes:

**Fix imports**:
```python
# OLD
from .config import Config
from .db import Channel, Comment, Job, Video, get_session
from .pipeline import run_cmd    # ← problem: imports from pipeline
from .queue import enqueue       # ← problem: imports from queue

# NEW
from ..config import Config
from ..models import Channel, Comment, Job, Video, get_session
```

**Remove the `run_cmd` import**:

The scheduler uses `pipeline.run_cmd` only to execute `tk-channel-checker` and
`tk-comments` CLI commands. But `run_cmd` is a general subprocess runner — it
doesn't belong in `pipeline`. Copy a local version into the scheduler module:

```python
# scheduler/subprocess.py
import asyncio
import logging

async def run_cli(cmd: list[str], logger: logging.Logger) -> str:
    """Run a CLI command and return its stdout. Raise on failure."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_bytes, stderr_bytes = await proc.communicate()
    if stderr_bytes:
        for line in stderr_bytes.decode(errors="replace").splitlines():
            logger.info("[stderr] %s", line)
    if proc.returncode != 0:
        raise RuntimeError(
            f"{cmd[0]} exited with code {proc.returncode}"
        )
    return stdout_bytes.decode(errors="replace")
```

Then in `polling.py`:
```python
from .subprocess import run_cli
# replace all run_cmd(...) calls with run_cli(...)
```

**Remove the `enqueue` import**:

Instead of directly calling `queue.enqueue(job_id)`, the scheduler should just
write `Job(status="pending")` to the database. The worker polls for pending
jobs. Change `poll_channel()`:

```python
# OLD (in poll_channel):
from .queue import enqueue
# ... later:
enqueue(job.id)

# NEW (in poll_channel):
# Just create the Job with status="pending" — the worker will pick it up.
# Remove the enqueue() call entirely.
# The job is already created with status="pending" by default in the existing
# code, so you just need to delete the enqueue() line.
```

**Add heartbeat**:

At the end of `poll_all_channels()`, write a heartbeat timestamp so the API
can report scheduler health without a live reference:

```python
# At the bottom of poll_all_channels():
from ..models import get_session
from datetime import datetime, timezone

with get_session() as s:
    s.execute(text(
        "INSERT OR REPLACE INTO heartbeats (name, last_beat) VALUES ('scheduler', :ts)"
    ), {"ts": datetime.now(timezone.utc).isoformat()})
```

(You'll need to add a `heartbeats` table to `models/tables.py` — a simple
key-value: `name TEXT PRIMARY KEY, last_beat TEXT`.)

### Step 3.3: Create `scheduler/__init__.py`

```python
# scheduler/__init__.py
from .polling import poll_all_channels, poll_channel, setup_scheduler
```

### Step 3.4: Update `cli.py` imports

```python
# OLD
from .scheduler import setup_scheduler

# NEW
from .scheduler import setup_scheduler
# (path stays the same thanks to __init__.py re-export)
```

### Step 3.5: Verify

```bash
uv run --package tk-orchestrator tk-orch start
# Watch logs — scheduler should poll channels and create Job rows
# Verify: SELECT * FROM jobs WHERE status='pending' shows new jobs
```

---

## Phase 4: Extract `worker/` module

### Step 4.1: Create directory

```
mkdir -p src/tk_orchestrator/worker/
touch src/tk_orchestrator/worker/__init__.py
```

### Step 4.2: Move `pipeline.py` → `worker/pipeline.py`

Copy `pipeline.py` to `worker/pipeline.py`. Fix imports:

```python
# OLD
from .config import Config
from .db import Job, get_session
from .logging_config import get_job_logger, remove_job_logger

# NEW
from ..config import Config
from ..models import Job, get_session
from ..logging_config import get_job_logger, remove_job_logger
```

No other changes needed — `pipeline.py` already only imports from `config`,
`db`, and `logging_config`.

### Step 4.3: Move `queue.py` → `worker/queue.py`

Copy `queue.py` to `worker/queue.py`. Fix imports:

```python
# OLD
from .config import Config
from .db import Job, get_session
from .pipeline import run_pipeline

# NEW
from ..config import Config
from ..models import Job, get_session
from .pipeline import run_pipeline  # now a local import within worker/
```

**Change the worker to poll the DB instead of using asyncio.Queue**:

The current worker uses `asyncio.Queue` which requires the scheduler to call
`enqueue()` directly. Replace with DB polling:

```python
# worker/queue.py
import asyncio
import logging
from ..config import Config
from ..models import Job, get_session
from .pipeline import run_pipeline

logger = logging.getLogger(__name__)

async def worker(config: Config) -> None:
    """Poll for pending jobs and run them one at a time."""
    logger.info("Worker started — polling for pending jobs")
    while True:
        job_id = _claim_next_job()
        if job_id:
            logger.info("Claimed job %d", job_id)
            try:
                await run_pipeline(job_id, config)
            except Exception:
                logger.exception("Job %d failed unexpectedly", job_id)
        else:
            await asyncio.sleep(5)  # no pending jobs, wait 5 seconds

def _claim_next_job() -> int | None:
    """Atomically claim the oldest pending job. Returns job_id or None."""
    with get_session() as s:
        job = (
            s.query(Job)
            .filter(Job.status.in_(("pending", "interrupted")))
            .order_by(Job.created_at)
            .first()
        )
        if job:
            job.status = "running"
            job_id = job.id
            return job_id
    return None

def recover_interrupted_jobs() -> list[int]:
    """Mark any 'running' jobs as 'interrupted' so the worker will retry them."""
    with get_session() as s:
        stuck = s.query(Job).filter(Job.status == "running").all()
        ids = []
        for j in stuck:
            j.status = "interrupted"
            ids.append(j.id)
        return ids
```

### Step 4.4: Add `last_completed_step` to Job table

This replaces the fragile file-existence-based resume logic.

In `models/tables.py`, add a column to `Job`:

```python
class Job(Base):
    __tablename__ = "jobs"
    # ... existing columns ...
    last_completed_step = Column(String, nullable=True)  # NEW
```

In `models/session.py`, add a migration (similar to `_ensure_comment_columns`):

```python
def _ensure_job_columns() -> None:
    engine = get_engine()
    inspector = inspect(engine)
    if "jobs" not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns("jobs")}
    if "last_completed_step" not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE jobs ADD COLUMN last_completed_step TEXT"))
```

Call `_ensure_job_columns()` at the end of `init_db()`.

Then in `worker/pipeline.py`, after each step succeeds:

```python
# After download step completes:
with get_session() as s:
    j = s.get(Job, job_id)
    j.last_completed_step = "download"

# After stt step completes:
with get_session() as s:
    j = s.get(Job, job_id)
    j.last_completed_step = "stt"

# ... and so on for each step
```

And replace `_resolve_resume_step()` with:

```python
PIPELINE_STEPS = ("download", "stt", "punctuation", "alignment", "srt_merge", "translation")

def _get_resume_step(job_last_completed: str | None) -> str:
    """Return the next step after the last completed one."""
    if job_last_completed is None:
        return "download"
    idx = PIPELINE_STEPS.index(job_last_completed)
    if idx + 1 >= len(PIPELINE_STEPS):
        return "done"
    return PIPELINE_STEPS[idx + 1]
```

### Step 4.5: Create `worker/__init__.py`

```python
# worker/__init__.py
from .queue import worker, recover_interrupted_jobs
from .pipeline import run_pipeline
```

### Step 4.6: Update `cli.py`

```python
# OLD
from .queue import recover_interrupted_jobs, worker, enqueue
from .pipeline import run_pipeline

# NEW
from .worker import recover_interrupted_jobs, worker, run_pipeline
```

In `_start_async()`, remove the `enqueue` setup. The worker now polls
the DB — no explicit enqueue needed.

In `channel_check` and `run` commands that directly call `run_pipeline`,
the import path changes but usage stays the same.

### Step 4.7: Verify

```bash
# Terminal 1: start the server (scheduler + worker + api)
uv run --package tk-orchestrator tk-orch start

# Terminal 2: manually add a video
uv run --package tk-orchestrator tk-orch run https://www.tiktok.com/@someone/video/12345

# Watch Terminal 1 logs: worker should pick up the pending job within 5 seconds
```

---

## Phase 5: Clean up `cli.py`

After phases 1–4, `cli.py` should only import from:

```python
from .config import Config, load_config
from .models import Channel, Job, Video, get_session, init_db
from .logging_config import setup_logging
from .api import app, configure
from .scheduler import setup_scheduler
from .worker import recover_interrupted_jobs, worker, run_pipeline
```

`cli.py` is the **integration point** — it's the only file that knows about
all three modules. This is correct. It wires them together at startup.

### Step 5.1: Simplify `_start_async()`

```python
async def _start_async(config: Config, host: str, port: int) -> None:
    _seed_default_channels(config)
    recovered = recover_interrupted_jobs()
    if recovered:
        click.echo(f"Recovered {len(recovered)} interrupted jobs")

    scheduler = setup_scheduler(config)
    scheduler.start()

    configure(config)
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, ...))
    await asyncio.gather(worker(config), server.serve())
```

No `register_scheduler()`, no `enqueue()`. Clean.

### Step 5.2: Delete old files

```bash
rm src/tk_orchestrator/db.py        # replaced by models/
rm src/tk_orchestrator/api.py       # replaced by api/
rm src/tk_orchestrator/scheduler.py # replaced by scheduler/
rm src/tk_orchestrator/queue.py     # replaced by worker/
rm src/tk_orchestrator/pipeline.py  # replaced by worker/
```

---

## Phase 6: Verify final structure

### Expected directory tree

```
src/tk_orchestrator/
├── __init__.py
├── __main__.py
├── cli.py                        ← integration + CLI commands
├── config.py                     ← unchanged
├── logging_config.py             ← unchanged
├── models/
│   ├── __init__.py               ← re-exports everything
│   ├── tables.py                 ← Channel, Video, Comment, Job ORM classes
│   ├── session.py                ← init_db, get_session, get_engine
│   └── schemas.py                ← Pydantic response models
├── api/
│   ├── __init__.py               ← re-exports app, configure
│   └── routes.py                 ← FastAPI endpoints (reads DB only)
├── scheduler/
│   ├── __init__.py               ← re-exports setup_scheduler
│   ├── polling.py                ← poll_channel, poll_all_channels
│   └── subprocess.py             ← run_cli() helper
└── worker/
    ├── __init__.py               ← re-exports worker, run_pipeline
    ├── pipeline.py               ← 6-step pipeline execution
    └── queue.py                  ← DB-polling worker loop
```

### Import dependency diagram (final)

```
cli.py ──→ config, models, logging_config, api, scheduler, worker

api/routes.py ──→ config, models              ✓ no cross-module imports
scheduler/polling.py ──→ config, models       ✓ no cross-module imports
worker/pipeline.py ──→ config, models, logging_config  ✓ no cross-module imports
worker/queue.py ──→ config, models, worker/pipeline    ✓ internal only
```

### Verification checklist

```bash
# 1. Server starts and all features work
uv run --package tk-orchestrator tk-orch start

# 2. API responds
curl http://localhost:8000/health
curl http://localhost:8000/channels
curl http://localhost:8000/videos

# 3. CLI commands work
uv run --package tk-orchestrator tk-orch channel list
uv run --package tk-orchestrator tk-orch jobs

# 4. Scheduler polls (watch logs for "Polling channel ...")
# Wait for poll_interval_seconds (default 60)

# 5. Worker processes jobs (watch logs for "Claimed job ...")
# Add a video and verify it processes:
uv run --package tk-orchestrator tk-orch channel check <username>

# 6. Pipeline resumes correctly
# Kill the server mid-pipeline (Ctrl+C)
# Restart: uv run --package tk-orchestrator tk-orch start
# Verify worker picks up the interrupted job and resumes from correct step

# 7. No cross-module imports
# This should return nothing:
grep -r "from \.\.api" src/tk_orchestrator/scheduler/ src/tk_orchestrator/worker/
grep -r "from \.\.scheduler" src/tk_orchestrator/api/ src/tk_orchestrator/worker/
grep -r "from \.\.worker" src/tk_orchestrator/api/ src/tk_orchestrator/scheduler/
```

---

## Summary: What Each Team Member Needs to Know

| Person | Owns | Must understand | Never needs to touch |
|--------|------|-----------------|----------------------|
| **API dev** | `api/` | `models/` (schemas + tables), FastAPI | `scheduler/`, `worker/`, pipeline steps |
| **Scheduler dev** | `scheduler/` | `models/` (tables), config.yaml channels, `tk-channel-checker` CLI, `tk-comments` CLI | `api/`, `worker/`, pipeline steps |
| **Worker dev** | `worker/` | `models/` (tables + Job lifecycle), all `tk-*` CLI tools, `logging_config` | `api/`, `scheduler/` |
| **You (architect)** | `cli.py`, `models/`, `config.py` | Everything (but you only write glue code) | — |
