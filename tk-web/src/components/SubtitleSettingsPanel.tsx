import type { SubtitleSettings, SubtitlePosition, SubtitleFontSize, SubtitleMode } from '../types'

interface Props {
  open: boolean
  settings: SubtitleSettings
  onChange: (s: SubtitleSettings) => void
  onClose: () => void
}

const POSITIONS: { label: string; value: SubtitlePosition }[] = [
  { label: '1', value: 0 },
  { label: '2', value: 1 },
  { label: '3', value: 2 },
  { label: '4', value: 3 },
  { label: '5', value: 4 },
]

const FONT_SIZES: { label: string; value: SubtitleFontSize }[] = [
  { label: 'A', value: 0 },
  { label: 'A', value: 1 },
  { label: 'A', value: 2 },
]

const MODES: { label: string; value: SubtitleMode }[] = [
  { label: 'FR', value: 'fr' },
  { label: 'FR + 中', value: 'both' },
  { label: '中文', value: 'zh' },
]

export default function SubtitleSettingsPanel({ open, settings, onChange, onClose }: Props) {
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
          <div className="flex gap-2">
            {MODES.map(m => (
              <button
                key={m.value}
                onClick={() => onChange({ ...settings, mode: m.value })}
                className={`flex-1 h-9 rounded-lg text-xs font-semibold transition-colors ${
                  settings.mode === m.value
                    ? 'bg-white text-black'
                    : 'bg-white/15 text-white/70'
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>
        </div>

        {/* Position */}
        <div className="mb-4">
          <p className="text-white/60 text-xs mb-2 uppercase tracking-wide">Position</p>
          <div className="flex items-center gap-1">
            <span className="text-white/40 text-xs mr-1">Top</span>
            <div className="flex flex-1 gap-2">
              {POSITIONS.map(p => (
                <button
                  key={p.value}
                  onClick={() => onChange({ ...settings, position: p.value })}
                  className={`flex-1 h-8 rounded-lg text-xs font-semibold transition-colors ${
                    settings.position === p.value
                      ? 'bg-white text-black'
                      : 'bg-white/15 text-white/70'
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>
            <span className="text-white/40 text-xs ml-1">Bot</span>
          </div>
        </div>

        {/* Font size */}
        <div>
          <p className="text-white/60 text-xs mb-2 uppercase tracking-wide">Font Size</p>
          <div className="flex gap-3">
            {FONT_SIZES.map((f, i) => (
              <button
                key={f.value}
                onClick={() => onChange({ ...settings, fontSize: f.value })}
                className={`flex-1 h-10 rounded-lg font-semibold transition-colors ${
                  settings.fontSize === f.value
                    ? 'bg-white text-black'
                    : 'bg-white/15 text-white/70'
                }`}
                style={{ fontSize: 12 + i * 4 }}
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
