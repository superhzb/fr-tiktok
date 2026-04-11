# Phase 2: `api/` Module (HTTP Server)

**Owner**: API developer  
**Depends on**: Phase 1 (`models/`) must be complete  
**Does NOT touch**: `scheduler/`, `worker/`, `pipeline.py`, `queue.py`

---

## Context

You are building the HTTP API layer for a TikTok video subtitle orchestrator.
The system downloads TikTok videos, transcribes and translates subtitles, and
serves them to a mobile app frontend.

The API module is responsible for:
- Serving video/channel/job metadata from the SQLite database
- Serving static video and subtitle files from the output directory
- **New**: A smart feed endpoint that returns videos ordered by watch progress
- **New**: Watch progress tracking endpoints (the frontend reports how far the
  user has watched each video)
- **New**: Video deletion (removes video + all related data + output files)

**The rule**: `api/` imports only from `models/` and `config`. It must NEVER
import from `scheduler/`, `worker/`, or any pipeline code.

---

## What Already Exists

The current `api.py` is a single FastAPI file with these endpoints:

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | System health check |
| GET | `/channels` | List all channels |
| GET | `/channels/{username}` | Get one channel |
| GET | `/videos` | List all videos (ordered by created_at DESC) |
| GET | `/videos/{video_id}` | Get one video |
| GET | `/videos/{video_id}/comments` | Get comments for a video |
| GET | `/videos/{video_id}/subtitles` | Get subtitle file URLs |
| GET | `/jobs` | List recent jobs |
| GET | `/jobs/{job_id}` | Get one job |

It also has a `register_scheduler()` function that holds a live reference to
the scheduler object for the health endpoint. **This must be removed** — the
API should not hold references to other modules' live objects.

---

## What You Are Building

### Directory structure

```
src/tk_orchestrator/api/
├── __init__.py     # re-exports: app, configure
└── routes.py       # all FastAPI endpoints
```

### New endpoints to add

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/feed` | Smart-ordered video list with watch progress |
| GET | `/progress` | Bulk get all watch progress records |
| PUT | `/videos/{video_id}/progress` | Upsert watch progress for one video |
| DELETE | `/videos/{video_id}` | Delete video + related data + output files |

---

## Step-by-step

### 2.1 Create `api/routes.py`

Copy the current `api.py` into `api/routes.py`. Then make these changes:

**Fix imports** (relative paths change because we're one level deeper):

```python
# OLD
from .config import Config
from .db import Channel, Comment, Job, Video, get_session

# NEW
from ..config import Config
from ..models import (
    Channel, Comment, Job, Video, WatchProgress, get_session,
    VideoResponse, VideoFilesResponse, FeedVideoResponse,
    WatchProgressRequest, WatchProgressResponse,
)
```

**Remove scheduler coupling** — delete these entirely:

```python
# DELETE these:
_scheduler = None

def register_scheduler(scheduler) -> None: ...
def _scheduler_state_name(state) -> str: ...
def _scheduler_health() -> dict: ...
```

**Simplify the health endpoint** — remove scheduler health, keep DB health only:

```python
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
```

### 2.2 Add `GET /feed` endpoint

This is the primary endpoint the frontend calls on app start. It returns
completed videos ordered by the smart feed algorithm:

- **Tier 1 (Unwatched)**: `play_percentage = 0` or no watch progress. Ordered by `discovered_at DESC` (newest first).
- **Tier 2 (Started)**: `loop_count = 0` AND `play_percentage > 0`. Ordered by `play_percentage ASC` (least watched first).
- **Tier 3 (Completed)**: `loop_count >= 1`. Ordered by `loop_count ASC` (least rewatched first).

```python
@app.get("/feed")
async def feed():
    """Return completed videos in smart feed order with watch progress."""
    with get_session() as s:
        # Get completed videos (those with at least one completed job)
        completed_video_ids = (
            s.query(Job.video_id)
            .filter(Job.status == "completed")
            .distinct()
            .subquery()
        )

        videos = (
            s.query(Video, WatchProgress)
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

        # Sort using the three-tier algorithm
        def feed_sort_key(item):
            wp = item.get("watch_progress")
            pct = wp["play_percentage"] if wp else 0
            loops = wp["loop_count"] if wp else 0

            if pct == 0:
                tier = 0  # unwatched — show first
            elif loops == 0:
                tier = 1  # started — by ascending percentage
            else:
                tier = 2  # completed — by ascending loop count

            return (tier, pct if tier == 1 else loops if tier == 2 else 0)

        result.sort(key=feed_sort_key)
        return result
```

### 2.3 Add `GET /progress` endpoint

Bulk fetch all watch progress. The frontend calls this to hydrate its local
state on app start (or it can use `/feed` which already includes it).

```python
@app.get("/progress")
async def list_progress():
    """Return all watch progress records."""
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
```

### 2.4 Add `PUT /videos/{video_id}/progress` endpoint

The frontend calls this to report watch progress. It upserts (creates or
updates) the `WatchProgress` row for a video.

```python
@app.put("/videos/{video_id}/progress")
async def update_progress(
    video_id: Annotated[VideoId, FastAPIPath(description="Numeric TikTok video ID")],
    body: WatchProgressRequest,
):
    """Upsert watch progress for a video."""
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
```

You will need to add this import at the top of `routes.py`:

```python
from datetime import datetime, timezone
```

### 2.5 Add `DELETE /videos/{video_id}` endpoint

Deletes a video and all related data (comments, jobs, watch progress via
CASCADE) plus its output files from disk.

```python
@app.delete("/videos/{video_id}")
async def delete_video(
    video_id: Annotated[VideoId, FastAPIPath(description="Numeric TikTok video ID")],
):
    """Delete a video and all its related data + output files."""
    with get_session() as s:
        v = s.query(Video).filter(Video.id == video_id).first()
        if not v:
            raise HTTPException(404, "Video not found")

        channel_username = v.channel.username if v.channel else v.author
        s.delete(v)  # CASCADE handles comments, jobs, watch_progress

    # Clean up output files
    if channel_username:
        video_dir = _output_dir() / channel_username / video_id
        if video_dir.is_dir():
            import shutil
            shutil.rmtree(video_dir)

    return {"status": "deleted", "video_id": video_id}
```

### 2.6 Create `api/__init__.py`

```python
# api/__init__.py
from .routes import app, configure
```

Note: `register_scheduler` is intentionally NOT re-exported. It no longer exists.

### 2.7 Delete old `api.py`

Once `api/routes.py` is working, delete `src/tk_orchestrator/api.py`.

### 2.8 Update `cli.py` imports

In `cli.py`, the import in `_start_async()` changes:

```python
# OLD
from .api import app, configure, register_scheduler

# NEW
from .api import app, configure
```

And remove the `register_scheduler(scheduler)` call from `_start_async()`.

---

## Existing code you must preserve exactly

These existing serialization helpers and type annotations must be kept as-is in
`routes.py` (they are used by existing endpoints that must not break):

- `_serialize_channel()`, `_serialize_video()`, `_serialize_comment()`, `_serialize_job()`
- `_video_files()` — resolves output directory to API-serveable URLs
- `VideoId`, `Username`, `JobStatus`, `VideoListQuery` — request validation types
- `_db_health()` — database connectivity check
- `log_requests` middleware — request logging
- CORS middleware configuration
- Static file mount in `configure()`

All existing GET endpoints (`/channels`, `/videos`, `/videos/{id}`,
`/videos/{id}/comments`, `/videos/{id}/subtitles`, `/jobs`, `/jobs/{id}`)
must continue to work unchanged.

---

## Rules

- `api/` imports only from `models/` and `config`. Never from `scheduler/`,
  `worker/`, `pipeline`, or `queue`.
- No live object references to scheduler or worker. The API communicates with
  other modules only through the database.
- All new endpoints must validate `video_id` using the existing `VideoId`
  annotated type (ensures it's a numeric string up to 32 digits).

---

## Verification Criteria

### V1: Module imports work

```bash
uv run --package tk-orchestrator python -c "
from tk_orchestrator.api import app, configure
print('api imports OK')
"
```

### V2: Old api.py is gone

```bash
test ! -f src/tk_orchestrator/api.py && echo "api.py removed OK"
```

### V3: No cross-module imports

```bash
# Must return nothing:
grep -r "from \.\.scheduler" src/tk_orchestrator/api/ && echo "FAIL" || echo "OK: no scheduler import"
grep -r "from \.\.worker" src/tk_orchestrator/api/ && echo "FAIL" || echo "OK: no worker import"
grep -r "from \.\.pipeline" src/tk_orchestrator/api/ && echo "FAIL" || echo "OK: no pipeline import"
grep -r "from \.\.queue" src/tk_orchestrator/api/ && echo "FAIL" || echo "OK: no queue import"
grep -r "register_scheduler" src/tk_orchestrator/ && echo "FAIL: register_scheduler still exists" || echo "OK"
```

### V4: Existing endpoints still work

```bash
# Start server, test all existing endpoints, then kill
uv run --package tk-orchestrator tk-orch start &
SERVER_PID=$!
sleep 3

echo "=== Health ==="
curl -sf http://localhost:8000/health | python3 -m json.tool

echo "=== Channels ==="
curl -sf http://localhost:8000/channels | python3 -m json.tool

echo "=== Videos ==="
curl -sf http://localhost:8000/videos | python3 -m json.tool

echo "=== Jobs ==="
curl -sf http://localhost:8000/jobs | python3 -m json.tool

kill $SERVER_PID
```

### V5: New feed endpoint works

```bash
uv run --package tk-orchestrator tk-orch start &
SERVER_PID=$!
sleep 3

echo "=== Feed (should return completed videos with watch_progress field) ==="
curl -sf http://localhost:8000/feed | python3 -m json.tool

# The response should be a JSON array. Each item must have a "watch_progress"
# key (either null or an object with play_percentage, loop_count, etc.)

kill $SERVER_PID
```

### V6: Watch progress CRUD works

```bash
uv run --package tk-orchestrator tk-orch start &
SERVER_PID=$!
sleep 3

# Pick a video_id that exists in your DB (replace VIDEO_ID below)
VIDEO_ID=$(curl -sf http://localhost:8000/videos | python3 -c "import sys,json; vs=json.load(sys.stdin); print(vs[0]['id'] if vs else '')")

if [ -n "$VIDEO_ID" ]; then
    echo "=== PUT progress ==="
    curl -sf -X PUT "http://localhost:8000/videos/$VIDEO_ID/progress" \
        -H "Content-Type: application/json" \
        -d '{"play_percentage": 42, "loop_count": 0, "seen": false, "saved_position": 15}' \
        | python3 -m json.tool

    echo "=== GET progress (bulk) ==="
    curl -sf http://localhost:8000/progress | python3 -m json.tool
    # Should include an entry for VIDEO_ID with play_percentage=42

    echo "=== Feed now reflects progress ==="
    curl -sf http://localhost:8000/feed | python3 -c "
import sys, json
feed = json.load(sys.stdin)
for v in feed:
    wp = v.get('watch_progress')
    pct = wp['play_percentage'] if wp else 0
    print(f\"  {v['id']}  pct={pct}  loops={wp['loop_count'] if wp else 0}\")
"
else
    echo "No videos in DB — skip progress test"
fi

kill $SERVER_PID
```

### V7: Video deletion works

```bash
uv run --package tk-orchestrator tk-orch start &
SERVER_PID=$!
sleep 3

VIDEO_ID=$(curl -sf http://localhost:8000/videos | python3 -c "import sys,json; vs=json.load(sys.stdin); print(vs[0]['id'] if vs else '')")

if [ -n "$VIDEO_ID" ]; then
    echo "=== DELETE video ==="
    curl -sf -X DELETE "http://localhost:8000/videos/$VIDEO_ID" | python3 -m json.tool
    # Should return {"status": "deleted", "video_id": "..."}

    echo "=== Verify it is gone ==="
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:8000/videos/$VIDEO_ID")
    [ "$HTTP_CODE" = "404" ] && echo "OK: video is gone" || echo "FAIL: video still exists ($HTTP_CODE)"
else
    echo "No videos in DB — skip delete test"
fi

kill $SERVER_PID
```

### V8: Feed ordering is correct

```bash
uv run --package tk-orchestrator python -c "
# Unit test the sort logic in isolation
def feed_sort_key(item):
    wp = item.get('watch_progress')
    pct = wp['play_percentage'] if wp else 0
    loops = wp['loop_count'] if wp else 0
    if pct == 0:
        tier = 0
    elif loops == 0:
        tier = 1
    else:
        tier = 2
    return (tier, pct if tier == 1 else loops if tier == 2 else 0)

items = [
    {'id': 'A', 'watch_progress': {'play_percentage': 80, 'loop_count': 2}},  # completed, 2 loops
    {'id': 'B', 'watch_progress': None},                                       # unwatched
    {'id': 'C', 'watch_progress': {'play_percentage': 30, 'loop_count': 0}},  # started, 30%
    {'id': 'D', 'watch_progress': {'play_percentage': 60, 'loop_count': 0}},  # started, 60%
    {'id': 'E', 'watch_progress': {'play_percentage': 95, 'loop_count': 1}},  # completed, 1 loop
    {'id': 'F', 'watch_progress': {'play_percentage': 0, 'loop_count': 0}},   # unwatched (explicit 0)
]

items.sort(key=feed_sort_key)
order = [i['id'] for i in items]
# Expected: unwatched first (B,F), then started by pct asc (C,D), then completed by loops asc (E,A)
assert order == ['B', 'F', 'C', 'D', 'E', 'A'], f'Wrong order: {order}'
print('Feed sort OK:', order)
"
```

### V9: Existing tests still pass

```bash
uv run --package tk-orchestrator pytest
```
