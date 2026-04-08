import type { Video } from '../types'
import { fileUrl } from '../api'

const CACHE_NAME = 'video-cache-v1'

export class VideoCacheManager {
  // Session-only: object URLs are in-memory and must be re-created each app open
  private objectUrls = new Map<string, string>()
  private pending = new Map<string, AbortController>()
  private readonly LOOK_AHEAD = 5
  private readonly LOOK_BEHIND = 2

  onReady: ((videoId: string, objectUrl: string) => void) | null = null

  updateWindow(activeIndex: number, orderedFeed: Video[]): void {
    const keepStart = Math.max(0, activeIndex - this.LOOK_BEHIND)
    const keepEnd = Math.min(orderedFeed.length - 1, activeIndex + this.LOOK_AHEAD)

    const keepIds = new Set<string>()
    for (let i = keepStart; i <= keepEnd; i++) {
      keepIds.add(orderedFeed[i].id)
    }

    // Revoke object URLs for videos leaving the window
    for (const [videoId, objectUrl] of this.objectUrls) {
      if (!keepIds.has(videoId)) {
        URL.revokeObjectURL(objectUrl)
        this.objectUrls.delete(videoId)
      }
    }

    // Abort in-flight fetches for videos leaving the window
    for (const [videoId, controller] of this.pending) {
      if (!keepIds.has(videoId)) {
        controller.abort()
        this.pending.delete(videoId)
      }
    }

    for (let i = keepStart; i <= keepEnd; i++) {
      const video = orderedFeed[i]
      if (!this.objectUrls.has(video.id) && !this.pending.has(video.id)) {
        this.ensureCached(video)
      }
    }
  }

  getObjectUrl(videoId: string): string | null {
    return this.objectUrls.get(videoId) ?? null
  }

  private async ensureCached(video: Video): Promise<void> {
    const url = fileUrl(video.files.video_url)
    if (!url) return

    const controller = new AbortController()
    this.pending.set(video.id, controller)

    try {
      const diskCache = await caches.open(CACHE_NAME)
      let response = await diskCache.match(url)

      if (!response) {
        // Not on disk — fetch from network and store
        const fetched = await fetch(url, { signal: controller.signal })
        if (!fetched.ok) throw new Error(`HTTP ${fetched.status}`)
        await diskCache.put(url, fetched.clone())
        response = fetched
      }

      const blob = await response.blob()
      const objectUrl = URL.createObjectURL(blob)
      this.objectUrls.set(video.id, objectUrl)
      this.onReady?.(video.id, objectUrl)
    } catch (err: unknown) {
      if (err instanceof Error && err.name !== 'AbortError') {
        console.warn(`Failed to cache video ${video.id}:`, err)
      }
    } finally {
      this.pending.delete(video.id)
    }
  }

  destroy(): void {
    for (const controller of this.pending.values()) {
      controller.abort()
    }
    this.pending.clear()

    // Revoke all session object URLs — but intentionally leave Cache API entries
    // intact so next session can skip the network fetch
    for (const objectUrl of this.objectUrls.values()) {
      URL.revokeObjectURL(objectUrl)
    }
    this.objectUrls.clear()
  }
}
