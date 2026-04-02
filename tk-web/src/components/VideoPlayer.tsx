import { useRef, useEffect, useState, useCallback } from 'react'
import type { Video, SubtitleMode } from '../types'
import { fileUrl } from '../api'
import { useVtt } from '../hooks/useVtt'
import SubtitleOverlay from './SubtitleOverlay'
import ChannelBar from './ChannelBar'
import CommentsPanel from './CommentsPanel'

interface Props {
  video: Video
  active: boolean
}

const SUBTITLE_CYCLE: SubtitleMode[] = ['both', 'fr', 'zh']

export default function VideoPlayer({ video, active }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [currentTime, setCurrentTime] = useState(0)
  const [subtitleMode, setSubtitleMode] = useState<SubtitleMode>('both')
  const [commentsOpen, setCommentsOpen] = useState(false)
  const [paused, setPaused] = useState(false)

  const videoSrc = fileUrl(video.files.video_url)
  const vttSrc = fileUrl(video.files.vtt_url)
  const cues = useVtt(vttSrc)

  // Play/pause based on active prop
  useEffect(() => {
    const el = videoRef.current
    if (!el) return
    if (active) {
      el.play().catch(() => {})
      setPaused(false)
    } else {
      el.pause()
      el.currentTime = 0
    }
  }, [active])

  const handleTimeUpdate = useCallback(() => {
    setCurrentTime(videoRef.current?.currentTime ?? 0)
  }, [])

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

  const cycleSubtitles = useCallback(() => {
    setSubtitleMode(m => {
      const idx = SUBTITLE_CYCLE.indexOf(m)
      return SUBTITLE_CYCLE[(idx + 1) % SUBTITLE_CYCLE.length]
    })
  }, [])

  if (!videoSrc) return null

  return (
    <div className="relative w-full h-full bg-black flex items-center justify-center snap-start snap-always shrink-0">
      <video
        ref={videoRef}
        src={videoSrc}
        className="w-full h-full object-cover"
        loop
        playsInline
        muted={false}
        onTimeUpdate={handleTimeUpdate}
        onClick={togglePlay}
      />

      {/* Pause indicator */}
      {paused && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="w-16 h-16 rounded-full bg-black/40 flex items-center justify-center">
            <span className="text-white text-3xl">▶</span>
          </div>
        </div>
      )}

      <SubtitleOverlay cues={cues} currentTime={currentTime} mode={subtitleMode} />

      <ChannelBar
        video={video}
        subtitleMode={subtitleMode}
        onSubtitleToggle={cycleSubtitles}
        onCommentsOpen={() => setCommentsOpen(true)}
      />

      <CommentsPanel
        videoId={video.id}
        open={commentsOpen}
        onClose={() => setCommentsOpen(false)}
      />
    </div>
  )
}
