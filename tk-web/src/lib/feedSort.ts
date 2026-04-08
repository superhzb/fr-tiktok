import type { Video, VideoPlayStats } from '../types'

export function sortFeed(
  videos: Video[],
  statsMap: Map<string, VideoPlayStats>
): Video[] {
  const unwatched: Video[] = []
  const started: Video[] = []
  const completed: Video[] = []

  for (const video of videos) {
    const stats = statsMap.get(video.id)

    if (!stats || stats.playPercentage === 0) {
      unwatched.push(video)
    } else if (stats.loopCount === 0) {
      started.push(video)
    } else {
      completed.push(video)
    }
  }

  started.sort((a, b) => {
    const aStats = statsMap.get(a.id)!
    const bStats = statsMap.get(b.id)!
    return aStats.playPercentage - bStats.playPercentage
  })

  completed.sort((a, b) => {
    const aStats = statsMap.get(a.id)!
    const bStats = statsMap.get(b.id)!
    return aStats.loopCount - bStats.loopCount
  })

  return [...unwatched, ...started, ...completed]
}
