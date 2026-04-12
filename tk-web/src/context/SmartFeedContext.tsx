import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  useCallback,
  type ReactNode,
} from 'react'
import type { FeedVideo, VideoPlayStats, VideoSessionState } from '../types'
import { syncProgress } from '../api'

interface SmartFeedContextValue {
  orderedFeed: FeedVideo[]
  activeIndex: number
  setActiveIndex: (index: number) => void
  updatePlayProgress: (videoId: string, currentTime: number, duration: number) => void
  markLoopCompleted: (videoId: string) => void
  getSessionState: (videoId: string) => VideoSessionState
  deleteVideo: (videoId: string) => Promise<void>
}

const SmartFeedContext = createContext<SmartFeedContextValue | null>(null)

export function useSmartFeed(): SmartFeedContextValue {
  const ctx = useContext(SmartFeedContext)
  if (!ctx) throw new Error('useSmartFeed must be used within SmartFeedProvider')
  return ctx
}

interface ProviderProps {
  videos: FeedVideo[]
  onDeleteVideo: (videoId: string) => Promise<void>
  children: ReactNode
}

export function SmartFeedProvider({ videos, onDeleteVideo, children }: ProviderProps) {
  const [orderedFeed, setOrderedFeed] = useState<FeedVideo[]>([])
  const [activeIndex, setActiveIndexState] = useState(0)
  const [ready, setReady] = useState(false)

  const statsMapRef = useRef(new Map<string, VideoPlayStats>())
  const sessionMapRef = useRef(new Map<string, VideoSessionState>())
  const dirtyIdsRef = useRef(new Set<string>())
  const prevIndexRef = useRef(0)

  useEffect(() => {
    const existing = statsMapRef.current
    const map = new Map<string, VideoPlayStats>()
    for (const v of videos) {
      const current = existing.get(v.id)
      if (current) {
        map.set(v.id, current)
        continue
      }
      if (v.watch_progress) {
        map.set(v.id, {
          videoId: v.id,
          playPercentage: v.watch_progress.play_percentage,
          loopCount: v.watch_progress.loop_count,
          seen: v.watch_progress.seen,
        })
      }
    }
    statsMapRef.current = map
    setOrderedFeed(videos)
    setReady(true)
  }, [videos])

  const flushStats = useCallback(() => {
    const dirtyIds = dirtyIdsRef.current
    if (dirtyIds.size === 0) return

    const ids = [...dirtyIds]
    dirtyIdsRef.current = new Set()

    for (const id of ids) {
      const stat = statsMapRef.current.get(id)
      if (!stat) continue
      const session = sessionMapRef.current.get(id)

      syncProgress(id, {
        play_percentage: Math.round(stat.playPercentage),
        loop_count: stat.loopCount,
        seen: stat.seen,
        saved_position: Math.round(session?.savedPosition ?? 0),
      }).catch(err => {
        console.warn(`Failed to sync progress for ${id}:`, err)
        dirtyIdsRef.current.add(id)
      })
    }
  }, [])

  useEffect(() => {
    const interval = setInterval(flushStats, 30_000)

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'hidden') {
        flushStats()
      }
    }
    document.addEventListener('visibilitychange', handleVisibilityChange)

    return () => {
      clearInterval(interval)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
      flushStats()
    }
  }, [flushStats])

  const setActiveIndex = useCallback((index: number) => {
    const prev = prevIndexRef.current
    const direction: 'forward' | 'back' = index >= prev ? 'forward' : 'back'

    const feed = orderedFeed
    if (feed[index]) {
      const videoId = feed[index].id
      const existing = sessionMapRef.current.get(videoId)
      sessionMapRef.current.set(videoId, {
        savedPosition: existing?.savedPosition ?? 0,
        direction,
      })
    }

    prevIndexRef.current = index
    setActiveIndexState(index)
  }, [orderedFeed])

  const updatePlayProgress = useCallback((
    videoId: string,
    currentTime: number,
    duration: number
  ) => {
    if (!duration || !isFinite(duration)) return

    const percentage = Math.min(100, (currentTime / duration) * 100)

    let stat = statsMapRef.current.get(videoId)
    if (!stat) {
      stat = { videoId, playPercentage: 0, loopCount: 0, seen: false }
      statsMapRef.current.set(videoId, stat)
    }
    if (percentage > stat.playPercentage) {
      stat.playPercentage = percentage
      dirtyIdsRef.current.add(videoId)
    }

    sessionMapRef.current.set(videoId, {
      ...sessionMapRef.current.get(videoId),
      savedPosition: currentTime,
      direction: sessionMapRef.current.get(videoId)?.direction ?? null,
    })
  }, [])

  const markLoopCompleted = useCallback((videoId: string) => {
    let stat = statsMapRef.current.get(videoId)
    if (!stat) {
      stat = { videoId, playPercentage: 95, loopCount: 0, seen: false }
      statsMapRef.current.set(videoId, stat)
    }
    stat.loopCount += 1
    stat.seen = true
    dirtyIdsRef.current.add(videoId)
  }, [])

  const getSessionState = useCallback((videoId: string): VideoSessionState => {
    return sessionMapRef.current.get(videoId) ?? { savedPosition: 0, direction: null }
  }, [])

  const handleDeleteVideo = useCallback(async (videoId: string) => {
    await onDeleteVideo(videoId)
    statsMapRef.current.delete(videoId)
    sessionMapRef.current.delete(videoId)
    dirtyIdsRef.current.delete(videoId)
    setOrderedFeed(prev => {
      const next = prev.filter(v => v.id !== videoId)
      setActiveIndexState(idx => {
        const clamped = Math.min(idx, next.length - 1)
        prevIndexRef.current = clamped
        return Math.max(0, clamped)
      })
      return next
    })
  }, [onDeleteVideo])

  if (!ready) return null

  return (
    <SmartFeedContext.Provider
      value={{
        orderedFeed,
        activeIndex,
        setActiveIndex,
        updatePlayProgress,
        markLoopCompleted,
        getSessionState,
        deleteVideo: handleDeleteVideo,
      }}
    >
      {children}
    </SmartFeedContext.Provider>
  )
}
