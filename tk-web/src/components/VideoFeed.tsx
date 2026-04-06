import { useEffect, useRef, useState } from 'react'
import type { Video } from '../types'
import { SubtitleSettingsProvider } from '../context/SubtitleSettingsContext'
import VideoPlayer from './VideoPlayer'

interface Props {
  videos: Video[]
}

export default function VideoFeed({ videos }: Props) {
  const [activeIndex, setActiveIndex] = useState(0)
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
  }, [videos])

  return (
    <SubtitleSettingsProvider>
      <div
        ref={containerRef}
        className="h-full overflow-y-scroll snap-y snap-mandatory"
        style={{ scrollbarWidth: 'none' }}
      >
        {videos.map((video, i) => (
          <div
            key={video.id}
            data-index={i}
            className="w-full h-full snap-start snap-always shrink-0"
          >
            <VideoPlayer video={video} active={i === activeIndex} />
          </div>
        ))}
      </div>
    </SubtitleSettingsProvider>
  )
}
