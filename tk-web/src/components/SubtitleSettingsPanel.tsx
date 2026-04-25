import { useRef } from 'react'
import { useSubtitleSettings } from '../context/SubtitleSettingsContext'
import type { SubtitlePosition, SubtitleFontSize, SubtitleMode } from '../types'

interface Props {
  open: boolean
  onClose: () => void
}

const FONT_SIZES: { label: string; value: SubtitleFontSize; fontSize: number }[] = [
  { label: 'A', value: 0, fontSize: 18 },
  { label: 'A', value: 1, fontSize: 26 },
  { label: 'A', value: 2, fontSize: 34 },
]

const MODES: SubtitleMode[] = ['fr', 'both', 'zh']

function PositionSlider({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  const trackRef = useRef<HTMLDivElement>(null)

  function getValueFromX(clientX: number) {
    const rect = trackRef.current!.getBoundingClientRect()
    const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width))
    return Math.round(ratio * 4)
  }

  function onMouseDown(e: React.MouseEvent) {
    onChange(getValueFromX(e.clientX))
    const onMove = (ev: MouseEvent) => onChange(getValueFromX(ev.clientX))
    const onUp = () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  function onTouchStart(e: React.TouchEvent) {
    e.preventDefault()
    onChange(getValueFromX(e.touches[0].clientX))
    const onMove = (ev: TouchEvent) => onChange(getValueFromX(ev.touches[0].clientX))
    const onEnd = () => {
      window.removeEventListener('touchmove', onMove)
      window.removeEventListener('touchend', onEnd)
    }
    window.addEventListener('touchmove', onMove, { passive: false })
    window.addEventListener('touchend', onEnd)
  }

  const pct = (value / 4) * 100

  return (
    <div
      ref={trackRef}
      className="relative flex items-center h-12 cursor-pointer select-none"
      onMouseDown={onMouseDown}
      onTouchStart={onTouchStart}
    >
      {/* Track background */}
      <div className="absolute inset-x-0 h-1.5 rounded-full bg-white/20" />
      {/* Active fill */}
      <div
        className="absolute left-0 h-1.5 rounded-full bg-white/60"
        style={{ width: `${pct}%` }}
      />
      {/* Tick marks */}
      {[0, 1, 2, 3, 4].map(i => (
        <div
          key={i}
          className="absolute w-0.5 h-2 rounded-full bg-white/40 -translate-x-1/2"
          style={{ left: `${(i / 4) * 100}%` }}
        />
      ))}
      {/* Thumb */}
      <div
        className="absolute w-8 h-8 rounded-full bg-white shadow-lg -translate-x-1/2 transition-[left] duration-100"
        style={{ left: `${pct}%` }}
      />
    </div>
  )
}

export default function SubtitleSettingsPanel({ open, onClose }: Props) {
  const { settings, setSettings } = useSubtitleSettings()
  // Slider: 0=left=bottom(pos4), 4=right=top(pos0)
  const sliderValue = 4 - settings.position
  const modeIndex = MODES.indexOf(settings.mode)

  return (
    <div
      className={`absolute inset-x-0 bottom-0 z-40 transition-transform duration-300 ${
        open ? 'translate-y-0' : 'translate-y-full'
      }`}
    >
      {open && (
        <div className="absolute inset-x-0 bottom-full h-screen" onClick={onClose} />
      )}

      <div className="bg-black/80 backdrop-blur-md rounded-t-2xl px-5 py-4 border-t border-white/10">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <span className="text-white font-semibold text-sm">Subtitle Settings</span>
          <button onClick={onClose} className="text-white/50 text-xl leading-none">×</button>
        </div>

        {/* Language */}
        <div className="mb-4">
          <p className="text-white/60 text-xs mb-2 uppercase tracking-wide">Language</p>
          <button
            type="button"
            aria-label={`Subtitle language mode ${modeIndex + 1} of ${MODES.length}`}
            onClick={() => setSettings({ ...settings, mode: MODES[(modeIndex + 1) % MODES.length] })}
            className="flex h-9 w-16 items-center justify-center gap-2 rounded-full bg-white/15 transition-colors"
          >
            <span
              className={`h-2.5 w-2.5 rounded-full transition-colors ${
                settings.mode === 'zh' ? 'bg-white/30' : 'bg-white'
              }`}
            />
            <span
              className={`h-2.5 w-2.5 rounded-full transition-colors ${
                settings.mode === 'fr' ? 'bg-white/30' : 'bg-yellow-300'
              }`}
            />
          </button>
        </div>

        {/* Position */}
        <div className="mb-2">
          <p className="text-white/60 text-xs mb-1 uppercase tracking-wide">Position</p>
          <div className="flex items-center gap-3">
            <span className="text-white/40 text-xs">Bot</span>
            <div className="flex-1">
              <PositionSlider
                value={sliderValue}
                onChange={v => setSettings({ ...settings, position: (4 - v) as SubtitlePosition })}
              />
            </div>
            <span className="text-white/40 text-xs">Top</span>
          </div>
        </div>

        {/* Font size */}
        <div>
          <p className="text-white/60 text-xs mb-2 uppercase tracking-wide">Font Size</p>
          <div className="flex gap-3">
            {FONT_SIZES.map(f => (
              <button
                key={f.value}
                onClick={() => setSettings({ ...settings, fontSize: f.value })}
                className={`flex-1 h-12 rounded-lg font-semibold transition-colors ${
                  settings.fontSize === f.value
                    ? 'bg-white text-black'
                    : 'bg-white/15 text-white/70'
                }`}
                style={{ fontSize: f.fontSize }}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
