export interface VideoFiles {
  video_url: string | null
  vtt_url: string | null
  srt_url: string | null
}

export interface Video {
  id: string
  channel_username: string
  description: string
  url: string
  duration: number
  views: number
  likes: number
  comments_count: number
  shares: number
  author: string
  author_nickname: string
  music_title: string | null
  created_at: string
  files: VideoFiles
}

export interface Comment {
  id: number
  video_id: string
  user: string
  username: string
  text: string
  zh: string | null
  likes: number
}

export type SubtitleMode = 'fr' | 'zh' | 'both'

/** 0 = top, 4 = bottom (above description bar) */
export type SubtitlePosition = 0 | 1 | 2 | 3 | 4

/** 0 = small (16px), 1 = medium (20px), 2 = large (26px) */
export type SubtitleFontSize = 0 | 1 | 2

export interface SubtitleSettings {
  position: SubtitlePosition
  fontSize: SubtitleFontSize
  mode: SubtitleMode
}

export interface SubtitleCue {
  startTime: number
  endTime: number
  fr: string
  zh: string
}

/** Saved to IndexedDB — survives app restarts */
export interface VideoPlayStats {
  videoId: string
  playPercentage: number   // 0 to 100, the furthest point the user reached
  loopCount: number        // how many times the video was watched to >=95%
  seen: boolean            // true once the video has been watched to >=95%
}

/** Only lives in memory — lost when app closes */
export interface VideoSessionState {
  savedPosition: number    // the timestamp (in seconds) where user left off
  direction: 'forward' | 'back' | null  // how the user scrolled to this video
}
