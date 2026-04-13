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
  sessionState?: VideoSessionState
  onPlayProgress?: (videoId: string, currentTime: number, duration: number) => void
  onLoopComplete?: (videoId: string) => void
  onDelete?: () => void
  shouldLoadVideo: boolean
  shouldLoadSubtitles: boolean
}

export default function VideoPlayer({
  video,
  active,
  sessionState,
  onPlayProgress,
  onLoopComplete,
  onDelete,
  shouldLoadVideo,
  shouldLoadSubtitles,
}: Props) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [isReadyToPlay, setIsReadyToPlay] = useState(false)
  const [showLoadingOverlay, setShowLoadingOverlay] = useState(false)
  const [commentsOpen, setCommentsOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false)
  const [paused, setPaused] = useState(true)
  const touchStartX = useRef(0)
  const touchStartY = useRef(0)
  const progressRef = useRef<HTMLDivElement>(null)
  const isDragging = useRef(false)

  const hasReportedLoop = useRef(false)
  const lastReportedSecond = useRef(-1)

  const videoSrc = shouldLoadVideo ? (fileUrl(video.files.video_url) ?? '') : ''

  const vttSrc = fileUrl(video.files.vtt_url)
  const cues = useVtt(shouldLoadSubtitles ? vttSrc : null)

  useWakeLock(videoRef)

  useEffect(() => {
    const el = videoRef.current
    if (!el || (active && videoSrc)) return

    el.pause()
    el.removeAttribute('src')
    el.load()
    setCurrentTime(0)
    setDuration(0)
    setIsReadyToPlay(false)
    setShowLoadingOverlay(false)
    setPaused(true)
  }, [active, videoSrc])

  useEffect(() => {
    const el = videoRef.current
    if (!el) return

    const markReadyIfBuffered = () => {
      if (el.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
        setIsReadyToPlay(true)
      }
    }

    if (active && videoSrc) {
      markReadyIfBuffered()

      const direction = sessionState?.direction ?? 'forward'
      const savedPos = sessionState?.savedPosition ?? 0
      const dur = el.duration || 0

      if (direction === 'back' && dur > 0) {
        const percentPlayed = dur > 0 ? (savedPos / dur) * 100 : 0
        if (percentPlayed >= 90) {
          el.currentTime = 0
        } else {
          el.currentTime = savedPos
        }
      } else {
        el.currentTime = 0
      }

      setPaused(true)

      hasReportedLoop.current = false
      lastReportedSecond.current = -1
    } else {
      el.pause()
    }
  }, [active, sessionState, videoSrc])

  useEffect(() => {
    setIsReadyToPlay(false)
    setShowLoadingOverlay(false)
    setPaused(true)
  }, [video.id, videoSrc])

  useEffect(() => {
    if (!active || !videoSrc || isReadyToPlay) {
      setShowLoadingOverlay(false)
      return
    }

    const timeoutId = window.setTimeout(() => {
      setShowLoadingOverlay(true)
    }, 350)

    return () => {
      window.clearTimeout(timeoutId)
    }
  }, [active, isReadyToPlay, videoSrc])

  const handleTimeUpdate = useCallback(() => {
    const el = videoRef.current
    if (!el) return

    const ct = el.currentTime
    const dur = el.duration
    setCurrentTime(ct)

    if (!dur || !isFinite(dur)) return

    const flooredSecond = Math.floor(ct)
    if (flooredSecond !== lastReportedSecond.current) {
      lastReportedSecond.current = flooredSecond
      onPlayProgress?.(video.id, ct, dur)
    }

    const percentage = (ct / dur) * 100

    if (percentage >= 95 && !hasReportedLoop.current) {
      hasReportedLoop.current = true
      onLoopComplete?.(video.id)
    }

    if (percentage < 10) {
      hasReportedLoop.current = false
    }
  }, [video.id, onPlayProgress, onLoopComplete])

  const handleLoadedMetadata = useCallback(() => {
    setDuration(videoRef.current?.duration ?? 0)
  }, [])

  const handleCanPlay = useCallback(() => {
    setIsReadyToPlay(true)
  }, [])

  const handlePlaying = useCallback(() => {
    setIsReadyToPlay(true)
    setPaused(false)
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
      el.muted = false
      el.play()
        .then(() => {
          setPaused(false)
          setIsReadyToPlay(true)
        })
        .catch(() => {
          setPaused(true)
        })
    } else {
      el.pause()
      setPaused(true)
    }
  }, [])

  const confirmDelete = useCallback(() => {
    setDeleteConfirmOpen(false)
    onDelete?.()
  }, [onDelete])

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
        preload={active ? 'auto' : 'metadata'}
        onTimeUpdate={handleTimeUpdate}
        onLoadedMetadata={handleLoadedMetadata}
        onCanPlay={handleCanPlay}
        onPlaying={handlePlaying}
        onClick={togglePlay}
      />

      {active && showLoadingOverlay && !isReadyToPlay && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-black">
          <div className="flex flex-col items-center gap-3 text-white/80">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-white/25 border-t-white" />
            <p className="text-xs tracking-[0.18em] uppercase">Loading video</p>
          </div>
        </div>
      )}

      {paused && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none bg-black/20">
          <div className="w-16 h-16 rounded-full bg-black/50 flex items-center justify-center">
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
        onDelete={() => setDeleteConfirmOpen(true)}
      />

      {deleteConfirmOpen && (
        <div className="absolute inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-zinc-900 rounded-2xl p-6 mx-8 max-w-xs w-full">
            <p className="text-white text-sm font-medium mb-1">Delete this video?</p>
            <p className="text-white/60 text-xs mb-5">This will permanently remove the video and all related data.</p>
            <div className="flex gap-3">
              <button
                onClick={() => setDeleteConfirmOpen(false)}
                className="flex-1 py-2 rounded-lg bg-zinc-700 text-white text-sm"
              >
                Cancel
              </button>
              <button
                onClick={confirmDelete}
                className="flex-1 py-2 rounded-lg bg-red-600 text-white text-sm font-medium"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}

      <CommentsPanel
        videoId={video.id}
        open={commentsOpen}
        onClose={() => setCommentsOpen(false)}
      />

      <SubtitleSettingsPanel open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  )
}
