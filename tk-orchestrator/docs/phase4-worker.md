# Phase 4: `worker/` Module (Pipeline Execution)

**Owner**: Worker / pipeline developer  
**Depends on**: Phase 1 (`models/`) must be complete  
**Does NOT touch**: `api/`, `scheduler/`

---

## Context

You are building the worker module for a TikTok video subtitle orchestrator.
The orchestrator downloads TikTok videos and generates bilingual subtitles
through a 6-step pipeline of external CLI tools.

The worker module is responsible for:
- Picking up pending jobs from the database
- Running the 6-step subtitle pipeline for each job
- Tracking pipeline progress and handling failures/interruptions
- Recovering interrupted jobs on restart

**The rule**: `worker/` imports only from `models/`, `config`, and
`logging_config`. It must NEVER import from `api/` or `scheduler/`.

---

## What Already Exists

Two files are being merged into this module:

### `pipeline.py` (the 6-step pipeline)

Runs external CLI tools in sequence for a given job:

1. **download** — `tk-down` downloads the MP4
2. **stt** — `tk-stt` transcribes speech to text
3. **punctuation** — `tk-punctuation` adds punctuation
4. **alignment** — `tk-aligner` aligns words to timestamps
5. **srt_merge** — `tk-srt-merger` generates SRT subtitles
6. **translation** — `tk-batch-translate` translates to bilingual VTT

Each step updates `job.current_step` in the DB. On failure it records
`failed_step` and `error_message`. On interruption (CancelledError) it marks
the job as `interrupted` so it can be resumed.

### `queue.py` (the worker loop)

Currently uses `asyncio.Queue` — the scheduler calls `enqueue(job_id)` to push
jobs, and the worker coroutine pops them. **This changes**: the worker will
poll the database for pending jobs instead, removing the direct dependency
between scheduler and worker.

---

## What You Are Building

### Directory structure

```
src/tk_orchestrator/worker/
├── __init__.py      # re-exports: worker, run_pipeline, recover_interrupted_jobs
├── pipeline.py      # 6-step pipeline (moved from pipeline.py)
└── queue.py         # DB-polling worker loop (rewritten from queue.py)
```

---

## Step-by-step

### 4.1 Create `worker/pipeline.py`

Copy the current `pipeline.py` into `worker/pipeline.py`. Make these changes:

**Fix imports** (relative paths change because we're one level deeper):

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

**Add `last_completed_step` tracking.** After each pipeline step succeeds,
record it in the DB so we know exactly where to resume. Add this after each
successful step:

```python
# After download step succeeds (around line where video_path is saved):
with get_session() as s:
    j = s.get(Job, job_id)
    if j:
        j.video_path = str(video_path)
        j.last_completed_step = "download"

# After stt step succeeds:
with get_session() as s:
    j = s.get(Job, job_id)
    if j:
        j.last_completed_step = "stt"

# After punctuation step succeeds:
with get_session() as s:
    j = s.get(Job, job_id)
    if j:
        j.last_completed_step = "punctuation"

# After alignment step succeeds:
with get_session() as s:
    j = s.get(Job, job_id)
    if j:
        j.last_completed_step = "alignment"

# After srt_merge step succeeds:
with get_session() as s:
    j = s.get(Job, job_id)
    if j:
        j.srt_path = str(srt_path)
        j.last_completed_step = "srt_merge"

# After translation step succeeds:
with get_session() as s:
    j = s.get(Job, job_id)
    if j:
        j.vtt_path = str(vtt_path)
        j.last_completed_step = "translation"
```

**Improve `_resolve_resume_step` to use `last_completed_step`:**

The current resume logic checks for file existence to determine which step to
resume from. This is fragile — files might exist but be incomplete. Use the
new `last_completed_step` column as the primary signal, with file checks as
fallback for old jobs that don't have it set:

```python
def _resolve_resume_step(job_snapshot, video_dir: Path) -> str:
    """Determine which step to resume from."""
    # Primary: use last_completed_step if available
    last_done = getattr(job_snapshot, "last_completed_step", None)
    if last_done and last_done in PIPELINE_STEPS:
        idx = PIPELINE_STEPS.index(last_done)
        if idx + 1 < len(PIPELINE_STEPS):
            return PIPELINE_STEPS[idx + 1]
        return PIPELINE_STEPS[-1]  # all done, run last step again

    # Fallback: existing file-based logic for old jobs without last_completed_step
    if job_snapshot.current_step in PIPELINE_STEPS and job_snapshot.status in {"running", "interrupted"}:
        return job_snapshot.current_step

    video_path = Path(job_snapshot.video_path) if job_snapshot.video_path else None
    raw_json = video_dir / "raw_transcription.json"
    punctuated_json = video_dir / "punctuated.json"
    aligned_json = video_dir / "aligned.json"
    srt_path = Path(job_snapshot.srt_path) if job_snapshot.srt_path else video_dir / "subtitles.srt"

    if srt_path.exists():
        return "translation"
    if aligned_json.exists() and punctuated_json.exists():
        return "srt_merge"
    if punctuated_json.exists() and video_path and video_path.exists():
        return "alignment"
    if raw_json.exists() and video_path and video_path.exists():
        return "punctuation"
    if video_path and video_path.exists():
        return "stt"
    return "download"
```

Also add `last_completed_step` to the `_JobSnapshot` class in `run_pipeline()`:

```python
class _JobSnapshot:
    current_step = job_current_step
    status = job_status
    video_path = job_video_path
    srt_path = job_srt_path
    last_completed_step = job_last_completed_step  # NEW — read from DB
```

And read it from the initial session:

```python
with get_session() as s:
    job = s.get(Job, job_id)
    # ... existing field reads ...
    job_last_completed_step = job.last_completed_step  # NEW
```

**Everything else stays the same**: the `run_cmd` helper, the step execution
logic, error handling, logging.

### 4.2 Create `worker/queue.py`

**This is a rewrite**, not a copy. The current `queue.py` uses `asyncio.Queue`
which requires the scheduler to call `enqueue()`. Replace with DB polling:

```python
# worker/queue.py
from __future__ import annotations

import asyncio
import logging

from ..config import Config
from ..models import Job, get_session
from .pipeline import run_pipeline

logger = logging.getLogger(__name__)


async def worker(config: Config) -> None:
    """Poll for pending jobs and process them one at a time."""
    logger.info("Worker started — polling for pending jobs")
    while True:
        job_id = _claim_next_job()
        if job_id:
            logger.info("Claimed job %d", job_id)
            try:
                await run_pipeline(job_id, config)
            except Exception:
                logger.exception("Unexpected error processing job %d", job_id)
        else:
            await asyncio.sleep(5)  # no pending jobs, wait 5 seconds


def _claim_next_job() -> int | None:
    """Atomically claim the oldest pending/interrupted job. Returns job_id or None."""
    with get_session() as s:
        job = (
            s.query(Job)
            .filter(Job.status.in_(("pending", "interrupted")))
            .order_by(Job.created_at.asc(), Job.id.asc())
            .first()
        )
        if job:
            job.status = "running"
            return job.id
    return None


def recover_interrupted_jobs() -> list[int]:
    """Mark any 'running' jobs as 'interrupted' so the worker will pick them up.

    Called once at startup to handle jobs that were running when the process
    was killed.
    """
    with get_session() as s:
        stuck = (
            s.query(Job)
            .filter(Job.status == "running")
            .order_by(Job.created_at.asc(), Job.id.asc())
            .all()
        )
        ids = []
        for j in stuck:
            j.status = "interrupted"
            if not j.error_message:
                j.error_message = "Interrupted during previous shutdown"
            logger.warning(
                "Recovered stale running job %d as interrupted at step %s",
                j.id,
                j.current_step or "download",
            )
            ids.append(j.id)
        return ids
```

Key differences from the old `queue.py`:
- No `asyncio.Queue`, no `enqueue()` function
- Worker polls DB every 5 seconds for `pending` or `interrupted` jobs
- `_claim_next_job()` atomically claims a job by setting status to `running`
- `recover_interrupted_jobs()` no longer calls `enqueue()` — it just marks
  running jobs as interrupted, and the worker loop will find them naturally

### 4.3 Create `worker/__init__.py`

```python
# worker/__init__.py
from .queue import worker, recover_interrupted_jobs
from .pipeline import run_pipeline
```

### 4.4 Delete old files

Once the module is working, delete:

```bash
rm src/tk_orchestrator/pipeline.py
rm src/tk_orchestrator/queue.py
```

### 4.5 Update `cli.py` imports

In `cli.py`, update the imports:

```python
# In _start_async():
# OLD
from .api import app, configure, register_scheduler
from .queue import recover_interrupted_jobs, worker
from .scheduler import setup_scheduler

# NEW
from .api import app, configure
from .worker import recover_interrupted_jobs, worker
from .scheduler import setup_scheduler
```

Remove the `register_scheduler(scheduler)` call (the API dev handles this in
Phase 2, but if you're doing it first, just delete that line).

In `_channel_check_async()`:

```python
# OLD
from .pipeline import run_pipeline

# NEW
from .worker import run_pipeline
```

In `_run_all_async()` and `_run_video_async()`:

```python
# OLD
from .pipeline import run_pipeline

# NEW
from .worker import run_pipeline
```

Also remove the `enqueue` import if it still appears anywhere in `cli.py`.

---

## External CLI tools the pipeline calls

| Step | Tool | Invocation | Input | Output |
|------|------|-----------|-------|--------|
| download | `tk-down` | `tk-down <video_url> --output-dir <dir>` | Video URL | Prints MP4 path to stdout |
| stt | `tk-stt` | `tk-stt <mp4_path> --output <raw.json> --model <model>` | MP4 file | `raw_transcription.json` |
| punctuation | `tk-punctuation` | `tk-punctuation --input-file <raw.json>` | raw JSON | Prints punctuated JSON to stdout |
| alignment | `tk-aligner` | `tk-aligner <mp4> <punct.json> --output <aligned.json> --model <model>` | MP4 + punctuated JSON | `aligned.json` |
| srt_merge | `tk-srt-merger` | `tk-srt-merger <aligned.json> <punct.json> <srt_path>` | aligned + punctuated JSON | `subtitles.srt` |
| translation | `tk-batch-translate` | `tk-batch-translate srt <srt> --output <vtt> --format vtt --model <model> --batch-size <N>` | SRT file | `subtitles.vtt` |

---

## Config fields you use

| Field | Type | Purpose |
|-------|------|---------|
| `output_dir` | Path | Root output directory (videos stored at `output_dir/<username>/<video_id>/`) |
| `stt_model` | str | Model name for `tk-stt` |
| `aligner_model` | str | Model name for `tk-aligner` |
| `translate_model` | str | Model name for `tk-batch-translate` |
| `translate_batch_size` | int | Batch size for `tk-batch-translate` |

---

## Job lifecycle (your responsibility)

The worker owns the Job lifecycle from `pending` onward:

```
pending ──→ running ──→ completed
                   ├──→ failed (error_message set)
                   └──→ interrupted (on CancelledError / shutdown)

interrupted ──→ running (on next startup or next poll cycle)
```

- `pending`: Created by the scheduler. Worker picks it up.
- `running`: Worker is actively processing. `current_step` tracks which step.
- `completed`: All 6 steps finished. `current_step` cleared, `completed_at` set.
- `failed`: A step threw an exception. `failed_step` and `error_message` set.
- `interrupted`: Process was killed mid-pipeline. `current_step` preserved
  for resume. On next startup, `recover_interrupted_jobs()` catches stale
  `running` jobs and marks them `interrupted`.

---

## Output directory structure

For a video by `@username` with ID `1234567890`:

```
output/
└── username/
    └── 1234567890/
        ├── <video_id>.mp4          # download step
        ├── raw_transcription.json  # stt step
        ├── punctuated.json         # punctuation step
        ├── aligned.json            # alignment step
        ├── subtitles.srt           # srt_merge step
        ├── subtitles.vtt           # translation step
        └── job.log                 # pipeline execution log
```

---

## Rules

- `worker/` imports only from `models/`, `config`, and `logging_config`.
  Never from `api/` or `scheduler/`.
- Within `worker/`, `queue.py` imports from `pipeline.py` (local import).
  This is fine — they are in the same module.
- The worker communicates with the scheduler ONLY through the database.
  It reads `Job(status="pending")` rows. No function calls, no queue, no
  message passing.

---

## Verification Criteria

### V1: Module imports work

```bash
uv run --package tk-orchestrator python -c "
from tk_orchestrator.worker import worker, run_pipeline, recover_interrupted_jobs
print('worker imports OK')
"
```

### V2: Old files are gone

```bash
test ! -f src/tk_orchestrator/pipeline.py && echo "pipeline.py removed OK"
test ! -f src/tk_orchestrator/queue.py && echo "queue.py removed OK"
```

### V3: No cross-module imports

```bash
# Must return nothing:
grep -r "from \.\.api" src/tk_orchestrator/worker/ && echo "FAIL" || echo "OK: no api import"
grep -r "from \.\.scheduler" src/tk_orchestrator/worker/ && echo "FAIL" || echo "OK: no scheduler import"
```

### V4: No enqueue function exists

```bash
# The enqueue() function should not exist anywhere:
grep -rn "def enqueue" src/tk_orchestrator/ && echo "FAIL: enqueue still defined" || echo "OK: no enqueue"
grep -rn "from.*import.*enqueue" src/tk_orchestrator/ && echo "FAIL: enqueue still imported" || echo "OK: no enqueue import"
```

### V5: Worker claims and processes jobs from DB

```bash
uv run --package tk-orchestrator python -c "
from pathlib import Path
from tk_orchestrator.config import Config
from tk_orchestrator.models import init_db, get_session, Channel, Video, Job
from tk_orchestrator.worker.queue import _claim_next_job, recover_interrupted_jobs

config = Config(db_path=Path('/tmp/test_phase4.db'))
init_db(config)

# Create test data
with get_session() as s:
    ch = Channel(username='testuser', url='https://tiktok.com/@testuser')
    s.add(ch)
    s.flush()
    v = Video(id='111', channel_id=ch.id, url='https://example.com/111')
    s.add(v)
    s.flush()
    s.add(Job(video_id='111', status='pending'))

# Worker should claim the pending job
claimed = _claim_next_job()
assert claimed is not None, 'Worker should have claimed a job'
print(f'Claimed job {claimed}')

# Verify it is now running
with get_session() as s:
    j = s.get(Job, claimed)
    assert j.status == 'running', f'Expected running, got {j.status}'

# No more jobs to claim
assert _claim_next_job() is None, 'Should be no more jobs'

# Test recovery: create a stale running job
with get_session() as s:
    v2 = Video(id='222', channel_id=1, url='https://example.com/222')
    s.add(v2)
    s.flush()
    s.add(Job(video_id='222', status='running', current_step='stt'))

recovered = recover_interrupted_jobs()
assert len(recovered) >= 1, 'Should recover stale running jobs'

# Now the interrupted job should be claimable
claimed2 = _claim_next_job()
assert claimed2 is not None, 'Interrupted job should be claimable'

print('DB-polling worker OK')
"
rm -f /tmp/test_phase4.db
```

### V6: Pipeline resume uses last_completed_step

```bash
uv run --package tk-orchestrator python -c "
from tk_orchestrator.worker.pipeline import _resolve_resume_step, PIPELINE_STEPS

class MockJob:
    def __init__(self, **kwargs):
        self.current_step = kwargs.get('current_step')
        self.status = kwargs.get('status')
        self.video_path = kwargs.get('video_path')
        self.srt_path = kwargs.get('srt_path')
        self.last_completed_step = kwargs.get('last_completed_step')

from pathlib import Path
dummy_dir = Path('/tmp/nonexistent')

# With last_completed_step='download', should resume from 'stt'
j = MockJob(last_completed_step='download')
assert _resolve_resume_step(j, dummy_dir) == 'stt'

# With last_completed_step='stt', should resume from 'punctuation'
j = MockJob(last_completed_step='stt')
assert _resolve_resume_step(j, dummy_dir) == 'punctuation'

# With last_completed_step='srt_merge', should resume from 'translation'
j = MockJob(last_completed_step='srt_merge')
assert _resolve_resume_step(j, dummy_dir) == 'translation'

# With no last_completed_step, falls back to file-based logic
j = MockJob(current_step='stt', status='interrupted')
assert _resolve_resume_step(j, dummy_dir) == 'stt'

# Fresh job starts from download
j = MockJob()
assert _resolve_resume_step(j, dummy_dir) == 'download'

print('Resume logic OK')
"
```

### V7: Server starts and worker picks up jobs

```bash
# Terminal 1: start the server
uv run --package tk-orchestrator tk-orch start

# Terminal 2: create a job and verify the worker picks it up
# (watch Terminal 1 logs for "Claimed job ..." within 5 seconds)
uv run --package tk-orchestrator tk-orch run https://www.tiktok.com/@someone/video/12345
```

### V8: CLI commands still work

```bash
# These should all work with the new import paths:
uv run --package tk-orchestrator tk-orch jobs
uv run --package tk-orchestrator tk-orch channel list
# uv run --package tk-orchestrator tk-orch channel check <username>
# uv run --package tk-orchestrator tk-orch run <video_url>
```

### V9: Existing tests still pass

```bash
uv run --package tk-orchestrator pytest
```
