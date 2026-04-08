# tk-web iOS App Plan

## Direction

`tk-web` is no longer being treated as a PWA target. The app should become an iOS app using Capacitor, with React continuing to provide the UI layer.

The main architectural change is that video storage should be app-managed, not browser-managed. Downloaded videos should live in the app filesystem, with explicit metadata and delete behavior.

On iOS, video files should be stored in Capacitor Filesystem. Per-video metadata should be stored in Capacitor Preferences using one key per video, for example `video::{videoId}` mapping to a serialized `VideoStorageRecord`.

## Goals

- Wrap the existing React app with Capacitor for iOS.
- Use local filesystem storage for downloaded videos.
- Prefer local files for playback, with network fallback when needed.
- Track download state explicitly per video.
- Support deleting downloaded videos cleanly.
- Keep the current watch-progress and feed-ordering logic.

## Implementation Plan

1. Add Capacitor to `tk-web` and create the iOS project.
2. Remove PWA-specific offline behavior and stop relying on service workers.
3. Introduce a `VideoStorage` interface for resolving playable URLs and managing downloads.
4. Add a simple web implementation that returns backend URLs directly for browser development.
5. Add a Capacitor implementation that downloads videos into app storage and returns local file paths.
6. Add metadata storage for `videoId`, remote URL, local path, status, size, and timestamps using Capacitor Preferences with one key per video.
7. Update playback to prefer local files and fall back to remote URLs when a file is not downloaded or the local file is missing.
8. Add download and delete actions in the UI.
9. Test on iPhone for playback, persistence across restarts, storage cleanup, and failure handling.

## Suggested Interface

```ts
export interface PlayableResult {
  url: string
  isLocal: boolean
}

export interface VideoStorageRecord {
  videoId: string
  remoteUrl: string
  localPath: string | null
  status: 'idle' | 'downloading' | 'ready' | 'failed'
  sizeBytes: number | null
  updatedAt: string
}

export interface VideoStorage {
  getPlayableUrl(videoId: string, remoteUrl: string): Promise<PlayableResult>
  getRecord(videoId: string): Promise<VideoStorageRecord | null>
  ensureDownloaded(videoId: string, remoteUrl: string): Promise<VideoStorageRecord>
  cancelDownload(videoId: string): Promise<void>
  deleteDownloaded(videoId: string): Promise<void>
}
```

## Notes

- The current watch stats in IndexedDB are a deliberate choice for now. They can continue to live there in Capacitor's WKWebView unless a later native integration requirement justifies moving them.
- The browser should be treated as a secondary dev environment, not the primary offline target. The web implementation should return remote URLs directly and should not download or persist video files locally.
- Remove service worker registration, cache-first strategies, and offline-oriented PWA manifest behavior. The web build remains for development, but not as an offline-capable target.
- Prefetching should come after manual download and delete flows work reliably on iOS.
- `getPlayableUrl()` should verify that a recorded local file still exists before returning it. If the file is missing or unreadable, it should reset the record to `idle`, fall back to the remote URL, and allow a later re-download.
- If the app is killed during a download, any `downloading` record should be reset to `idle` on next launch.
- `ensureDownloaded()` should return the existing in-flight promise for duplicate requests instead of starting a second download.
- Calling `ensureDownloaded()` on a `failed` record should retry the download.
- If `remoteUrl` changes for an existing record, `ensureDownloaded()` should re-download and replace the local file.
- `deleteDownloaded()` should reject when the record is `downloading`. The caller must cancel first.
- Deleting during playback is allowed. The player should handle the missing file gracefully by stopping or switching to the remote URL.

## Test Cases

- Cold launch with previously downloaded videos should play from local files.
- Cold launch after app kill mid-download should reset the record to `idle` and fall back to the remote URL.
- Deleting a video should remove the file, reset the record, and allow re-download.
- A manually missing file should fall back to the remote URL and update the record.
- Low-storage conditions should mark the record as `failed` and surface an error in the UI.
- An expired or changed remote URL should trigger re-download when `ensureDownloaded()` is called.
