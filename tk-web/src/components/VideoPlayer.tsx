import { useRef, useEffect, useState, useCallback } from 'react'
import type { Video, SubtitleSettings } from '../types'
import { fileUrl } from '../api'
import { useVtt } from '../hooks/useVtt'
import SubtitleOverlay from './SubtitleOverlay'
import ChannelBar from './ChannelBar'
import CommentsPanel from './CommentsPanel'
import SubtitleSettingsPanel from './SubtitleSettingsPanel'

interface Props {
  video: Video
  active: boolean
  subtitleSettings: SubtitleSettings
  onSubtitleSettingsChange: (s: SubtitleSettings) => void
}

export default function VideoPlayer({ video, active, subtitleSettings, onSubtitleSettingsChange }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [currentTime, setCurrentTime] = useState(0)
  const [commentsOpen, setCommentsOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [paused, setPaused] = useState(false)
  const touchStartX = useRef(0)
  const touchStartY = useRef(0)

  const videoSrc = fileUrl(video.files.video_url)
  const vttSrc = fileUrl(video.files.vtt_url)
  const cues = useVtt(vttSrc)

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

  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    touchStartX.current = e.touches[0].clientX
    touchStartY.current = e.touches[0].clientY
  }, [])

  const handleTouchEnd = useCallback((e: React.TouchEvent) => {
    if (!commentsOpen) return
    const dx = e.changedTouches[0].clientX - touchStartX.current
    const dy = Math.abs(e.changedTouches[0].clientY - touchStartY.current)
    // Left-edge swipe: starts within 30px of left, moves right >60px, not too vertical
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
        onClick={togglePlay}
      />

      {paused && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="w-16 h-16 rounded-full bg-black/40 flex items-center justify-center">
            <span className="text-white text-3xl">▶</span>
          </div>
        </div>
      )}

      <SubtitleOverlay
        cues={cues}
        currentTime={currentTime}
        mode={subtitleSettings.mode}
        position={subtitleSettings.position}
        fontSize={subtitleSettings.fontSize}
      />

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

      <SubtitleSettingsPanel
        open={settingsOpen}
        settings={subtitleSettings}
        onChange={onSubtitleSettingsChange}
        onClose={() => setSettingsOpen(false)}
      />
    </div>
  )
}
