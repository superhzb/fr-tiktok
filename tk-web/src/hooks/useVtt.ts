import { useState, useEffect } from 'react'
import { parseVtt } from '../utils/parseVtt'
import type { SubtitleCue } from '../types'

export function useVtt(vttUrl: string | null) {
  const [cues, setCues] = useState<SubtitleCue[]>([])

  useEffect(() => {
    if (!vttUrl) { setCues([]); return }
    fetch(vttUrl)
      .then(r => r.text())
      .then(text => setCues(parseVtt(text)))
      .catch(() => setCues([]))
  }, [vttUrl])

  return cues
}
