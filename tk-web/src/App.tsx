import { useEffect, useState, useCallback } from 'react'
import { fetchFeed, deleteVideo } from './api'
import type { FeedVideo } from './types'
import { SmartFeedProvider } from './context/SmartFeedContext'
import VideoFeed from './components/VideoFeed'

const INITIAL_FEED_BATCH_SIZE = 12

export default function App() {
  const [videos, setVideos] = useState<FeedVideo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    fetchFeed({ limit: INITIAL_FEED_BATCH_SIZE })
      .then(vs => {
        if (cancelled) return
        setVideos(vs.filter(v => v.files.video_url))
        setLoading(false)
      })
      .then(() => {
        return fetchFeed({ offset: INITIAL_FEED_BATCH_SIZE })
          .then(vs => {
            if (cancelled || vs.length === 0) return
            setVideos(prev => {
              const existing = new Set(prev.map(video => video.id))
              const next = vs.filter(v => v.files.video_url && !existing.has(v.id))
              return next.length > 0 ? [...prev, ...next] : prev
            })
          })
      })
      .catch(e => {
        if (!cancelled) {
          setError(e.message)
          setLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [])

  const handleDeleteVideo = useCallback(async (videoId: string) => {
    await deleteVideo(videoId)
    setVideos(prev => prev.filter(v => v.id !== videoId))
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
      {/* Centered card on desktop */}
      <div className="h-full max-w-sm mx-auto relative">
        <SmartFeedProvider videos={videos} onDeleteVideo={handleDeleteVideo}>
          <VideoFeed />
        </SmartFeedProvider>
      </div>
    </div>
  )
}
