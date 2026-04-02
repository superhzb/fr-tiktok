import { useEffect, useRef, useState } from 'react'
import type { Video, SubtitleSettings } from '../types'
import VideoPlayer from './VideoPlayer'

interface Props {
  videos: Video[]
}

const DEFAULT_SETTINGS: SubtitleSettings = { position: 4, fontSize: 1, mode: 'both' }

export default function VideoFeed({ videos }: Props) {
  const [activeIndex, setActiveIndex] = useState(0)
  const [subtitleSettings, setSubtitleSettings] = useState<SubtitleSettings>(DEFAULT_SETTINGS)
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
          <VideoPlayer
            video={video}
            active={i === activeIndex}
            subtitleSettings={subtitleSettings}
            onSubtitleSettingsChange={setSubtitleSettings}
          />
        </div>
      ))}
    </div>
  )
}
