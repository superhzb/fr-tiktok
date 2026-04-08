# Smart Video Feed — Junior Developer Implementation Guide

## What We're Building

Right now, tk-web loads all videos from the server and plays them in whatever order the server returns. There's no memory of what you've watched, no pre-loading, and every time you reopen the app it starts fresh.

We're adding:
1. **Pre-caching** — Download the next 5 videos in advance so they play instantly
2. **Play tracking** — Remember how far you watched each video
3. **Smart ordering** — Show unwatched videos first, then partially watched, then fully watched
4. **Resume/restart** — When you scroll back to a video, pick up where you left off (or restart if you almost finished it)
5. **Persistence** — Save your watch history so it survives app restarts

---

## How the Current Code Works (Read This First)

Before changing anything, understand these files:

- **`src/App.tsx`** — Fetches all videos on mount, passes them to `<VideoFeed>`
- **`src/components/VideoFeed.tsx`** — Renders a scrollable list of videos. Uses `IntersectionObserver` to detect which video is on screen (`activeIndex`). Each video is a `<VideoPlayer>`.
- **`src/components/VideoPlayer.tsx`** — Wraps an HTML5 `<video>` element. Auto-plays when `active` prop is true, pauses when false. Currently resets to `currentTime = 0` when you scroll away.
- **`src/api.ts`** — Has `fetchVideos()` to get the video list and `fileUrl()` to build full URLs
- **`src/types.ts`** — TypeScript interfaces for `Video`, `Comment`, etc.

---

## Step-by-Step Implementation

### Phase 1: Add New Types

**File: `src/types.ts`**

Add these two interfaces at the bottom of the file (after the existing `SubtitleCue` interface):

```ts
/** Saved to IndexedDB — survives app restarts */
export interface VideoPlayStats {
  videoId: string
  playPercentage: number   // 0 to 100, the furthest point the user reached
  loopCount: number        // how many times the video was watched to >=95%
  seen: boolean            // true once the video has been watched to >=95%
}

/** Only lives in memory — lost when app closes */
export interface VideoSessionState {
  savedPosition: number    // the timestamp (in seconds) where user left off
  direction: 'forward' | 'back' | null  // how the user scrolled to this video
}
```

**Why these two separate types?** We want `VideoPlayStats` to survive app restarts (stored in IndexedDB). But `VideoSessionState` is only useful during the current session — things like "where exactly was I in this video" and "did I scroll forward or backward to get here" — so we just keep it in a JavaScript Map.

---

### Phase 2: IndexedDB Persistence Layer

**Create new file: `src/lib/playStatsDb.ts`**

This file handles reading/writing `VideoPlayStats` to the browser's IndexedDB (a built-in browser database). We're NOT using any library — just the raw browser API, since our needs are simple.

```ts
import type { VideoPlayStats } from '../types'

const DB_NAME = 'frtiktok-playstats'
const DB_VERSION = 1
const STORE_NAME = 'stats'

/**
 * Opens (or creates) the IndexedDB database.
 * 
 * IndexedDB is like a mini database in the browser. We create one "store"
 * (think: table) called "stats" that holds VideoPlayStats objects,
 * keyed by videoId.
 */
function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION)

    // This runs the FIRST time the database is created (or when version changes)
    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: 'videoId' })
      }
    }

    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

/** Read ALL play stats from the database */
export async function getAllStats(): Promise<VideoPlayStats[]> {
  const db = await openDb()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readonly')
    const store = tx.objectStore(STORE_NAME)
    const request = store.getAll()
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

/** Write one stat record (creates or overwrites by videoId) */
export async function putStat(stat: VideoPlayStats): Promise<void> {
  const db = await openDb()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite')
    const store = tx.objectStore(STORE_NAME)
    store.put(stat)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}

/** Write many stat records in one transaction (more efficient than multiple putStat calls) */
export async function putManyStats(stats: VideoPlayStats[]): Promise<void> {
  if (stats.length === 0) return
  const db = await openDb()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite')
    const store = tx.objectStore(STORE_NAME)
    for (const stat of stats) {
      store.put(stat)
    }
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}
```

**How to test:** After implementing, open the app in the browser, then in DevTools console run:
```js
// This tests the database directly
const { putStat, getAllStats } = await import('/src/lib/playStatsDb.ts')
await putStat({ videoId: 'test123', playPercentage: 50, loopCount: 0, seen: false })
console.log(await getAllStats()) // Should show the record you just wrote
```

You can also check DevTools > Application > IndexedDB > `frtiktok-playstats` > `stats`.

---

### Phase 3: Feed Sorting Algorithm

**Create new file: `src/lib/feedSort.ts`**

This is a **pure function** — it takes data in and returns data out, no side effects. That makes it easy to test.

```ts
import type { Video, VideoPlayStats } from '../types'

/**
 * Sorts videos into the smart feed order:
 * 
 * 1. UNWATCHED — never started (playPercentage is 0 or no stats exist)
 *    → Keep in original server order
 * 
 * 2. STARTED BUT NOT FINISHED — user watched some but never hit 95%
 *    → Sort by playPercentage ascending (least watched first,
 *      so user sees the ones they barely started)
 * 
 * 3. COMPLETED — user watched to >=95% at least once
 *    → Sort by loopCount ascending (least re-watched first)
 */
export function sortFeed(
  videos: Video[],
  statsMap: Map<string, VideoPlayStats>
): Video[] {
  // Split videos into three buckets
  const unwatched: Video[] = []
  const started: Video[] = []
  const completed: Video[] = []

  for (const video of videos) {
    const stats = statsMap.get(video.id)

    if (!stats || stats.playPercentage === 0) {
      // Bucket 1: Never watched
      unwatched.push(video)
    } else if (stats.loopCount === 0) {
      // Bucket 2: Started but never completed (never hit 95%)
      started.push(video)
    } else {
      // Bucket 3: Completed at least once
      completed.push(video)
    }
  }

  // Sort bucket 2 by play percentage (ascending = least watched first)
  started.sort((a, b) => {
    const aStats = statsMap.get(a.id)!
    const bStats = statsMap.get(b.id)!
    return aStats.playPercentage - bStats.playPercentage
  })

  // Sort bucket 3 by loop count (ascending = least re-watched first)
  completed.sort((a, b) => {
    const aStats = statsMap.get(a.id)!
    const bStats = statsMap.get(b.id)!
    return aStats.loopCount - bStats.loopCount
  })

  // Concatenate: unwatched first, then started, then completed
  return [...unwatched, ...started, ...completed]
}
```

---

### Phase 4: Blob Pre-Cache Manager

**Create new file: `src/lib/videoCacheManager.ts`**

This class fetches video files ahead of time and stores them as blobs (binary data) in memory. When a video needs to play, it can use the pre-cached blob instead of waiting for a network download.

```ts
import type { Video } from '../types'
import { fileUrl } from '../api'

/**
 * VideoCacheManager pre-fetches video blobs for upcoming videos.
 * 
 * It maintains a "window" around the currently active video:
 * - 2 videos behind (for scroll-back)
 * - 5 videos ahead (for scroll-forward)
 * 
 * Everything outside this window gets evicted (deleted from memory).
 * 
 * IMPORTANT: This class is NOT a React component. It's plain TypeScript.
 * The SmartFeedContext creates one instance and keeps it in a useRef.
 */
export class VideoCacheManager {
  // Maps videoId → { blob, objectUrl }
  private cache = new Map<string, { blob: Blob; objectUrl: string }>()

  // Maps videoId → AbortController (for cancelling in-flight fetches)
  private pending = new Map<string, AbortController>()

  // How many videos ahead to pre-fetch
  private readonly LOOK_AHEAD = 5

  // How many videos behind to keep cached
  private readonly LOOK_BEHIND = 2

  /**
   * Call this whenever the active video changes.
   * It will start fetching new videos and evict old ones.
   */
  updateWindow(activeIndex: number, orderedFeed: Video[]): void {
    // Figure out which videoIds should be cached
    const keepStart = Math.max(0, activeIndex - this.LOOK_BEHIND)
    const keepEnd = Math.min(orderedFeed.length - 1, activeIndex + this.LOOK_AHEAD)

    const keepIds = new Set<string>()
    for (let i = keepStart; i <= keepEnd; i++) {
      keepIds.add(orderedFeed[i].id)
    }

    // Evict anything outside the window
    for (const [videoId, entry] of this.cache) {
      if (!keepIds.has(videoId)) {
        URL.revokeObjectURL(entry.objectUrl) // Free the memory
        this.cache.delete(videoId)
      }
    }

    // Cancel pending fetches that are no longer needed
    for (const [videoId, controller] of this.pending) {
      if (!keepIds.has(videoId)) {
        controller.abort()
        this.pending.delete(videoId)
      }
    }

    // Start fetching any videos in the window that aren't cached yet
    for (let i = keepStart; i <= keepEnd; i++) {
      const video = orderedFeed[i]
      if (!this.cache.has(video.id) && !this.pending.has(video.id)) {
        this.fetchAndCache(video)
      }
    }
  }

  /**
   * Returns the blob URL for a video if it's been pre-cached.
   * Returns null if not cached (VideoPlayer will fall back to the network URL).
   */
  getObjectUrl(videoId: string): string | null {
    return this.cache.get(videoId)?.objectUrl ?? null
  }

  /**
   * Fetches a single video blob and stores it.
   * Uses AbortController so we can cancel if the user scrolls past.
   */
  private async fetchAndCache(video: Video): Promise<void> {
    const url = fileUrl(video.files.video_url)
    if (!url) return

    const controller = new AbortController()
    this.pending.set(video.id, controller)

    try {
      const res = await fetch(url, { signal: controller.signal })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)

      const blob = await res.blob()
      const objectUrl = URL.createObjectURL(blob)

      this.cache.set(video.id, { blob, objectUrl })
    } catch (err: unknown) {
      // AbortError is expected when we cancel — don't log it
      if (err instanceof Error && err.name !== 'AbortError') {
        console.warn(`Failed to cache video ${video.id}:`, err)
      }
    } finally {
      this.pending.delete(video.id)
    }
  }

  /** Clean up everything. Called when the component unmounts. */
  destroy(): void {
    // Cancel all in-flight fetches
    for (const controller of this.pending.values()) {
      controller.abort()
    }
    this.pending.clear()

    // Revoke all blob URLs to free memory
    for (const entry of this.cache.values()) {
      URL.revokeObjectURL(entry.objectUrl)
    }
    this.cache.clear()
  }
}
```

**Key concept — Object URLs:** When we fetch a video file, we get a `Blob` (binary data). We can't pass a Blob directly to a `<video src="...">`. Instead, we call `URL.createObjectURL(blob)` which creates a special URL like `blob:http://localhost:5173/abc-123` that points to the in-memory data. When we're done, we call `URL.revokeObjectURL()` to free the memory.

---

### Phase 5: The SmartFeed Context (The Brain)

**Create new file: `src/context/SmartFeedContext.tsx`**

This is the most complex piece. It ties everything together.

```tsx
import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  useCallback,
  type ReactNode,
} from 'react'
import type { Video, VideoPlayStats, VideoSessionState } from '../types'
import { getAllStats, putManyStats } from '../lib/playStatsDb'
import { sortFeed } from '../lib/feedSort'
import { VideoCacheManager } from '../lib/videoCacheManager'

// ---- Types for the context value ----

interface SmartFeedContextValue {
  /** Videos in smart-sorted order */
  orderedFeed: Video[]

  /** Which video index is currently on screen */
  activeIndex: number

  /** Call this when the IntersectionObserver detects a new active video */
  setActiveIndex: (index: number) => void

  /** Call this from VideoPlayer on timeupdate (throttled to 1/sec by caller) */
  updatePlayProgress: (videoId: string, currentTime: number, duration: number) => void

  /** Call this when a video reaches >=95% */
  markLoopCompleted: (videoId: string) => void

  /** Returns the pre-cached blob URL for a video, or null */
  blobUrlFor: (videoId: string) => string | null

  /** Returns session state (savedPosition, direction) for a video */
  getSessionState: (videoId: string) => VideoSessionState
}

const SmartFeedContext = createContext<SmartFeedContextValue | null>(null)

// ---- Custom hook to use the context ----

export function useSmartFeed(): SmartFeedContextValue {
  const ctx = useContext(SmartFeedContext)
  if (!ctx) throw new Error('useSmartFeed must be used within SmartFeedProvider')
  return ctx
}

// ---- Provider component ----

interface ProviderProps {
  videos: Video[]       // The raw videos from the API
  children: ReactNode
}

export function SmartFeedProvider({ videos, children }: ProviderProps) {
  // ---- State ----
  const [orderedFeed, setOrderedFeed] = useState<Video[]>([])
  const [activeIndex, setActiveIndexState] = useState(0)
  const [ready, setReady] = useState(false)

  // ---- Refs (mutable values that don't trigger re-renders) ----
  const statsMapRef = useRef(new Map<string, VideoPlayStats>())
  const sessionMapRef = useRef(new Map<string, VideoSessionState>())
  const dirtyIdsRef = useRef(new Set<string>()) // videoIds with unsaved changes
  const cacheManagerRef = useRef(new VideoCacheManager())
  const prevIndexRef = useRef(0)

  // ---- On mount: load stats from IndexedDB, sort the feed ----
  useEffect(() => {
    let cancelled = false

    getAllStats().then(stats => {
      if (cancelled) return

      // Build the statsMap from stored data
      const map = new Map<string, VideoPlayStats>()
      for (const s of stats) {
        map.set(s.videoId, s)
      }
      statsMapRef.current = map

      // Sort the feed and store it
      const sorted = sortFeed(videos, map)
      setOrderedFeed(sorted)
      setReady(true)

      // Start pre-caching from index 0
      cacheManagerRef.current.updateWindow(0, sorted)
    }).catch(err => {
      console.warn('Failed to load play stats, using unsorted feed:', err)
      if (!cancelled) {
        setOrderedFeed(videos)
        setReady(true)
        cacheManagerRef.current.updateWindow(0, videos)
      }
    })

    return () => { cancelled = true }
  }, [videos])

  // ---- Flush dirty stats to IndexedDB ----
  const flushStats = useCallback(() => {
    const dirtyIds = dirtyIdsRef.current
    if (dirtyIds.size === 0) return

    const statsToSave: VideoPlayStats[] = []
    for (const id of dirtyIds) {
      const stat = statsMapRef.current.get(id)
      if (stat) statsToSave.push(stat)
    }
    dirtyIdsRef.current = new Set()

    putManyStats(statsToSave).catch(err => {
      console.warn('Failed to flush stats:', err)
      // Put them back in dirty set so we retry next flush
      for (const s of statsToSave) dirtyIdsRef.current.add(s.videoId)
    })
  }, [])

  // ---- Periodic flush (every 30 seconds) + visibilitychange ----
  useEffect(() => {
    const interval = setInterval(flushStats, 30_000)

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'hidden') {
        flushStats()
      }
    }
    document.addEventListener('visibilitychange', handleVisibilityChange)

    return () => {
      clearInterval(interval)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
      flushStats() // Flush on unmount too
      cacheManagerRef.current.destroy()
    }
  }, [flushStats])

  // ---- setActiveIndex: called by VideoFeed's IntersectionObserver ----
  const setActiveIndex = useCallback((index: number) => {
    const prev = prevIndexRef.current
    const direction: 'forward' | 'back' = index >= prev ? 'forward' : 'back'

    // Store the direction for the video we're scrolling TO
    const feed = orderedFeed
    if (feed[index]) {
      const videoId = feed[index].id
      const existing = sessionMapRef.current.get(videoId)
      sessionMapRef.current.set(videoId, {
        savedPosition: existing?.savedPosition ?? 0,
        direction,
      })
    }

    prevIndexRef.current = index
    setActiveIndexState(index)

    // Update the pre-cache window
    cacheManagerRef.current.updateWindow(index, feed)
  }, [orderedFeed])

  // ---- updatePlayProgress: called by VideoPlayer every ~1 second ----
  const updatePlayProgress = useCallback((
    videoId: string,
    currentTime: number,
    duration: number
  ) => {
    if (!duration || !isFinite(duration)) return

    const percentage = Math.min(100, (currentTime / duration) * 100)

    // Update stats (only increase playPercentage — it's a high-water mark)
    let stat = statsMapRef.current.get(videoId)
    if (!stat) {
      stat = { videoId, playPercentage: 0, loopCount: 0, seen: false }
      statsMapRef.current.set(videoId, stat)
    }
    if (percentage > stat.playPercentage) {
      stat.playPercentage = percentage
      dirtyIdsRef.current.add(videoId)
    }

    // Always update session position (for resume on scroll-back)
    sessionMapRef.current.set(videoId, {
      ...sessionMapRef.current.get(videoId),
      savedPosition: currentTime,
      direction: sessionMapRef.current.get(videoId)?.direction ?? null,
    })
  }, [])

  // ---- markLoopCompleted: called when a video reaches >=95% ----
  const markLoopCompleted = useCallback((videoId: string) => {
    let stat = statsMapRef.current.get(videoId)
    if (!stat) {
      stat = { videoId, playPercentage: 95, loopCount: 0, seen: false }
      statsMapRef.current.set(videoId, stat)
    }
    stat.loopCount += 1
    stat.seen = true
    dirtyIdsRef.current.add(videoId)
  }, [])

  // ---- blobUrlFor: check if a video is pre-cached ----
  const blobUrlFor = useCallback((videoId: string): string | null => {
    return cacheManagerRef.current.getObjectUrl(videoId)
  }, [])

  // ---- getSessionState: get resume position + direction ----
  const getSessionState = useCallback((videoId: string): VideoSessionState => {
    return sessionMapRef.current.get(videoId) ?? { savedPosition: 0, direction: null }
  }, [])

  // ---- Don't render children until stats are loaded ----
  if (!ready) return null

  return (
    <SmartFeedContext.Provider
      value={{
        orderedFeed,
        activeIndex,
        setActiveIndex,
        updatePlayProgress,
        markLoopCompleted,
        blobUrlFor,
        getSessionState,
      }}
    >
      {children}
    </SmartFeedContext.Provider>
  )
}
```

**Key concepts explained:**
- **`useRef` vs `useState`:** We use `useRef` for `statsMap`, `sessionMap`, etc. because updating them should NOT cause a re-render. They change frequently (every second during playback), and re-rendering the entire feed each time would be terrible for performance. `useState` is only for things that should update the UI (like `orderedFeed` and `activeIndex`).
- **Dirty tracking:** Instead of writing to IndexedDB on every update, we track which videoIds have changed (`dirtyIdsRef`) and batch-write them every 30 seconds or when the app goes to background.
- **`ready` flag:** We don't render the feed until IndexedDB stats are loaded, so the feed appears already sorted.

---

### Phase 6: Wire Up App.tsx

**File: `src/App.tsx`**

Changes:
1. Import `SmartFeedProvider`
2. Wrap `<VideoFeed>` with it
3. Remove the `videos` prop from `<VideoFeed>`

```tsx
import { useEffect, useState } from 'react'
import { fetchVideos } from './api'
import type { Video } from './types'
import { SmartFeedProvider } from './context/SmartFeedContext'
import VideoFeed from './components/VideoFeed'

export default function App() {
  const [videos, setVideos] = useState<Video[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchVideos()
      .then(vs => setVideos(vs.filter(v => v.files.video_url)))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center bg-black">
        <p className="text-white text-sm">Loading...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="h-full flex items-center justify-center bg-black">
        <p className="text-red-400 text-sm">{error}</p>
      </div>
    )
  }

  if (videos.length === 0) {
    return (
      <div className="h-full flex items-center justify-center bg-black">
        <p className="text-white/50 text-sm">No videos available</p>
      </div>
    )
  }

  return (
    <div className="w-screen bg-black overflow-hidden" style={{ height: '100dvh' }}>
      <div className="h-full max-w-sm mx-auto relative">
        <SmartFeedProvider videos={videos}>
          <VideoFeed />
        </SmartFeedProvider>
      </div>
    </div>
  )
}
```

---

### Phase 7: Update VideoFeed.tsx

**File: `src/components/VideoFeed.tsx`**

Remove the `videos` prop and read everything from the SmartFeed context instead.

```tsx
import { useEffect, useRef } from 'react'
import { SubtitleSettingsProvider } from '../context/SubtitleSettingsContext'
import { useSmartFeed } from '../context/SmartFeedContext'
import VideoPlayer from './VideoPlayer'

export default function VideoFeed() {
  const {
    orderedFeed,
    activeIndex,
    setActiveIndex,
    updatePlayProgress,
    markLoopCompleted,
    blobUrlFor,
    getSessionState,
  } = useSmartFeed()

  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const observer = new IntersectionObserver(
      entries => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            const idx = Number((entry.target as HTMLElement).dataset.index)
            setActiveIndex(idx)
          }
        }
      },
      { root: container, threshold: 0.6 }
    )

    const items = container.querySelectorAll('[data-index]')
    items.forEach(el => observer.observe(el))

    return () => observer.disconnect()
  }, [orderedFeed, setActiveIndex])

  return (
    <SubtitleSettingsProvider>
      <div
        ref={containerRef}
        className="h-full overflow-y-scroll snap-y snap-mandatory"
        style={{ scrollbarWidth: 'none' }}
      >
        {orderedFeed.map((video, i) => (
          <div
            key={video.id}
            data-index={i}
            className="w-full h-full snap-start snap-always shrink-0"
          >
            <VideoPlayer
              video={video}
              active={i === activeIndex}
              blobSrc={blobUrlFor(video.id)}
              sessionState={getSessionState(video.id)}
              onPlayProgress={updatePlayProgress}
              onLoopComplete={markLoopCompleted}
            />
          </div>
        ))}
      </div>
    </SubtitleSettingsProvider>
  )
}
```

**What changed from the original:**
- No more `videos` prop — reads `orderedFeed` from context
- No more local `activeIndex` state — managed by context
- Passes new props to `VideoPlayer`: `blobSrc`, `sessionState`, `onPlayProgress`, `onLoopComplete`
- `useEffect` dependency changed from `[videos]` to `[orderedFeed, setActiveIndex]`

---

### Phase 8: Update VideoPlayer.tsx

**File: `src/components/VideoPlayer.tsx`**

This is the trickiest part. We need to:
1. Use the blob URL when available (pre-cached), fall back to network URL
2. Track play progress (throttled to 1 report per second)
3. Detect when a video reaches 95% (loop completion)
4. Resume or restart based on scroll direction

```tsx
import { useRef, useEffect, useState, useCallback } from 'react'
import type { Video, VideoSessionState } from '../types'
import { fileUrl } from '../api'
import { useVtt } from '../hooks/useVtt'
import { useWakeLock } from '../hooks/useWakeLock'
import SubtitleOverlay from './SubtitleOverlay'
import ChannelBar from './ChannelBar'
import CommentsPanel from './CommentsPanel'
import SubtitleSettingsPanel from './SubtitleSettingsPanel'

interface Props {
  video: Video
  active: boolean
  blobSrc?: string | null
  sessionState?: VideoSessionState
  onPlayProgress?: (videoId: string, currentTime: number, duration: number) => void
  onLoopComplete?: (videoId: string) => void
}

export default function VideoPlayer({
  video,
  active,
  blobSrc,
  sessionState,
  onPlayProgress,
  onLoopComplete,
}: Props) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [commentsOpen, setCommentsOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [paused, setPaused] = useState(false)
  const touchStartX = useRef(0)
  const touchStartY = useRef(0)
  const progressRef = useRef<HTMLDivElement>(null)
  const isDragging = useRef(false)

  // ---- NEW REFS for tracking ----
  // Tracks whether we've already reported the >=95% loop for this play-through
  const hasReportedLoop = useRef(false)
  // Throttle: only report progress when the floored second changes
  const lastReportedSecond = useRef(-1)

  // ---- Video source: prefer blob, fall back to network ----
  const networkSrc = fileUrl(video.files.video_url)
  const videoSrc = blobSrc ?? networkSrc

  const vttSrc = fileUrl(video.files.vtt_url)
  const cues = useVtt(vttSrc)

  useWakeLock(videoRef)

  // ---- Play/pause when active changes + resume/restart logic ----
  useEffect(() => {
    const el = videoRef.current
    if (!el) return

    if (active) {
      // Decide where to start playback
      const direction = sessionState?.direction ?? 'forward'
      const savedPos = sessionState?.savedPosition ?? 0
      const dur = el.duration || 0

      if (direction === 'back' && dur > 0) {
        // Scrolling BACK to this video
        const percentPlayed = dur > 0 ? (savedPos / dur) * 100 : 0
        if (percentPlayed >= 90) {
          // Almost finished — restart from beginning
          el.currentTime = 0
        } else {
          // Resume from where they left off
          el.currentTime = savedPos
        }
      } else {
        // Scrolling FORWARD (or first time) — always start from beginning
        el.currentTime = 0
      }

      el.play().catch(() => {})
      setPaused(false)

      // Reset loop detection for this new viewing
      hasReportedLoop.current = false
      lastReportedSecond.current = -1
    } else {
      el.pause()
      // NOTE: We no longer reset currentTime to 0 here!
      // The savedPosition in sessionState preserves where we left off.
    }
  }, [active, sessionState])

  // ---- Time update handler (with throttled progress reporting) ----
  const handleTimeUpdate = useCallback(() => {
    const el = videoRef.current
    if (!el) return

    const ct = el.currentTime
    const dur = el.duration
    setCurrentTime(ct)

    // Guard against invalid duration
    if (!dur || !isFinite(dur)) return

    // ---- Throttled progress reporting (once per second) ----
    const flooredSecond = Math.floor(ct)
    if (flooredSecond !== lastReportedSecond.current) {
      lastReportedSecond.current = flooredSecond
      onPlayProgress?.(video.id, ct, dur)
    }

    // ---- Loop detection ----
    const percentage = (ct / dur) * 100

    if (percentage >= 95 && !hasReportedLoop.current) {
      // Video has reached 95% — count it as a completed loop
      hasReportedLoop.current = true
      onLoopComplete?.(video.id)
    }

    if (percentage < 10) {
      // Video looped back to the beginning (the <video loop> attribute did this)
      // Reset so we can detect the next loop
      hasReportedLoop.current = false
    }
  }, [video.id, onPlayProgress, onLoopComplete])

  const handleLoadedMetadata = useCallback(() => {
    setDuration(videoRef.current?.duration ?? 0)
  }, [])

  const seekToPosition = useCallback((clientX: number) => {
    const bar = progressRef.current
    const el = videoRef.current
    if (!bar || !el || !duration) return
    const rect = bar.getBoundingClientRect()
    const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width))
    el.currentTime = ratio * duration
    setCurrentTime(ratio * duration)
  }, [duration])

  const handleProgressMouseDown = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    isDragging.current = true
    seekToPosition(e.clientX)
    const onMove = (ev: MouseEvent) => { if (isDragging.current) seekToPosition(ev.clientX) }
    const onUp = () => { isDragging.current = false; window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onUp) }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }, [seekToPosition])

  const handleProgressTouchStart = useCallback((e: React.TouchEvent) => {
    e.stopPropagation()
    isDragging.current = true
    seekToPosition(e.touches[0].clientX)
    const onMove = (ev: TouchEvent) => { if (isDragging.current) seekToPosition(ev.touches[0].clientX) }
    const onEnd = () => { isDragging.current = false; window.removeEventListener('touchmove', onMove); window.removeEventListener('touchend', onEnd) }
    window.addEventListener('touchmove', onMove)
    window.addEventListener('touchend', onEnd)
  }, [seekToPosition])

  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    touchStartX.current = e.touches[0].clientX
    touchStartY.current = e.touches[0].clientY
  }, [])

  const handleTouchEnd = useCallback((e: React.TouchEvent) => {
    if (!commentsOpen) return
    const dx = e.changedTouches[0].clientX - touchStartX.current
    const dy = Math.abs(e.changedTouches[0].clientY - touchStartY.current)
    if (touchStartX.current < 30 && dx > 60 && dy < 80) {
      setCommentsOpen(false)
    }
  }, [commentsOpen])

  const togglePlay = useCallback(() => {
    const el = videoRef.current
    if (!el) return
    if (el.paused) {
      el.play().catch(() => {})
      setPaused(false)
    } else {
      el.pause()
      setPaused(true)
    }
  }, [])

  if (!videoSrc) return null

  return (
    <div
      className="relative w-full h-full bg-black flex items-center justify-center snap-start snap-always shrink-0 overflow-hidden"
      onTouchStart={handleTouchStart}
      onTouchEnd={handleTouchEnd}
    >
      <video
        ref={videoRef}
        src={videoSrc}
        className="w-full h-full object-cover"
        loop
        playsInline
        muted={false}
        onTimeUpdate={handleTimeUpdate}
        onLoadedMetadata={handleLoadedMetadata}
        onClick={togglePlay}
      />

      {paused && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="w-16 h-16 rounded-full bg-black/40 flex items-center justify-center">
            <span className="text-white text-3xl">&#9654;</span>
          </div>
        </div>
      )}

      <div
        ref={progressRef}
        className="absolute left-0 right-0 h-1 cursor-pointer group"
        style={{ bottom: 'calc(env(safe-area-inset-bottom) + 0.5rem)', zIndex: 20 }}
        onMouseDown={handleProgressMouseDown}
        onTouchStart={handleProgressTouchStart}
      >
        <div className="absolute inset-x-0 -top-2 bottom-0" />
        <div className="absolute inset-0 bg-white/20" />
        <div
          className="absolute inset-y-0 left-0 bg-white/70 transition-none"
          style={{ width: `${duration > 0 ? (currentTime / duration) * 100 : 0}%` }}
        />
      </div>

      <SubtitleOverlay cues={cues} currentTime={currentTime} />

      <ChannelBar
        video={video}
        onCommentsOpen={() => setCommentsOpen(true)}
        onSettingsOpen={() => setSettingsOpen(true)}
      />

      <CommentsPanel
        videoId={video.id}
        open={commentsOpen}
        onClose={() => setCommentsOpen(false)}
      />

      <SubtitleSettingsPanel open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  )
}
```

**What changed from the original VideoPlayer:**
1. **New props:** `blobSrc`, `sessionState`, `onPlayProgress`, `onLoopComplete`
2. **Video src:** Uses `blobSrc ?? fileUrl(...)` instead of just `fileUrl(...)`
3. **Active effect:** No longer always resets to `currentTime = 0`. Now checks `sessionState.direction` — resumes on scroll-back (unless >=90%), restarts on scroll-forward
4. **handleTimeUpdate:** Added throttled progress reporting (1/sec) and loop detection (>=95%)
5. **Two new refs:** `hasReportedLoop` and `lastReportedSecond`
6. **No longer resets `currentTime = 0`** when video becomes inactive — the position is preserved in session state

---

## Testing Checklist

After implementing all phases, test these scenarios:

1. **Basic feed loads** — `npm run dev`, app shows videos in feed order
2. **Stats persist** — Watch a video >50%, reload, check DevTools > Application > IndexedDB > `frtiktok-playstats` > `stats` — should see a row for that video
3. **Feed sorting** — Watch one video fully (past 95%), reload — it should appear at the end of the feed
4. **Partial watch sorting** — Watch 3 videos to different points (20%, 50%, 80%), reload — they should appear after unwatched videos, sorted 20% → 50% → 80%
5. **Scroll-back resume** — Scroll forward past a video, scroll back to it — should resume from where you left off
6. **Scroll-back restart at 90%** — Watch a video to 92%, scroll forward, scroll back — should restart from 0 (not resume at 92%)
7. **Scroll-forward restart** — Watch a video partially, scroll forward past it, then continue forward until you loop back — should restart from 0
8. **Loop counting** — Watch a video past 95% three times (let it loop), reload, check IndexedDB — `loopCount` should be 3
9. **Pre-caching** — Open DevTools > Network, look for blob fetches for videos you haven't scrolled to yet. Should see ~5 fetches on load
10. **Fast scroll** — Scroll quickly through 10 videos — should see cancelled network requests in DevTools (the abort controller working)

---

## File Summary

| Action | File | What |
|--------|------|------|
| EDIT | `src/types.ts` | Add `VideoPlayStats` + `VideoSessionState` interfaces |
| CREATE | `src/lib/playStatsDb.ts` | IndexedDB read/write helpers |
| CREATE | `src/lib/feedSort.ts` | Pure feed sorting function |
| CREATE | `src/lib/videoCacheManager.ts` | Blob pre-cache manager class |
| CREATE | `src/context/SmartFeedContext.tsx` | Central coordination context |
| EDIT | `src/App.tsx` | Wrap VideoFeed with SmartFeedProvider |
| EDIT | `src/components/VideoFeed.tsx` | Read from context, pass new props |
| EDIT | `src/components/VideoPlayer.tsx` | Add tracking, blob src, resume logic |
