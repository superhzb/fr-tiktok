import { describe, it, expect, beforeEach } from 'vitest'
import 'fake-indexeddb/auto'
import { IDBFactory } from 'fake-indexeddb'
import { getAllStats, putStat, putManyStats } from '../../src/lib/playStatsDb'
import { sortFeed } from '../../src/lib/feedSort'
import type { Video, VideoPlayStats } from '../../src/types'

function makeVideo(id: string): Video {
  return {
    id,
    channel_username: 'chan',
    description: `video ${id}`,
    url: `http://example.com/${id}`,
    duration: 60,
    views: 0,
    likes: 0,
    comments_count: 0,
    shares: 0,
    author: 'author',
    author_nickname: 'Author',
    music_title: null,
    created_at: '2025-01-01T00:00:00Z',
    files: { video_url: `/output/${id}.mp4`, vtt_url: null, srt_url: null },
  }
}

describe('watch-progress persistence across cold relaunch', () => {
  beforeEach(() => {
    indexedDB = new IDBFactory()
  })

  it('persists play stats to IndexedDB and reloads them', async () => {
    const stats: VideoPlayStats = {
      videoId: 'v1',
      playPercentage: 45,
      loopCount: 0,
      seen: false,
    }

    await putStat(stats)

    const loaded = await getAllStats()
    expect(loaded).toHaveLength(1)
    expect(loaded[0]).toEqual(stats)
  })

  it('preserves feed ordering based on persisted stats after simulating app relaunch', async () => {
    const videos = [makeVideo('unwatched'), makeVideo('started'), makeVideo('completed')]

    await putManyStats([
      { videoId: 'started', playPercentage: 30, loopCount: 0, seen: false },
      { videoId: 'completed', playPercentage: 100, loopCount: 3, seen: true },
    ])

    const stats = await getAllStats()
    const statsMap = new Map(stats.map(s => [s.videoId, s]))
    const sorted = sortFeed(videos, statsMap)

    expect(sorted.map(v => v.id)).toEqual(['unwatched', 'started', 'completed'])
  })

  it('sorts partially-watched videos by ascending playPercentage', async () => {
    const videos = [makeVideo('v80'), makeVideo('v10'), makeVideo('v50')]

    await putManyStats([
      { videoId: 'v80', playPercentage: 80, loopCount: 0, seen: false },
      { videoId: 'v10', playPercentage: 10, loopCount: 0, seen: false },
      { videoId: 'v50', playPercentage: 50, loopCount: 0, seen: false },
    ])

    const stats = await getAllStats()
    const statsMap = new Map(stats.map(s => [s.videoId, s]))
    const sorted = sortFeed(videos, statsMap)

    expect(sorted.map(v => v.id)).toEqual(['v10', 'v50', 'v80'])
  })

  it('sorts completed videos by ascending loopCount', async () => {
    const videos = [makeVideo('v5'), makeVideo('v1'), makeVideo('v3')]

    await putManyStats([
      { videoId: 'v5', playPercentage: 100, loopCount: 5, seen: true },
      { videoId: 'v1', playPercentage: 100, loopCount: 1, seen: true },
      { videoId: 'v3', playPercentage: 100, loopCount: 3, seen: true },
    ])

    const stats = await getAllStats()
    const statsMap = new Map(stats.map(s => [s.videoId, s]))
    const sorted = sortFeed(videos, statsMap)

    expect(sorted.map(v => v.id)).toEqual(['v1', 'v3', 'v5'])
  })

  it('orders: unwatched first, then started (ascending %), then completed (ascending loops)', async () => {
    const videos = [
      makeVideo('comp2'),
      makeVideo('fresh'),
      makeVideo('start30'),
      makeVideo('start10'),
      makeVideo('comp1'),
    ]

    await putManyStats([
      { videoId: 'comp2', playPercentage: 100, loopCount: 2, seen: true },
      { videoId: 'start30', playPercentage: 30, loopCount: 0, seen: false },
      { videoId: 'start10', playPercentage: 10, loopCount: 0, seen: false },
      { videoId: 'comp1', playPercentage: 100, loopCount: 1, seen: true },
    ])

    const stats = await getAllStats()
    const statsMap = new Map(stats.map(s => [s.videoId, s]))
    const sorted = sortFeed(videos, statsMap)

    expect(sorted.map(v => v.id)).toEqual([
      'fresh',
      'start10',
      'start30',
      'comp1',
      'comp2',
    ])
  })

  it('survives a simulated cold relaunch: write -> read -> update -> read', async () => {
    await putManyStats([
      { videoId: 'a', playPercentage: 55, loopCount: 0, seen: false },
      { videoId: 'b', playPercentage: 100, loopCount: 2, seen: true },
    ])

    const firstRead = await getAllStats()
    expect(firstRead).toHaveLength(2)

    await putStat({ videoId: 'a', playPercentage: 95, loopCount: 0, seen: false })

    const secondRead = await getAllStats()
    const aStat = secondRead.find(s => s.videoId === 'a')!
    expect(aStat.playPercentage).toBe(95)
  })

  it('batch putManyStats persists all records', async () => {
    const stats: VideoPlayStats[] = Array.from({ length: 20 }, (_, i) => ({
      videoId: `v${i}`,
      playPercentage: i * 5,
      loopCount: 0,
      seen: false,
    }))

    await putManyStats(stats)

    const loaded = await getAllStats()
    expect(loaded).toHaveLength(20)

    const loadedMap = new Map(loaded.map(s => [s.videoId, s]))
    for (const s of stats) {
      expect(loadedMap.get(s.videoId)?.playPercentage).toBe(s.playPercentage)
    }
  })
})
