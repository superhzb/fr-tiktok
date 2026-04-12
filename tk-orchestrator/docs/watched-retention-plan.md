# Watched Video Retention Plan

## Goal

Add an automatic cleanup feature in `tk-orchestrator` so the backend deletes older watched videos before storage becomes crowded.

The product rule for v1 is:

- Treat a video as watched when `watch_progress.seen = true` or `watch_progress.loop_count >= 1`.
- When watched videos are at least 50% of stored videos, delete 10 watched videos.
- Deleted videos should free both database rows and output files on disk.
- Do not wait until `max_videos_total` is already reached.

This plan is written so a junior engineer can implement it directly.

## Why This Feature Exists

Current behavior:

- The frontend reports watch progress to `PUT /videos/{video_id}/progress`.
- The backend stores that in `watch_progress`.
- The backend uses watch progress to sort the feed.
- The scheduler stops adding new videos when storage limits are reached.

The current limit behavior is reactive:

- If total stored videos reaches `max_videos_total`, polling stops.
- That means the app can stop bringing in fresh videos even if many stored videos were already watched.

The new retention feature should be proactive:

- Once watched videos become a large enough share of storage, delete some watched videos to make room for future new videos.

## Current Code Paths

These are the files you need to understand before coding:

- Scheduler: [tk-orchestrator/src/tk_orchestrator/scheduler/polling.py](/Users/brett/Documents/GitHub/fr-tiktok/tk-orchestrator/src/tk_orchestrator/scheduler/polling.py)
- API progress update: [tk-orchestrator/src/tk_orchestrator/api/routes.py](/Users/brett/Documents/GitHub/fr-tiktok/tk-orchestrator/src/tk_orchestrator/api/routes.py:382)
- API delete endpoint: [tk-orchestrator/src/tk_orchestrator/api/routes.py](/Users/brett/Documents/GitHub/fr-tiktok/tk-orchestrator/src/tk_orchestrator/api/routes.py:413)
- DB models: [tk-orchestrator/src/tk_orchestrator/models/tables.py](/Users/brett/Documents/GitHub/fr-tiktok/tk-orchestrator/src/tk_orchestrator/models/tables.py:35)
- Config model: [tk-orchestrator/src/tk_orchestrator/config.py](/Users/brett/Documents/GitHub/fr-tiktok/tk-orchestrator/src/tk_orchestrator/config.py)

Relevant existing behavior:

- `poll_channel()` in `polling.py` skips work when per-channel or global stored video limits are hit.
- `WatchProgress` stores `play_percentage`, `loop_count`, `seen`, `saved_position`, and `updated_at`.
- Deleting a `Video` cascades to comments, jobs, and watch progress through ORM relationships and foreign keys.
- The delete API also removes the output directory from disk.

## Scope For V1

Implement only the backend cleanup trigger and deletion policy.

In scope:

- New retention settings in config.
- Scheduler-side cleanup trigger.
- Query to find watched videos eligible for deletion.
- Shared delete helper that removes DB rows and output files.
- Tests for the retention logic.

Out of scope for v1:

- Frontend UI for retention settings.
- Pinning videos.
- Disk-usage based thresholds.
- Partial deletion of only some files.
- Channel-specific watched ratio rules.

## Retention Rules

### Trigger Rule

Run retention when all of the following are true:

- `total_stored_videos > 0`
- `watched_ratio >= retention_watched_ratio_threshold`

Default values:

- `retention_watched_ratio_threshold = 0.5`
- `retention_delete_batch_size = 10`

Formula:

- `watched_ratio = watched_video_count / total_stored_video_count`

### Watched Definition

For v1, a video is watched if either of these is true:

- `watch_progress.seen = true`
- `watch_progress.loop_count >= 1`

Do not define watched using only `play_percentage`. The schema already has better signals.

### Eligible Deletion Candidates

A video is eligible for automatic deletion only if all of these are true:

- It has a completed job.
- It is watched.
- It is not one of the newest protected videos for its channel.

Optional but recommended for v1 if easy to add:

- It is older than a minimum age, such as 24 hours from `discovered_at`.

### Candidate Ordering

When multiple videos are eligible, delete in this order:

1. Higher `loop_count` first.
2. Older `watch_progress.updated_at` first.
3. Older `video.discovered_at` first.

Reasoning:

- If the user finished and looped a video more times, it is lower priority to keep.
- If it has not been touched recently, it is safer to delete.
- Older discovered videos should be reclaimed before newer ones.

### Safety Rules

To avoid surprising deletions:

- Keep at least `retention_keep_newest_per_channel` videos per channel, default `2`.
- Do not delete videos with non-completed jobs.
- Do not delete videos that have no output directory only because of a filesystem error; log and continue carefully.

## Proposed Config Changes

Add these fields to `Config` in `config.py`:

- `retention_enabled: bool = True`
- `retention_watched_ratio_threshold: float = 0.5`
- `retention_delete_batch_size: int = 10`
- `retention_keep_newest_per_channel: int = 2`
- Optional: `retention_min_age_hours: int = 24`

Also add matching environment variable support in `_ENV_MAP`, for example:

- `TK_RETENTION_ENABLED`
- `TK_RETENTION_WATCHED_RATIO_THRESHOLD`
- `TK_RETENTION_DELETE_BATCH_SIZE`
- `TK_RETENTION_KEEP_NEWEST_PER_CHANNEL`
- `TK_RETENTION_MIN_AGE_HOURS`

Implementation note:

- `_ENV_MAP` currently casts values with plain constructors like `int`.
- For booleans, add a small helper parser instead of using `bool("false")`, which would be wrong.

## Proposed Implementation Structure

Do not place this logic in the API layer. Put it in the scheduler code because retention is part of storage management during polling.

Recommended helper functions inside `polling.py`:

- `_count_total_videos() -> int`
- `_count_watched_videos() -> int`
- `_watched_ratio() -> float`
- `_select_retention_candidates(config: Config, limit: int) -> list[Video]`
- `_delete_video_record(video_id: str, output_dir: Path) -> bool`
- `_run_retention_if_needed(config: Config) -> int`

You may reuse existing `_total_video_count()` if preferred. Keep naming consistent.

## Important Refactor Before Adding Retention

Right now the delete behavior is duplicated conceptually:

- The API endpoint knows how to delete a video and remove files.
- The scheduler will need the same behavior.

Before adding retention, extract the delete logic into a shared helper module, for example:

- `tk_orchestrator/video_retention.py`
- or `tk_orchestrator/video_store.py`

Suggested shared function:

```python
def delete_video_and_files(video_id: str, output_dir: Path) -> bool:
    """Delete one video row and its output directory. Returns True if deleted."""
```

This function should:

1. Load the video from the DB.
2. If not found, return `False`.
3. Capture `channel_username` before deleting.
4. Delete the `Video` row.
5. Remove the on-disk video directory if it exists.
6. Log success or failure.

Then:

- The API `DELETE /videos/{video_id}` route should call this shared helper.
- The scheduler retention code should call the same helper.

This reduces drift and makes the behavior testable.

## Suggested Query Design

You need a query that returns watched videos safe to delete.

### Data Needed

Join these tables:

- `Video`
- `WatchProgress`
- `Job`
- `Channel` if you need channel username or per-channel grouping

### Filters

Use filters roughly like this:

- `WatchProgress.video_id == Video.id`
- `Job.video_id == Video.id`
- `Job.status == "completed"`
- `(WatchProgress.seen == True) OR (WatchProgress.loop_count >= 1)`

Then apply the channel protection rule:

- For each channel, keep the newest `retention_keep_newest_per_channel` videos.

This per-channel protection may be easiest to implement in Python in v1:

1. Query candidate rows ordered by channel and recency.
2. Build a set of protected video IDs per channel.
3. Exclude protected IDs.

That is acceptable for v1 because the library size is small.

### Ordering

Sort deletion candidates by:

- `WatchProgress.loop_count.desc()`
- `WatchProgress.updated_at.asc().nullsfirst()` if supported
- `Video.discovered_at.asc()`

If `.nullsfirst()` creates compatibility issues with SQLite, sort in Python after loading rows.

## Where To Trigger Retention

Run retention near the start of `poll_channel()` before early returns based on hard storage limits.

Recommended order:

1. Compute current totals.
2. If retention is enabled, run `_run_retention_if_needed(config)`.
3. Recompute totals after deletion.
4. Continue existing channel/global limit checks.

Why here:

- This keeps retention close to the code that manages capacity.
- It allows retention to free space before the scheduler decides to skip polling.

## Detailed Implementation Steps

### Step 1: Add Config Fields

Update `Config` and `_ENV_MAP` in `config.py`.

Tasks:

- Add retention settings with defaults.
- Add env var parsing.
- Add any needed boolean parsing helper.
- Confirm config loading still works with existing tests.

### Step 2: Extract Shared Delete Logic

Create a small shared helper module for deletion.

Tasks:

- Move DB row deletion plus filesystem cleanup out of the API route.
- Update the API route to call the helper.
- Return the same API response as before.

Done when:

- Manual delete endpoint behavior does not change.
- Scheduler code can call the same helper directly.

### Step 3: Add Retention Metrics Helpers

Inside scheduler code, add helpers to count:

- total stored videos
- watched stored videos
- watched ratio

Be explicit about watched definition in code comments.

### Step 4: Add Candidate Selection

Implement `_select_retention_candidates(config, limit)`.

Tasks:

- Query watched videos with completed jobs.
- Protect the newest N per channel.
- Apply ordering.
- Return up to `limit` video IDs.

Keep this function deterministic so tests are stable.

### Step 5: Add Retention Runner

Implement `_run_retention_if_needed(config) -> int`.

Behavior:

1. Exit early if `retention_enabled` is false.
2. Count total videos. If zero, return 0.
3. Count watched videos.
4. Compute ratio.
5. If ratio is below threshold, return 0.
6. Select up to `retention_delete_batch_size` candidates.
7. Delete them one by one using the shared helper.
8. Return number deleted.

Logging:

- Log total count, watched count, threshold, and delete batch size.
- Log each deleted video ID.
- Log final deleted count.

### Step 6: Call Retention From `poll_channel()`

At the top of `poll_channel()`:

1. Read counts.
2. Run retention if needed.
3. Refresh counts.
4. Continue with existing logic.

Be careful:

- Recompute both `channel_video_total` and `total_video_total` after retention, because counts may have changed.

### Step 7: Add Tests

Add tests in `tk-orchestrator/tests/`.

Recommended new file:

- `test_retention.py`

## Test Cases To Implement

Write these tests. They are the minimum useful set.

### Test 1: No Retention When Ratio Below Threshold

Setup:

- 10 stored videos
- 4 watched
- threshold 0.5

Expected:

- `_run_retention_if_needed()` deletes 0

### Test 2: Retention Triggers At Threshold

Setup:

- 10 stored videos
- 5 watched
- batch size 10

Expected:

- retention runs
- up to 5 eligible watched videos are deleted if only 5 exist

### Test 3: Only Watched Videos Are Deleted

Setup:

- mix of watched and unwatched videos

Expected:

- unwatched videos remain

### Test 4: Newest Videos Per Channel Are Protected

Setup:

- multiple videos in one channel
- all watched
- `retention_keep_newest_per_channel = 2`

Expected:

- newest two in each channel are not deleted

### Test 5: Only Completed Videos Are Eligible

Setup:

- watched videos with `Job.status != "completed"`

Expected:

- those videos are not deleted

### Test 6: Delete Helper Removes Filesystem Directory

Setup:

- create a fake output directory for one video

Expected:

- deleting the video also removes the directory

### Test 7: Polling Uses Retention Before Hard Limit Check

Setup:

- total videos at hard limit
- watched ratio above threshold
- eligible watched candidates exist

Expected:

- retention deletes some watched videos first
- polling no longer exits immediately for `total_limit_reached`

This is the most important integration test because it verifies the feature changes behavior in the desired way.

## Pseudocode

Use this only as a guide. The exact code can differ.

```python
def _is_watched_expr():
    return or_(
        WatchProgress.seen.is_(True),
        WatchProgress.loop_count >= 1,
    )


def _run_retention_if_needed(config: Config) -> int:
    if not config.retention_enabled:
        return 0

    total = _total_video_count()
    if total == 0:
        return 0

    watched = _watched_video_count()
    ratio = watched / total

    if ratio < config.retention_watched_ratio_threshold:
        return 0

    candidates = _select_retention_candidates(
        config,
        config.retention_delete_batch_size,
    )

    deleted = 0
    for video_id in candidates:
        if delete_video_and_files(video_id, config.output_dir.resolve()):
            deleted += 1

    return deleted
```

## Risks And Edge Cases

### Risk 1: Deleting Too Aggressively

If the watched ratio is above 50% for a long time, retention may run repeatedly on each poll.

Two acceptable v1 approaches:

- Keep it simple and allow repeated batches.
- Or add a cooldown later if needed.

Do not add cooldown in v1 unless testing shows churn.

### Risk 2: Small Libraries

If there are very few videos, deleting 10 may be too much.

Use:

- `limit = min(batch_size, number_of_eligible_candidates)`

### Risk 3: Missing WatchProgress Rows

Some old videos may not have `watch_progress`.

That is fine:

- they are not watched
- they should not be auto-deleted in this feature

### Risk 4: Filesystem Errors

If DB delete succeeds but file delete fails, log it clearly.

Prefer behavior:

- DB delete still commits
- file removal failure is logged as an error

Do not try to roll back DB deletion because of a filesystem failure.

## Suggested Log Events

The repo already uses structured logging patterns in CLI services. Follow the same spirit here even if these scheduler logs are currently plain logger calls.

Add logs for:

- retention evaluation started
- watched ratio computed
- candidate count found
- each video deleted
- file deletion failure
- retention completed

Example content:

- total videos
- watched videos
- watched ratio
- threshold
- batch size
- deleted count

## Definition Of Done

This feature is complete when all of the following are true:

- Config supports retention settings with sensible defaults.
- Delete logic is shared between API and scheduler.
- Scheduler runs watched-ratio retention before hard storage-limit exits.
- Only watched, completed, non-protected videos are auto-deleted.
- Output files are removed along with DB rows.
- Tests cover trigger logic, candidate filtering, and polling integration.

## Recommended Commit Breakdown

If you want to keep the work easy to review, use this order:

1. Config support for retention settings.
2. Shared delete helper and API refactor.
3. Scheduler retention logic.
4. Tests.

This keeps each diff understandable and lowers the chance of breaking behavior silently.
