import { useEffect, useState } from 'react'
import { fetchVideos } from './api'
import type { Video } from './types'
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
    <div className="h-screen w-screen bg-black overflow-hidden">
      {/* Centered card on desktop */}
      <div className="h-full max-w-sm mx-auto relative">
        <VideoFeed videos={videos} />
      </div>
    </div>
  )
}
