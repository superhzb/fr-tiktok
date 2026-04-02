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

export interface SubtitleCue {
  startTime: number
  endTime: number
  fr: string
  zh: string
}
