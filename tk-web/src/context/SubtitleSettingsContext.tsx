import { createContext, useContext, useState } from 'react'
import type { Dispatch, ReactNode, SetStateAction } from 'react'
import type { SubtitleSettings } from '../types'

interface SubtitleSettingsContextValue {
  settings: SubtitleSettings
  setSettings: Dispatch<SetStateAction<SubtitleSettings>>
}

export const DEFAULT_SUBTITLE_SETTINGS: SubtitleSettings = {
  position: 2,
  fontSize: 1,
  mode: 'both',
}

const SubtitleSettingsContext = createContext<SubtitleSettingsContextValue | null>(null)

interface SubtitleSettingsProviderProps {
  children: ReactNode
}

export function SubtitleSettingsProvider({ children }: SubtitleSettingsProviderProps) {
  const [settings, setSettings] = useState(DEFAULT_SUBTITLE_SETTINGS)

  return (
    <SubtitleSettingsContext.Provider value={{ settings, setSettings }}>
      {children}
    </SubtitleSettingsContext.Provider>
  )
}

export function useSubtitleSettings() {
  const context = useContext(SubtitleSettingsContext)

  if (!context) {
    throw new Error('useSubtitleSettings must be used within a SubtitleSettingsProvider')
  }

  return context
}
