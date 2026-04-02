import type { Video, SubtitleMode } from '../types'

interface Props {
  video: Video
  subtitleMode: SubtitleMode
  onSubtitleToggle: () => void
  onCommentsOpen: () => void
}

function fmt(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K'
  return String(n)
}

const subtitleLabel: Record<SubtitleMode, string> = {
  fr: 'FR',
  zh: '中',
  both: 'FR\n中',
}

export default function ChannelBar({ video, subtitleMode, onSubtitleToggle, onCommentsOpen }: Props) {
  return (
    <>
      {/* Bottom-left: author + description */}
      <div className="absolute bottom-6 left-4 right-20 pointer-events-none">
        <p className="text-white font-bold text-sm mb-1">@{video.author}</p>
        <p className="text-white text-xs opacity-80 line-clamp-2">{video.description}</p>
      </div>

      {/* Right-side action column */}
      <div className="absolute bottom-6 right-3 flex flex-col items-center gap-5">
        {/* Subtitle toggle */}
        <button
          onClick={onSubtitleToggle}
          className="flex flex-col items-center"
        >
          <div className="w-10 h-10 rounded-full bg-white/20 backdrop-blur-sm flex items-center justify-center">
            <span className="text-white text-xs font-bold leading-none whitespace-pre-line text-center">
              {subtitleLabel[subtitleMode]}
            </span>
          </div>
          <span className="text-white text-xs mt-1 opacity-80">CC</span>
        </button>

        {/* Likes */}
        <div className="flex flex-col items-center">
          <div className="w-10 h-10 rounded-full bg-white/20 backdrop-blur-sm flex items-center justify-center">
            <span className="text-white text-lg">❤️</span>
          </div>
          <span className="text-white text-xs mt-1">{fmt(video.likes)}</span>
        </div>

        {/* Comments */}
        <button onClick={onCommentsOpen} className="flex flex-col items-center">
          <div className="w-10 h-10 rounded-full bg-white/20 backdrop-blur-sm flex items-center justify-center">
            <span className="text-white text-lg">💬</span>
          </div>
          <span className="text-white text-xs mt-1">{fmt(video.comments_count)}</span>
        </button>

        {/* Shares */}
        <div className="flex flex-col items-center">
          <div className="w-10 h-10 rounded-full bg-white/20 backdrop-blur-sm flex items-center justify-center">
            <span className="text-white text-lg">↗️</span>
          </div>
          <span className="text-white text-xs mt-1">{fmt(video.shares)}</span>
        </div>
      </div>
    </>
  )
}
