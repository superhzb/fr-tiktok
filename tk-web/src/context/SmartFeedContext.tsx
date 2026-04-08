import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  useCallback,
  type ReactNode,
} from 'react'
import type { Video, VideoPlayStats, VideoSessionState } from '../types'
import { getAllStats, putManyStats } from '../lib/playStatsDb'
import { sortFeed } from '../lib/feedSort'
import { VideoCacheManager } from '../lib/videoCacheManager'

interface SmartFeedContextValue {
  orderedFeed: Video[]
  activeIndex: number
  setActiveIndex: (index: number) => void
  updatePlayProgress: (videoId: string, currentTime: number, duration: number) => void
  markLoopCompleted: (videoId: string) => void
  blobUrlFor: (videoId: string) => string | null
  getSessionState: (videoId: string) => VideoSessionState
}

const SmartFeedContext = createContext<SmartFeedContextValue | null>(null)

export function useSmartFeed(): SmartFeedContextValue {
  const ctx = useContext(SmartFeedContext)
  if (!ctx) throw new Error('useSmartFeed must be used within SmartFeedProvider')
  return ctx
}

interface ProviderProps {
  videos: Video[]
  children: ReactNode
}

export function SmartFeedProvider({ videos, children }: ProviderProps) {
  const [orderedFeed, setOrderedFeed] = useState<Video[]>([])
  const [activeIndex, setActiveIndexState] = useState(0)
  const [ready, setReady] = useState(false)

  const statsMapRef = useRef(new Map<string, VideoPlayStats>())
  const sessionMapRef = useRef(new Map<string, VideoSessionState>())
  const dirtyIdsRef = useRef(new Set<string>())
  const cacheManagerRef = useRef(new VideoCacheManager())
  const prevIndexRef = useRef(0)

  useEffect(() => {
    let cancelled = false

    getAllStats().then(stats => {
      if (cancelled) return

      const map = new Map<string, VideoPlayStats>()
      for (const s of stats) {
        map.set(s.videoId, s)
      }
      statsMapRef.current = map

      const sorted = sortFeed(videos, map)
      setOrderedFeed(sorted)
      setReady(true)

      cacheManagerRef.current.updateWindow(0, sorted)
    }).catch(err => {
      console.warn('Failed to load play stats, using unsorted feed:', err)
      if (!cancelled) {
        setOrderedFeed(videos)
        setReady(true)
        cacheManagerRef.current.updateWindow(0, videos)
      }
    })

    return () => { cancelled = true }
  }, [videos])

  const flushStats = useCallback(() => {
    const dirtyIds = dirtyIdsRef.current
    if (dirtyIds.size === 0) return

    const statsToSave: VideoPlayStats[] = []
    for (const id of dirtyIds) {
      const stat = statsMapRef.current.get(id)
      if (stat) statsToSave.push(stat)
    }
    dirtyIdsRef.current = new Set()

    putManyStats(statsToSave).catch(err => {
      console.warn('Failed to flush stats:', err)
      for (const s of statsToSave) dirtyIdsRef.current.add(s.videoId)
    })
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
      cacheManagerRef.current.destroy()
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

    cacheManagerRef.current.updateWindow(index, feed)
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

  const blobUrlFor = useCallback((videoId: string): string | null => {
    return cacheManagerRef.current.getObjectUrl(videoId)
  }, [])

  const getSessionState = useCallback((videoId: string): VideoSessionState => {
    return sessionMapRef.current.get(videoId) ?? { savedPosition: 0, direction: null }
  }, [])

  if (!ready) return null

  return (
    <SmartFeedContext.Provider
      value={{
        orderedFeed,
        activeIndex,
        setActiveIndex,
        updatePlayProgress,
        markLoopCompleted,
        blobUrlFor,
        getSessionState,
      }}
    >
      {children}
    </SmartFeedContext.Provider>
  )
}
