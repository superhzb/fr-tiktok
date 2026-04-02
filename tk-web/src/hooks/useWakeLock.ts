import { useEffect, type RefObject } from 'react'

export function useWakeLock(videoRef: RefObject<HTMLVideoElement | null>) {
  useEffect(() => {
    const video = videoRef.current
    if (!video || !('wakeLock' in navigator)) return

    let wakeLock: WakeLockSentinel | null = null

    const acquire = () => {
      navigator.wakeLock.request('screen')
        .then(lock => { wakeLock = lock })
        .catch(() => {})
    }

    const release = () => {
      wakeLock?.release().catch(() => {})
      wakeLock = null
    }

    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible' && !video.paused) acquire()
    }

    video.addEventListener('play', acquire)
    video.addEventListener('pause', release)
    video.addEventListener('ended', release)
    document.addEventListener('visibilitychange', onVisibilityChange)

    return () => {
      video.removeEventListener('play', acquire)
      video.removeEventListener('pause', release)
      video.removeEventListener('ended', release)
      document.removeEventListener('visibilitychange', onVisibilityChange)
      release()
    }
  }, [videoRef])
}
