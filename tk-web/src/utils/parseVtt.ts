import type { SubtitleCue } from '../types'

function timeToSeconds(t: string): number {
  const parts = t.split(':').map(Number)
  if (parts.length === 3) {
    return parts[0] * 3600 + parts[1] * 60 + parts[2]
  }
  return parts[0] * 60 + parts[1]
}

export function parseVtt(text: string): SubtitleCue[] {
  const cues: SubtitleCue[] = []
  const blocks = text.split(/\n\n+/)
  for (const block of blocks) {
    const lines = block.trim().split('\n')
    const timingIdx = lines.findIndex(l => l.includes('-->'))
    if (timingIdx === -1) continue
    const [startStr, endStr] = lines[timingIdx].split('-->').map(s => s.trim())
    const textLines = lines.slice(timingIdx + 1).filter(Boolean)
    if (textLines.length === 0) continue
    const fr = textLines[0] ?? ''
    const zh = textLines[1] ?? ''
    cues.push({
      startTime: timeToSeconds(startStr),
      endTime: timeToSeconds(endStr),
      fr,
      zh,
    })
  }
  return cues
}
