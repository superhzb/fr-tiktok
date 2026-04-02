import type { SubtitleCue, SubtitleMode, SubtitlePosition, SubtitleFontSize } from '../types'

interface Props {
  cues: SubtitleCue[]
  currentTime: number
  mode: SubtitleMode
  position: SubtitlePosition
  fontSize: SubtitleFontSize
}

// top% for each position; pos 4 uses bottom anchor instead
const POSITION_TOP: Record<SubtitlePosition, string | null> = {
  0: '8%',
  1: '22%',
  2: '38%',
  3: '54%',
  4: null, // bottom-anchored
}

const FR_SIZE: Record<SubtitleFontSize, number> = { 0: 13, 1: 16, 2: 20 }
const ZH_SIZE: Record<SubtitleFontSize, number> = { 0: 11, 1: 13, 2: 17 }

export default function SubtitleOverlay({ cues, currentTime, mode, position, fontSize }: Props) {
  const cue = cues.find(c => currentTime >= c.startTime && currentTime <= c.endTime)
  if (!cue) return null

  const isBottom = position === 4
  const posStyle = isBottom
    ? { bottom: 'calc(130px)' }
    : { top: POSITION_TOP[position]! }

  return (
    <div
      className="absolute left-0 right-0 flex flex-col items-center px-4 pointer-events-none"
      style={posStyle}
    >
      <div className="inline-flex flex-col items-center rounded-md px-2 py-1 bg-black/75">
        {(mode === 'fr' || mode === 'both') && (
          <p
            className="text-white text-center font-semibold leading-snug"
            style={{ fontSize: FR_SIZE[fontSize] }}
          >
            {cue.fr}
          </p>
        )}
        {(mode === 'zh' || mode === 'both') && cue.zh && (
          <p
            className="text-yellow-300 text-center font-medium leading-snug mt-0.5"
            style={{ fontSize: ZH_SIZE[fontSize] }}
          >
            {cue.zh}
          </p>
        )}
      </div>
    </div>
  )
}
