# Frontend Integration Guide

How tk-web should consume the updated tk-orchestrator API.

---

## What Changed in the Backend

| Before | After |
|--------|-------|
| `GET /videos?status=completed` returns a flat list, no watch state | `GET /feed` returns videos **pre-sorted** by watch progress, with `watch_progress` attached to each item |
| Watch progress lives only in IndexedDB | Backend is the source of truth; frontend syncs progress to the API |
| No way to delete a video | `DELETE /videos/{id}` removes video + files + all related data |
| No server-side progress storage | `PUT /videos/{id}/progress` upserts watch state |

---

## New & Changed Endpoints

### `GET /feed`

**Replaces**: `GET /videos?status=completed` as the primary data source.

Returns completed videos already sorted by the smart feed algorithm:
1. **Unwatched** (no progress or `play_percentage = 0`) — oldest first
2. **Started** (`loop_count = 0`, `play_percentage > 0`) — least watched first
3. **Completed** (`loop_count >= 1`) — least rewatched first

**Response** — JSON array:

```jsonc
[
  {
    "id": "7234567890123456789",
    "channel_id": 1,
    "channel_username": "frances.con.romeo",
    "description": "Video description",
    "url": "https://www.tiktok.com/@frances.con.romeo/video/7234567890123456789",
    "duration": 45,
    "views": 12000,
    "likes": 500,
    "comments_count": 30,
    "shares": 10,
    "author": "frances.con.romeo",
    "author_nickname": "Frances",
    "music_title": "Song Title",
    "created_at": "2025-01-15T12:00:00",
    "discovered_at": "2025-01-16T08:30:00",
    "files": {
      "video_url": "/output/frances.con.romeo/7234567890123456789/video.mp4",
      "vtt_url": "/output/frances.con.romeo/7234567890123456789/subtitles.vtt",
      "srt_url": "/output/frances.con.romeo/7234567890123456789/subtitles.srt"
    },
    // NEW — null if never watched
    "watch_progress": {
      "video_id": "7234567890123456789",
      "play_percentage": 42,
      "loop_count": 0,
      "seen": false,
      "saved_position": 19,
      "updated_at": "2025-01-16T10:00:00"
    }
  }
]
```

The `watch_progress` field is `null` for unwatched videos.

---

### `PUT /videos/{video_id}/progress`

**Purpose**: Report watch progress to the backend. Call this on flush intervals
(replaces writing to IndexedDB).

The backend stores `saved_position`, but the frontend should **not** use it to
resume playback after a cold app restart. Resume-from-position is only an
in-memory same-session behavior when the user scrolls back to a previously
visited video.

**Request body**:

```json
{
  "play_percentage": 42,
  "loop_count": 0,
  "seen": false,
  "saved_position": 19
}
```

| Field | Type | Description |
|-------|------|-------------|
| `play_percentage` | int (0–100) | Furthest point reached (validated: 0 <= x <= 100) |
| `loop_count` | int | Times watched to >= 95% |
| `seen` | bool | True once watched to >= 95% |
| `saved_position` | int | Seconds, where user left off |

**Response**: `{"status": "ok", "video_id": "..."}`

**Error**: `404` if video_id not found.

---

### `GET /progress`

**Purpose**: Bulk fetch all watch progress. Alternative to extracting it from
`/feed` responses if needed separately.

**Response** — JSON array:

```json
[
  {
    "video_id": "7234567890123456789",
    "play_percentage": 42,
    "loop_count": 0,
    "seen": false,
    "saved_position": 19,
    "updated_at": "2025-01-16T10:00:00"
  }
]
```

---

### `DELETE /videos/{video_id}`

**Purpose**: Delete a video and all related data (comments, jobs, watch
progress, output files on disk).

**Response**: `{"status": "deleted", "video_id": "..."}`

**Error**: `404` if video_id not found.

---

## Migration Plan

### Overview of what changes in tk-web

```
src/
├── api.ts                    # add fetchFeed, syncProgress, deleteVideo
├── types.ts                  # add FeedVideo type (Video + watch_progress)
├── lib/
│   ├── feedSort.ts           # legacy local sort; remove from main feed path
│   └── playStatsDb.ts        # legacy IndexedDB path; remove from main feed path
├── context/
│   └── SmartFeedContext.tsx   # replace IndexedDB-first with API-first
└── App.tsx                   # call fetchFeed instead of fetchVideos
```

## Parallel Work Split

Use these tracks to let multiple frontend engineers work in parallel with
minimal overlap.

### Track A: API Client + Types

**Owner**: frontend API/data layer

**Files**:
- `src/types.ts`
- `src/api.ts`

**Goal**: define the backend response types and API calls used by the rest of
the app.

**Deliverables**:
- Add `WatchProgress`
- Add `FeedVideo`
- Add `fetchFeed()`
- Add `syncProgress()`
- Add `deleteVideo()`
- Keep existing comment/subtitle helpers unchanged

**Rules**:
- Preserve existing `Video` shape and extend it with `FeedVideo`
- Throw on non-OK responses for all new API calls
- Do not add offline/cache logic in this track

### Track B: App Bootstrap

**Owner**: app shell / entrypoint

**Files**:
- `src/App.tsx`

**Goal**: switch app startup from the legacy completed-videos endpoint to the
new feed endpoint.

**Deliverables**:
- Fetch with `fetchFeed()` on app load
- Store `FeedVideo[]` in app state
- Keep the existing loading, error, and empty states
- Continue filtering out videos with no `files.video_url`

**Rules**:
- App bootstrap should not implement feed sorting
- App bootstrap should not implement progress sync

### Track C: Smart Feed State

**Owner**: playback/feed state management

**Files**:
- `src/context/SmartFeedContext.tsx`

**Goal**: consume server-provided watch progress while preserving current
same-session playback behavior.

**Deliverables**:
- Remove IndexedDB-first startup hydration
- Build `statsMapRef` from `video.watch_progress`
- Use the incoming `/feed` order as-is
- Flush progress to `PUT /videos/{id}/progress`
- Keep same-session scroll-back resume via `sessionMapRef`
- Do not restore `saved_position` on cold app launch

**Rules**:
- Treat `/feed` ordering as fixed for the current app session
- Do not locally re-sort after progress changes
- Do not re-fetch `/feed` in response to progress writes
- Do not add offline fallback in this track

**Integration dependency**:
- Depends on Track A types and API functions
- Can be developed in parallel with Track B as long as `FeedVideo` is the
  agreed input type

### Track D: Delete Video UX

**Owner**: feed UI / interaction layer

**Files**:
- whichever component owns the delete interaction
- possibly `src/App.tsx` if top-level feed state owns removal

**Goal**: expose backend deletion to the user and remove deleted items from the
current feed state.

**Deliverables**:
- Add a delete trigger in the UI
- Call `deleteVideo(videoId)`
- Remove the deleted video from local state after success
- Handle failure visibly or at least log it clearly

**Rules**:
- Deletion should not trigger a feed re-fetch
- Deletion should update local state immediately after success

---

## Implementation Details

### Track A Details: Update `types.ts`

Add the server-side watch progress type and the feed video type:

```typescript
/** Watch progress as returned by the backend */
export interface WatchProgress {
  video_id: string
  play_percentage: number
  loop_count: number
  seen: boolean
  saved_position: number
  updated_at: string | null
}

/** A video with watch progress attached — returned by GET /feed */
export interface FeedVideo extends Video {
  watch_progress: WatchProgress | null
}
```

The existing `VideoPlayStats` (camelCase, IndexedDB format) can stay as-is for
the in-memory play stats layer. You'll convert between the two formats.

### Track A Details: Update `api.ts`

```typescript
export async function fetchFeed(): Promise<FeedVideo[]> {
  const res = await fetch(`${BASE}/feed`)
  if (!res.ok) throw new Error('Failed to fetch feed')
  return res.json()
}

export async function syncProgress(
  videoId: string,
  progress: {
    play_percentage: number
    loop_count: number
    seen: boolean
    saved_position: number
  }
): Promise<void> {
  const res = await fetch(`${BASE}/videos/${videoId}/progress`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(progress),
  })
  if (!res.ok) throw new Error(`Failed to sync progress for ${videoId}`)
}

export async function deleteVideo(videoId: string): Promise<void> {
  const res = await fetch(`${BASE}/videos/${videoId}`, { method: 'DELETE' })
  if (!res.ok) throw new Error('Failed to delete video')
}
```

### Track B Details: Update `App.tsx`

```diff
- import { fetchVideos } from './api'
+ import { fetchFeed } from './api'
- import type { Video } from './types'
+ import type { FeedVideo } from './types'

- const [videos, setVideos] = useState<Video[]>([])
+ const [videos, setVideos] = useState<FeedVideo[]>([])

  useEffect(() => {
-   fetchVideos()
-     .then(vs => setVideos(vs.filter(v => v.files.video_url)))
+   fetchFeed()
+     .then(vs => setVideos(vs.filter(v => v.files.video_url)))
```

### Track C Details: Update `SmartFeedContext.tsx`

The key change: **the feed comes pre-sorted from the server** and includes
`watch_progress`. The context no longer needs to load from IndexedDB on startup
or sort locally.

Important session rule: treat the `/feed` order as fixed for the lifetime of the
current app session. Progress updates should not trigger a local re-sort or a
background re-fetch to move videos around. The next app launch will fetch a new
server-sorted feed.

**On mount (replace the `getAllStats` effect):**

```typescript
// Before: load stats from IndexedDB, then sort locally
// After: feed is already sorted, extract stats from watch_progress field

useEffect(() => {
  const map = new Map<string, VideoPlayStats>()
  for (const v of videos) {
    if (v.watch_progress) {
      map.set(v.id, {
        videoId: v.id,
        playPercentage: v.watch_progress.play_percentage,
        loopCount: v.watch_progress.loop_count,
        seen: v.watch_progress.seen,
      })
    }
  }
  statsMapRef.current = map
  setOrderedFeed(videos)  // already sorted by server
  setReady(true)
}, [videos])
```

**On flush (replace the IndexedDB write):**

```typescript
const flushStats = useCallback(() => {
  const dirtyIds = dirtyIdsRef.current
  if (dirtyIds.size === 0) return
  dirtyIdsRef.current = new Set()

  for (const id of dirtyIds) {
    const stat = statsMapRef.current.get(id)
    if (!stat) continue
    const session = sessionMapRef.current.get(id)

    syncProgress(id, {
      play_percentage: Math.round(stat.playPercentage),
      loop_count: stat.loopCount,
      seen: stat.seen,
      saved_position: Math.round(session?.savedPosition ?? 0),
    }).catch(err => {
      console.warn(`Failed to sync progress for ${id}:`, err)
      dirtyIdsRef.current.add(id)  // retry next flush
    })
  }
}, [])
```

The 30-second flush interval and visibility-change flush stay the same.

Do not hydrate `saved_position` from the backend on app start. Same-session
scroll-back resume should continue to live in `sessionMapRef` only.

The existing IndexedDB persistence path should be removed or ignored for this
migration. Offline fallback is out of scope for now.

### Track D Details: Add video deletion UI

Wire a delete action (e.g. long-press menu or swipe action) to:

```typescript
import { deleteVideo } from '../api'

async function handleDelete(videoId: string) {
  await deleteVideo(videoId)
  // Remove from local state — the video is gone server-side
  setVideos(prev => prev.filter(v => v.id !== videoId))
}
```

---

## Field Name Mapping

The frontend uses camelCase, the backend uses snake_case. Here's the mapping
between `VideoPlayStats` (frontend) and the backend `watch_progress` object:

| Frontend (camelCase) | Backend (snake_case) | Notes |
|---------------------|---------------------|-------|
| `videoId` | `video_id` | |
| `playPercentage` | `play_percentage` | Both 0–100 |
| `loopCount` | `loop_count` | |
| `seen` | `seen` | |
| — (in `VideoSessionState`) | `saved_position` | Frontend keeps this in session state; backend stores it in watch_progress |
| — | `updated_at` | Server-set timestamp, read-only for frontend |

---

## Endpoints the Frontend Does NOT Need to Change

These existing endpoints are unchanged and remain available:

| Endpoint | Still used for |
|----------|---------------|
| `GET /videos?status=completed` | Admin/debug use; frontend should prefer `/feed` |
| `GET /videos/{id}/comments` | Comments panel (no changes) |
| `GET /videos/{id}/subtitles` | Subtitle loading (no changes) |
| `GET /channels` | Not used by frontend currently |
| `GET /health` | Not used by frontend currently |

---

## Testing Checklist

- [ ] App start: `GET /feed` returns videos with `watch_progress` field
- [ ] Unwatched videos appear first, then partially watched (by % asc), then completed (by loops asc)
- [ ] Playing a video and waiting 30s: `PUT /videos/{id}/progress` is called
- [ ] Backgrounding the app: progress is flushed immediately
- [ ] Killing and reopening the app: feed order reflects the latest server-side progress
- [ ] Killing and reopening the app: playback starts from the beginning, not from prior `saved_position`
- [ ] Scrolling back to a previously visited video in the same session: playback resumes from in-memory session state
- [ ] Progress updates during a session do not re-sort the visible feed
- [ ] Deleting a video: `DELETE /videos/{id}` succeeds, video disappears from feed

## Suggested Merge Order

To reduce conflicts:

1. Merge Track A first
2. Merge Track B and Track D in either order
3. Merge Track C last, since it touches the main feed-state integration point

## Out Of Scope

- Offline fallback
- IndexedDB write-through caching
- Cold-start resume from `saved_position`
- Mid-session feed re-sorting
