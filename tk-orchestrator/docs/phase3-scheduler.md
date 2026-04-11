# Phase 3: `scheduler/` Module (Channel Polling)

**Owner**: Scheduler developer  
**Depends on**: Phase 1 (`models/`) must be complete  
**Does NOT touch**: `api/`, `worker/`, `pipeline.py`, `queue.py`

---

## Context

You are building the scheduler module for a TikTok video subtitle orchestrator.
The orchestrator monitors TikTok channels, discovers new videos, fetches and
translates their comments, and creates pipeline jobs for subtitle generation.

The scheduler module is responsible for:
- Periodically polling all active channels for new videos
- Running external CLI tools (`tk-channel-checker`, `tk-comments`,
  `tk-batch-translate`) to discover videos and fetch comments
- Writing new `Video`, `Comment`, and `Job` rows to the database
- **That's it.** The scheduler does NOT process videos (the worker does that)
  and does NOT serve HTTP (the API does that).

**The rule**: `scheduler/` imports only from `models/` and `config`. It must
NEVER import from `api/`, `worker/`, `pipeline`, or `queue`.

---

## What Already Exists

The current `scheduler.py` is a single file that:

1. Polls channels on a timer using APScheduler
2. Discovers new videos via `tk-channel-checker` CLI
3. Creates Video + Job records in the DB
4. Fetches and translates comments via `tk-comments` and `tk-batch-translate` CLIs
5. Calls `queue.enqueue(job_id)` to send jobs to the worker **<-- THIS MUST CHANGE**
6. Calls `pipeline.run_cmd()` to execute CLI subprocesses **<-- THIS MUST CHANGE**

Problems with the current code:
- `from .pipeline import run_cmd` — imports from the pipeline module just
  to run CLI subprocesses. This is a cross-module dependency.
- `from .queue import enqueue` — directly pushes jobs into the worker's
  asyncio.Queue. This is a cross-module dependency.

---

## What You Are Building

### Directory structure

```
src/tk_orchestrator/scheduler/
├── __init__.py        # re-exports: setup_scheduler, poll_channel, poll_all_channels
├── polling.py         # channel polling logic (moved from scheduler.py)
└── subprocess.py      # local run_cli() helper (replaces pipeline.run_cmd import)
```

---

## Step-by-step

### 3.1 Create `scheduler/subprocess.py`

The current code imports `run_cmd` from `pipeline.py` to run CLI tools. You
need a local copy that does the same thing. This is the `run_cmd` function
from the current `pipeline.py` (lines 56–111) — copy it as `run_cli`:

```python
# scheduler/subprocess.py
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import suppress


async def run_cli(
    cmd: list[str],
    job_logger: logging.Logger,
    *,
    extra_env: dict[str, str] | None = None,
) -> str:
    """Run a subprocess, stream stderr to the logger, and return stdout.

    Raises RuntimeError on non-zero exit code.
    """
    job_logger.debug("$ %s", " ".join(cmd))
    run_env = {**os.environ, **(extra_env or {})}
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=run_env,
    )
    stderr_lines: list[str] = []

    async def _drain_stderr() -> None:
        assert proc.stderr
        async for raw in proc.stderr:
            line = raw.decode().rstrip()
            stderr_lines.append(line)
            job_logger.debug("[stderr] %s", line)

    drain_task = asyncio.create_task(_drain_stderr())
    stdout_bytes = b""
    try:
        assert proc.stdout
        stdout_bytes = await proc.stdout.read()
        await drain_task
        await proc.wait()
    except asyncio.CancelledError:
        job_logger.warning("Command interrupted, terminating subprocess")
        if proc.returncode is None:
            with suppress(ProcessLookupError):
                proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                with suppress(ProcessLookupError):
                    proc.kill()
                await proc.wait()
        drain_task.cancel()
        with suppress(asyncio.CancelledError):
            await drain_task
        raise

    if proc.returncode != 0:
        raise RuntimeError(
            "\n".join(stderr_lines) or f"process exited with code {proc.returncode}"
        )

    return stdout_bytes.decode().strip()
```

### 3.2 Create `scheduler/polling.py`

Copy the current `scheduler.py` into `scheduler/polling.py`. Then make these
changes:

**Fix imports:**

```python
# OLD
from .config import Config
from .db import Channel, Comment, Job, Video, get_session
from .pipeline import run_cmd
from .queue import enqueue

# NEW
from ..config import Config
from ..models import Channel, Comment, Job, Video, get_session
from .subprocess import run_cli
```

**Replace `run_cmd` with `run_cli`:**

In functions `_run_channel_checker_count` and `_run_comments` and
`_translate_comments`, change all `run_cmd(...)` calls to `run_cli(...)`.
The signature is identical so this is a pure rename.

**Remove the `enqueue` call:**

In `poll_all_channels()`, the current code calls `enqueue(job_id)` after
polling each channel. **Remove this entirely.** The worker module will poll
the database for pending jobs on its own.

Current code (lines 329–332 of scheduler.py):

```python
# CURRENT — DELETE the enqueue call:
for job_id in result.job_ids:
    enqueue(job_id)
```

The scheduler already creates `Job(status="pending")` rows in `poll_channel()`.
That's the handoff. The worker picks up pending jobs by querying the DB.

**Everything else stays the same.** The polling logic, video discovery,
comment fetching, and comment translation are all unchanged.

### 3.3 Create `scheduler/__init__.py`

```python
# scheduler/__init__.py
from .polling import poll_all_channels, poll_channel, setup_scheduler
```

### 3.4 Delete old `scheduler.py`

Once the module is working, delete `src/tk_orchestrator/scheduler.py`.

### 3.5 Update `cli.py` imports

The import path for `poll_channel` in `cli.py`'s `_channel_check_async()`
function stays the same thanks to the `__init__.py` re-export:

```python
from .scheduler import poll_channel  # still works
```

But verify that `cli.py`'s `_start_async()` import also works:

```python
from .scheduler import setup_scheduler  # still works
```

---

## External CLI tools you call

These are the CLI tools the scheduler invokes via subprocess. You do not need
to understand their internals — you just need to know the interface:

| Tool | Invocation | Returns |
|------|-----------|---------|
| `tk-channel-checker` | `tk-channel-checker <channel_url> --count <N>` | JSON array of video metadata objects on stdout |
| `tk-comments` | `tk-comments <video_url> --count <N>` | JSON array of comment objects on stdout |
| `tk-batch-translate` | `tk-batch-translate comments <input.json> --output <output.json> --model <model> --batch-size <N> [--description <file>]` | Writes translated JSON to output file |

Video metadata object shape (from `tk-channel-checker`):

```json
{
    "id": "7234567890123456789",
    "url": "https://www.tiktok.com/@user/video/7234567890123456789",
    "desc": "Video description text",
    "duration": 45,
    "views": 12000,
    "likes": 500,
    "comments": 30,
    "shares": 10,
    "author": "username",
    "author_nickname": "Display Name",
    "music_title": "Song Title",
    "create_date": "2025-01-15T12:00:00"
}
```

Comment object shape (from `tk-comments`):

```json
{
    "user": "Display Name",
    "username": "handle",
    "text": "Original comment text",
    "likes": 42
}
```

After translation, comments gain a `"zh"` field with the Chinese translation.

---

## Database tables you write to

You need to understand these tables (defined in `models/tables.py`):

**Channel** — you read `id`, `username`, `url`, `is_active` and write
`last_checked_at` after polling.

**Video** — you create new rows when discovering unseen videos. Primary key
is the TikTok video ID string.

**Comment** — you create new rows after fetching and translating comments.

**Job** — you create new rows with `status="pending"` for each new video.
You do NOT modify job status after creation — the worker handles that.

---

## Config fields you use

From `Config` (defined in `config.py`):

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `poll_interval_seconds` | int | 60 | How often to run `poll_all_channels` |
| `videos_per_poll` | int | 1 | Max new videos to discover per channel per poll |
| `max_videos_per_channel` | int | 20 | Stop polling if channel has this many stored videos |
| `max_videos_total` | int | 200 | Stop polling if total stored videos reaches this |
| `comment_count` | int | 10 | How many comments to fetch per video |
| `translate_model` | str | `mlx-community/...` | Model name passed to `tk-batch-translate` |
| `translate_batch_size` | int | 10 | Batch size passed to `tk-batch-translate` |

---

## Rules

- `scheduler/` imports only from `models/` and `config`. Never from `api/`,
  `worker/`, `pipeline`, or `queue`.
- The scheduler communicates with the worker ONLY through the database. It
  creates `Job(status="pending")` rows. It never calls `enqueue()` or any
  worker function.
- The scheduler does not modify `Job.status` after creation. Once the job is
  created with `status="pending"`, the worker owns its lifecycle.

---

## Verification Criteria

### V1: Module imports work

```bash
uv run --package tk-orchestrator python -c "
from tk_orchestrator.scheduler import setup_scheduler, poll_channel, poll_all_channels
print('scheduler imports OK')
"
```

### V2: Old scheduler.py is gone

```bash
test ! -f src/tk_orchestrator/scheduler.py && echo "scheduler.py removed OK"
```

### V3: No cross-module imports

```bash
# Must return nothing:
grep -r "from \.\.api" src/tk_orchestrator/scheduler/ && echo "FAIL" || echo "OK: no api import"
grep -r "from \.\.worker" src/tk_orchestrator/scheduler/ && echo "FAIL" || echo "OK: no worker import"
grep -r "from \.\.pipeline" src/tk_orchestrator/scheduler/ && echo "FAIL" || echo "OK: no pipeline import"
grep -r "from \.\.queue" src/tk_orchestrator/scheduler/ && echo "FAIL" || echo "OK: no queue import"
```

### V4: No enqueue calls remain

```bash
grep -r "enqueue" src/tk_orchestrator/scheduler/ && echo "FAIL: enqueue still referenced" || echo "OK: no enqueue"
```

### V5: run_cli works (subprocess helper)

```bash
uv run --package tk-orchestrator python -c "
import asyncio, logging
from tk_orchestrator.scheduler.subprocess import run_cli

async def test():
    logger = logging.getLogger('test')
    # 'echo' should work on any system
    result = await run_cli(['echo', 'hello world'], logger)
    assert result.strip() == 'hello world', f'Got: {result}'
    print('run_cli OK')

asyncio.run(test())
"
```

### V6: Scheduler creates pending jobs (no enqueue)

```bash
uv run --package tk-orchestrator python -c "
from pathlib import Path
from tk_orchestrator.config import Config
from tk_orchestrator.models import init_db, get_session, Channel, Job

config = Config(db_path=Path('/tmp/test_phase3.db'))
init_db(config)

# Seed a channel
with get_session() as s:
    s.add(Channel(username='testchannel', url='https://www.tiktok.com/@testchannel'))

# We can't actually call poll_channel without tk-channel-checker installed,
# but we can verify the module loads and the scheduler sets up without error.
from tk_orchestrator.scheduler import setup_scheduler
scheduler = setup_scheduler(config)
jobs = scheduler.get_jobs()
assert len(jobs) == 1, f'Expected 1 scheduled job, got {len(jobs)}'
assert jobs[0].id == 'poll_channels'
print('Scheduler setup OK (1 interval job configured)')
"
rm -f /tmp/test_phase3.db
```

### V7: Server starts with the refactored scheduler

```bash
uv run --package tk-orchestrator tk-orch start &
SERVER_PID=$!
sleep 3

# Health check should work
curl -sf http://localhost:8000/health | python3 -m json.tool

# If you have channels configured, watch the logs for "Polling @..." messages
# after poll_interval_seconds (default 60s)

kill $SERVER_PID
```

### V8: Manual channel check still works (CLI)

```bash
# If you have a channel in the DB:
uv run --package tk-orchestrator tk-orch channel list
# Then check a specific channel:
# uv run --package tk-orchestrator tk-orch channel check <username>
```

### V9: Existing tests still pass

```bash
uv run --package tk-orchestrator pytest
```
