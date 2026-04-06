import { useRef, useEffect, useState, useCallback } from 'react'
import type { Video } from '../types'
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
}

export default function VideoPlayer({ video, active }: Props) {
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

  const videoSrc = fileUrl(video.files.video_url)
  const vttSrc = fileUrl(video.files.vtt_url)
  const cues = useVtt(vttSrc)

  useWakeLock(videoRef)

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
        onLoadedMetadata={handleLoadedMetadata}
        onClick={togglePlay}
      />

      {paused && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="w-16 h-16 rounded-full bg-black/40 flex items-center justify-center">
            <span className="text-white text-3xl">▶</span>
          </div>
        </div>
      )}

      {/* Progress bar */}
      <div
        ref={progressRef}
        className="absolute left-0 right-0 h-1 cursor-pointer group"
        style={{ bottom: 'calc(env(safe-area-inset-bottom) + 0.5rem)', zIndex: 20 }}
        onMouseDown={handleProgressMouseDown}
        onTouchStart={handleProgressTouchStart}
      >
        {/* hit area padding */}
        <div className="absolute inset-x-0 -top-2 bottom-0" />
        {/* track */}
        <div className="absolute inset-0 bg-white/20" />
        {/* fill */}
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
