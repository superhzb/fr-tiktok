import type { Video } from '../types'
import { fileUrl } from '../api'

export class VideoCacheManager {
  private cache = new Map<string, { blob: Blob; objectUrl: string }>()
  private pending = new Map<string, AbortController>()
  private readonly LOOK_AHEAD = 5
  private readonly LOOK_BEHIND = 2

  updateWindow(activeIndex: number, orderedFeed: Video[]): void {
    const keepStart = Math.max(0, activeIndex - this.LOOK_BEHIND)
    const keepEnd = Math.min(orderedFeed.length - 1, activeIndex + this.LOOK_AHEAD)

    const keepIds = new Set<string>()
    for (let i = keepStart; i <= keepEnd; i++) {
      keepIds.add(orderedFeed[i].id)
    }

    for (const [videoId, entry] of this.cache) {
      if (!keepIds.has(videoId)) {
        URL.revokeObjectURL(entry.objectUrl)
        this.cache.delete(videoId)
      }
    }

    for (const [videoId, controller] of this.pending) {
      if (!keepIds.has(videoId)) {
        controller.abort()
        this.pending.delete(videoId)
      }
    }

    for (let i = keepStart; i <= keepEnd; i++) {
      const video = orderedFeed[i]
      if (!this.cache.has(video.id) && !this.pending.has(video.id)) {
        this.fetchAndCache(video)
      }
    }
  }

  getObjectUrl(videoId: string): string | null {
    return this.cache.get(videoId)?.objectUrl ?? null
  }

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

    for (const entry of this.cache.values()) {
      URL.revokeObjectURL(entry.objectUrl)
    }
    this.cache.clear()
  }
}
