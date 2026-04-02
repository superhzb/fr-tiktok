import type { SubtitleCue, SubtitleMode } from '../types'

interface Props {
  cues: SubtitleCue[]
  currentTime: number
  mode: SubtitleMode
}

export default function SubtitleOverlay({ cues, currentTime, mode }: Props) {
  const cue = cues.find(c => currentTime >= c.startTime && currentTime <= c.endTime)
  if (!cue) return null

  return (
    <div className="absolute bottom-24 left-0 right-0 flex flex-col items-center px-4 pointer-events-none">
      {(mode === 'fr' || mode === 'both') && (
        <p className="text-white text-center text-base font-semibold drop-shadow-lg leading-snug"
           style={{ textShadow: '0 1px 3px rgba(0,0,0,0.9)' }}>
          {cue.fr}
        </p>
      )}
      {(mode === 'zh' || mode === 'both') && cue.zh && (
        <p className="text-yellow-300 text-center text-sm font-medium drop-shadow-lg leading-snug mt-0.5"
           style={{ textShadow: '0 1px 3px rgba(0,0,0,0.9)' }}>
          {cue.zh}
        </p>
      )}
    </div>
  )
}
