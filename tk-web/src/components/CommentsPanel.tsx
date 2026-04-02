import { useEffect, useState } from 'react'
import { fetchComments } from '../api'
import type { Comment } from '../types'

interface Props {
  videoId: string
  open: boolean
  onClose: () => void
}

type CommentLang = 'both' | 'fr'

export default function CommentsPanel({ videoId, open, onClose }: Props) {
  const [comments, setComments] = useState<Comment[]>([])
  const [lang, setLang] = useState<CommentLang>('both')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!open) return
    setLoading(true)
    fetchComments(videoId)
      .then(setComments)
      .catch(() => setComments([]))
      .finally(() => setLoading(false))
  }, [videoId, open])

  return (
    <>
      {/* Backdrop — sits above video (z-40) so clicks on upper area close the panel */}
      {open && (
        <div className="fixed inset-0 bg-black/40 z-40" onClick={onClose} />
      )}

      <div
        className={`fixed inset-x-0 bottom-0 z-50 transition-transform duration-300 ${
          open ? 'translate-y-0' : 'translate-y-full'
        }`}
        style={{ maxHeight: '70vh' }}
      >

      <div className="bg-neutral-900 rounded-t-2xl flex flex-col" style={{ maxHeight: '70vh' }}>
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
          <h2 className="text-white font-semibold text-sm">{comments.length} Comments</h2>
          <div className="flex gap-2 items-center">
            <button
              onClick={() => setLang(lang === 'both' ? 'fr' : 'both')}
              className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                lang === 'both' ? 'bg-white text-black' : 'bg-white/20 text-white'
              }`}
            >中文</button>
            <button onClick={onClose} className="text-white/60 text-xl leading-none ml-2">×</button>
          </div>
        </div>

        {/* Comment list */}
        <div className="overflow-y-auto flex-1 px-4 py-2">
          {loading && (
            <p className="text-white/50 text-sm text-center py-8">Loading...</p>
          )}
          {!loading && comments.map(c => (
            <div key={c.id} className="py-3 border-b border-white/5 last:border-0">
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <p className="text-white/60 text-xs mb-0.5">@{c.username}</p>
                  <p className="text-white text-sm leading-relaxed">{c.text}</p>
                  {lang === 'both' && c.zh && (
                    <p className="text-yellow-300 text-xs leading-relaxed mt-0.5">{c.zh}</p>
                  )}
                </div>
                <div className="flex flex-col items-center shrink-0">
                  <span className="text-white/40 text-xs">❤️</span>
                  <span className="text-white/40 text-xs">{c.likes}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
      </div>
    </>
  )
}
