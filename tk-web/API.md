# tk-orchestrator Backend API

## Overview

This backend serves a French TikTok video processing pipeline. It downloads TikTok videos from monitored channels, generates bilingual (French + Chinese) subtitles via speech-to-text and translation, and collects/translates top comments.

The frontend should present these videos in a TikTok-like vertical feed with bilingual subtitle display and translated comments.

**Base URL:** `http://localhost:8000`

---

## Data Model

### Channel

A monitored TikTok creator account.

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Primary key |
| `username` | string | TikTok handle (e.g. `paulmirabel_`) |
| `url` | string | Full TikTok profile URL |
| `added_at` | ISO 8601 | When the channel was added |
| `last_checked_at` | ISO 8601 \| null | Last poll time |
| `is_active` | boolean | Whether polling is enabled |

### Video

A TikTok video from a monitored channel.

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | TikTok video ID (e.g. `7623453386213543190`) |
| `channel_id` | int | FK to channel |
| `channel_username` | string | Channel handle (included in list/detail responses) |
| `description` | string | Original TikTok caption |
| `url` | string | TikTok video page URL |
| `duration` | int | Duration in seconds |
| `views` | int | View count |
| `likes` | int | Like count |
| `comments_count` | int | Comment count (on TikTok) |
| `shares` | int | Share count |
| `author` | string | Author username |
| `author_nickname` | string | Author display name (e.g. `Paul Mirabel`) |
| `music_title` | string | Background music title |
| `created_at` | ISO 8601 | When the video was posted on TikTok |
| `discovered_at` | ISO 8601 | When our system first saw it |
| `files` | object | See [Video Files](#video-files) below |

### Video Files

Included in video responses as the `files` object. All values are URL paths relative to the base URL, or `null` if the file doesn't exist yet.

| Field | Type | Description |
|-------|------|-------------|
| `video_url` | string \| null | Path to MP4 file (e.g. `/output/paulmirabel_/7623453386213543190/ssstik.io_@paulmirabel__1775141585333.mp4`) |
| `vtt_url` | string \| null | Path to bilingual VTT subtitle file |
| `srt_url` | string \| null | Path to French-only SRT subtitle file |

Usage in HTML:
```html
<video src="http://localhost:8000/output/paulmirabel_/...mp4">
  <track kind="subtitles" src="http://localhost:8000/output/paulmirabel_/.../subtitles.vtt" default>
</video>
```

### Comment

A top comment on a video, with Chinese translation.

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Primary key |
| `video_id` | string | FK to video |
| `user` | string | Commenter display name |
| `username` | string | Commenter handle |
| `text` | string | Original comment (French) |
| `zh` | string \| null | Chinese translation (may be empty or null) |
| `likes` | int | Like count on the comment |

### Job

Processing status for a video. Each video has one job.

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Primary key |
| `video_id` | string | FK to video |
| `status` | string | `pending` \| `running` \| `completed` \| `failed` |
| `current_step` | string \| null | Active pipeline step (when `running`) |
| `failed_step` | string \| null | Which step failed (when `failed`) |
| `error_message` | string \| null | Error details (when `failed`) |
| `created_at` | ISO 8601 | Job creation time |
| `started_at` | ISO 8601 \| null | Processing start time |
| `completed_at` | ISO 8601 \| null | Processing completion time |

Pipeline steps (in order): `download` > `stt` > `punctuation` > `alignment` > `srt_merge` > `translation`

---

## Endpoints

### Channels

#### `GET /channels`

List all monitored channels.

**Response:** `Channel[]`

```json
[
  {
    "id": 1,
    "username": "paulmirabel_",
    "url": "https://www.tiktok.com/@paulmirabel_",
    "added_at": "2026-04-02T14:51:33.019000",
    "last_checked_at": "2026-04-02T15:05:56.000000",
    "is_active": true
  }
]
```

#### `GET /channels/{username}`

Get a single channel by username.

**Response:** `Channel`
**Errors:** `404` if not found

---

### Videos

#### `GET /videos`

List all videos, newest first.

**Query params:**
| Param | Type | Description |
|-------|------|-------------|
| `channel` | string (optional) | Filter by channel username |
| `status` | string (optional) | Filter by job status (`completed`, `pending`, `running`, `failed`) |

**Response:** `Video[]` (each includes `files` and `channel_username`)

```json
[
  {
    "id": "7623453386213543190",
    "channel_id": 1,
    "channel_username": "paulmirabel_",
    "description": "Les ami(e)s, mon spectacle \u00ab Par Amour \u00bb sera diffus\u00e9...",
    "url": "https://www.tiktok.com/@paulmirabel_/video/7623453386213543190",
    "duration": 63,
    "views": 44500,
    "likes": 4714,
    "comments_count": 37,
    "shares": 142,
    "author": "paulmirabel_",
    "author_nickname": "Paul Mirabel",
    "music_title": null,
    "created_at": "2026-03-31T16:12:46",
    "discovered_at": "2026-04-02T14:52:33.645407",
    "files": {
      "video_url": "/output/paulmirabel_/7623453386213543190/ssstik.io_@paulmirabel__1775141585333.mp4",
      "vtt_url": "/output/paulmirabel_/7623453386213543190/subtitles.vtt",
      "srt_url": "/output/paulmirabel_/7623453386213543190/subtitles.srt"
    }
  }
]
```

#### `GET /videos/{video_id}`

Get a single video by ID.

**Response:** `Video` (includes `files` and `channel_username`)
**Errors:** `404` if not found

---

### Comments

#### `GET /videos/{video_id}/comments`

Get comments for a video, sorted by likes (descending).

**Response:** `Comment[]`

```json
[
  {
    "id": 1,
    "video_id": "7623453386213543190",
    "user": "\u00c9mile \ud83e\udd37\ud83c\udffb\u200d\u2642\ufe0f\ud83d\udca4",
    "username": "emile_blv",
    "text": "L'un des meilleurs humoriste Fran\u00e7ais, 0 d\u00e9bats.",
    "zh": null,
    "likes": 116
  },
  {
    "id": 2,
    "video_id": "7623453386213543190",
    "user": "\u2720 \ud835\udd08\ud835\udd29\ud835\udd26\ud835\udd30\ud835\udd22 \ud83e\ude78",
    "username": "elise_010228",
    "text": "Le spectacle \u00e9tait juste incroyable\ud83d\ude0d Encore bravo Paul!",
    "zh": null,
    "likes": 7
  }
]
```

**Note:** The `zh` field may be `null` or empty string if comment translation hasn't run or the comment was empty. The frontend should handle both cases gracefully (show only French text when `zh` is absent).

---

### Subtitles

#### `GET /videos/{video_id}/subtitles`

Get subtitle file URLs for a video.

**Response:**
```json
{
  "video_url": "/output/paulmirabel_/7623453386213543190/ssstik.io_@paulmirabel__1775141585333.mp4",
  "vtt_url": "/output/paulmirabel_/7623453386213543190/subtitles.vtt",
  "srt_url": "/output/paulmirabel_/7623453386213543190/subtitles.srt"
}
```

---

### Jobs

#### `GET /jobs`

List the 50 most recent jobs, newest first.

**Response:** `Job[]`

#### `GET /jobs/{job_id}`

Get a single job by ID.

**Response:** `Job`
**Errors:** `404` if not found

---

## Static Files

The backend serves the `output/` directory at `/output/`. Video and subtitle files are accessed directly via the paths returned in `files` objects.

**Directory structure:**
```
/output/{channel_username}/{video_id}/
  ├── *.mp4              (video file)
  ├── subtitles.vtt      (bilingual subtitles - French + Chinese)
  └── subtitles.srt      (French-only subtitles)
```

---

## VTT Subtitle Format

The VTT files contain bilingual subtitles. Each cue has two lines: French (original) on top, Chinese (translation) below.

```
WEBVTT

00:00:00.400 --> 00:00:04.160
En 2023, Paul a pris le stage.
2023年，保罗开始实习。

00:00:04.960 --> 00:00:09.680
Bonsoir En 2026, avec son nouveau show.
晚上2026年，有了他的新节目。
```

The native `<track>` element will render both lines together. If the frontend needs to show/hide languages independently, it must parse the VTT and split odd/even lines per cue.

---

## Current Data

| Entity | Count |
|--------|-------|
| Channels | 1 (`paulmirabel_` - French comedian) |
| Videos | 7 |
| Comments | 70 (10 per video) |
| Completed jobs | 6 |
| Running/stuck jobs | 1 |

Video durations range from 14s to 63s. Videos are sorted newest-first by default.

---

## CORS

All origins are allowed (`*`). No authentication is required.

---

## Running the Backend

```bash
cd tk-orchestrator
tk-orch start --host 0.0.0.0 --port 8000
```

This starts the API server, the channel polling scheduler, and the job processing queue worker together.
