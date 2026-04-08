import { useEffect, useRef } from 'react'
import { SubtitleSettingsProvider } from '../context/SubtitleSettingsContext'
import { useSmartFeed } from '../context/SmartFeedContext'
import VideoPlayer from './VideoPlayer'

export default function VideoFeed() {
  const {
    orderedFeed,
    activeIndex,
    setActiveIndex,
    updatePlayProgress,
    markLoopCompleted,
    getSessionState,
  } = useSmartFeed()

  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const observer = new IntersectionObserver(
      entries => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            const idx = Number((entry.target as HTMLElement).dataset.index)
            setActiveIndex(idx)
          }
        }
      },
      { root: container, threshold: 0.6 }
    )

    const items = container.querySelectorAll('[data-index]')
    items.forEach(el => observer.observe(el))

    return () => observer.disconnect()
  }, [orderedFeed, setActiveIndex])

  return (
    <SubtitleSettingsProvider>
      <div
        ref={containerRef}
        className="h-full overflow-y-scroll snap-y snap-mandatory"
        style={{ scrollbarWidth: 'none' }}
      >
        {orderedFeed.map((video, i) => (
          <div
            key={video.id}
            data-index={i}
            className="w-full h-full snap-start snap-always shrink-0"
          >
            <VideoPlayer
              video={video}
              active={i === activeIndex}
              sessionState={getSessionState(video.id)}
              onPlayProgress={updatePlayProgress}
              onLoopComplete={markLoopCompleted}
            />
          </div>
        ))}
      </div>
    </SubtitleSettingsProvider>
  )
}
