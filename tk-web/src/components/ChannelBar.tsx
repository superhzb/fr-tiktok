import type { Video } from '../types'

interface Props {
  video: Video
  onCommentsOpen: () => void
  onSettingsOpen: () => void
  onDelete: () => void
}

function fmt(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K'
  return String(n)
}

export default function ChannelBar({ video, onCommentsOpen, onSettingsOpen, onDelete }: Props) {
  return (
    <>
      {/* Bottom-left: author + description */}
      <div className="absolute left-4 right-20 pointer-events-none" style={{ bottom: 'calc(1.5rem + env(safe-area-inset-bottom))' }}>
        <p className="text-white font-bold text-sm mb-1">@{video.author}</p>
        <p className="text-white text-xs opacity-80 line-clamp-2">{video.description}</p>
      </div>

      {/* Right-side action column */}
      <div className="absolute right-3 flex flex-col items-center gap-5" style={{ bottom: 'calc(1.5rem + env(safe-area-inset-bottom))' }}>
        {/* Likes */}
        <div className="flex flex-col items-center">
          <div className="w-10 h-10 rounded-full bg-white/20 backdrop-blur-sm flex items-center justify-center">
            <span className="text-white text-lg">&#10084;&#65039;</span>
          </div>
          <span className="text-white text-xs mt-1">{fmt(video.likes)}</span>
        </div>

        {/* Comments */}
        <button onClick={onCommentsOpen} className="flex flex-col items-center">
          <div className="w-10 h-10 rounded-full bg-white/20 backdrop-blur-sm flex items-center justify-center">
            <span className="text-white text-lg">&#128172;</span>
          </div>
          <span className="text-white text-xs mt-1">{fmt(video.comments_count)}</span>
        </button>

        {/* Settings */}
        <button onClick={onSettingsOpen} className="flex flex-col items-center">
          <div className="w-10 h-10 rounded-full bg-white/20 backdrop-blur-sm flex items-center justify-center">
            <span className="text-white text-lg">&#9881;</span>
          </div>
        </button>

        {/* Delete */}
        <button onClick={onDelete} className="flex flex-col items-center">
          <div className="w-10 h-10 rounded-full bg-white/20 backdrop-blur-sm flex items-center justify-center">
            <span className="text-white text-lg">&#128465;</span>
          </div>
        </button>
      </div>
    </>
  )
}
