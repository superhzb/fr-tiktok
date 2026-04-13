const BASE =
  import.meta.env.VITE_API_BASE ??
  `${window.location.protocol}//${window.location.hostname}:8000`

export const fileUrl = (path: string | null) =>
  path ? `${BASE}${path}` : null

interface FetchFeedOptions {
  limit?: number
  offset?: number
}

export async function fetchVideos(): Promise<import('./types').Video[]> {
  const res = await fetch(`${BASE}/videos?status=completed`)
  if (!res.ok) throw new Error('Failed to fetch videos')
  return res.json()
}

export async function fetchFeed(
  options: FetchFeedOptions = {}
): Promise<import('./types').FeedVideo[]> {
  const params = new URLSearchParams()
  if (options.limit !== undefined) params.set('limit', String(options.limit))
  if (options.offset !== undefined && options.offset > 0) {
    params.set('offset', String(options.offset))
  }
  const query = params.toString()
  const res = await fetch(`${BASE}/feed${query ? `?${query}` : ''}`)
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

export async function fetchComments(videoId: string): Promise<import('./types').Comment[]> {
  const res = await fetch(`${BASE}/videos/${videoId}/comments`)
  if (!res.ok) throw new Error('Failed to fetch comments')
  return res.json()
}
