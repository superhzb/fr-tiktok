const BASE =
  import.meta.env.VITE_API_BASE ??
  `${window.location.protocol}//${window.location.hostname}:8000`

export const fileUrl = (path: string | null) =>
  path ? `${BASE}${path}` : null

export async function fetchVideos(): Promise<import('./types').Video[]> {
  const res = await fetch(`${BASE}/videos?status=completed`)
  if (!res.ok) throw new Error('Failed to fetch videos')
  return res.json()
}

export async function fetchComments(videoId: string): Promise<import('./types').Comment[]> {
  const res = await fetch(`${BASE}/videos/${videoId}/comments`)
  if (!res.ok) throw new Error('Failed to fetch comments')
  return res.json()
}
