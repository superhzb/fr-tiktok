# tk-orchestrator — Implementation Plan

## Overview

tk-orchestrator is the central coordinator for a TikTok video processing pipeline. It monitors TikTok channels for new videos, downloads them, and runs a subtitle pipeline (speech-to-text, punctuation, alignment, SRT generation, and translation). All heavy ML work is done by existing standalone CLI tools — the orchestrator's job is to call them in order, track state, and expose results via a REST API.

The entire pipeline runs **serially** — one video at a time — because the ML steps (STT, alignment, translation) are GPU-bound (Apple MLX).

---

## Tech Stack

| Tool | Purpose |
|------|---------|
| Python 3.11+ | Runtime |
| Click or Typer | CLI interface |
| asyncio + asyncio.Queue | In-process task queue (no Redis) |
| subprocess | Call existing microservice CLIs |
| SQLite + SQLAlchemy | Database |
| FastAPI | REST API (async-native) |
| APScheduler | Cron-style channel polling |
| pathlib | File/output management |

---

## Existing Microservice CLIs (reference)

These are the tools the orchestrator calls via `subprocess`. Each is a separate installed Python package. The orchestrator never imports their code — it runs them as shell commands and captures stdout/stderr.

### 1. `tk-channel-checker`

Fetches the latest video list from a TikTok channel.

```
tk-channel-checker <url> [--count N] [--debug]
```

- `url` — TikTok channel URL, e.g. `https://www.tiktok.com/@username`
- `--count` — number of videos to fetch (default: 10)
- **stdout** — JSON array of video objects. Each has: `id`, `desc`, `create_time`, `create_date`, `author`, `author_nickname`, `music_title`, `duration`, `views`, `likes`, `comments`, `shares`, `url`

### 2. `tk-comments`

Fetches top comments for a single video.

```
tk-comments <url> [--count N] [--output FILE] [--debug]
```

- `url` — TikTok video URL
- `--count` — number of comments (default: 10)
- `--output` — file path or `-` for stdout (default: `-`)
- **stdout** — JSON array of comment objects: `user`, `username`, `text`, `likes`

### 3. `tk-down`

Downloads a TikTok video file.

```
tk-down <url> [--output-dir DIR] [--debug]
```

- `url` — TikTok video URL
- `--output-dir` / `-o` — destination directory (default: `~/Public/Tiktok`)
- **stdout** — the downloaded file path
- Skips download if already saved locally

### 4. `tk-stt`

Speech-to-text using MLX Whisper. **GPU-bound.**

```
tk-stt <input_file> [--model MODEL] [--output FILE] [--debug]
```

- `input_file` — audio or video file (any ffmpeg-compatible format)
- `--model` / `-m` — MLX Whisper model (default: `mlx-community/whisper-large-v3-asr-4bit`)
- `--output` / `-o` — write to file instead of stdout
- **stdout** — JSON `{"text": "raw transcription without punctuation"}`

### 5. `tk-punctuation`

Adds punctuation to raw transcription text.

```
tk-punctuation [--input-file FILE] [--model MODEL] [--chunk-words N] [--debug]
```

- `--input-file` — JSON file with `{"text": "..."}`. Reads from **stdin** if omitted.
- `--model` — HuggingFace model (default: `kredor/punctuate-all`)
- `--chunk-words` — words per chunk (default: 180)
- **stdout** — JSON `{"text": "punctuated transcription"}`

### 6. `tk-aligner`

Forced word-level alignment using MLX. **GPU-bound.**

```
tk-aligner <audio_file> <text_file> [--model MODEL] [--output FILE] [--debug]
```

- `audio_file` — the original audio/video file
- `text_file` — JSON file with `{"text": "..."}` (the punctuated text)
- `--model` / `-m` — MLX aligner model (default: `mlx-community/Qwen3-ForcedAligner-0.6B-8bit`)
- `--output` / `-o` — write to file instead of stdout
- **stdout** — JSON array of word-level segments: `[{"start": 0.0, "end": 0.42, "text": "word"}, ...]`

### 7. `tk-srt-merger`

Merges word-level timestamps with punctuated text into subtitle file.

```
tk-srt-merger <aligned> <punctuated> [output] [--debug]
```

- `aligned` — JSON file with word-level timestamp array (from tk-aligner)
- `punctuated` — JSON file with `{"text": "..."}` (from tk-punctuation)
- `output` — destination .srt file (default: `output.srt`)
- **output** — writes an `.srt` file to disk

### 8. `tk-srt-translate`

Translates SRT subtitles into bilingual format (French to Chinese). **GPU-bound.**

```
tk-srt-translate <input> [--output FILE] [--format {srt|vtt}] [--model MODEL] [--batch-size N] [--max-tokens N] [--temperature N] [-v]
```

- `input` — input .srt file
- `--output` / `-o` — output path (default: `<input>.bilingual.<format>`)
- `--format` — `srt` or `vtt` (default: `srt`)
- `--model` / `-m` — MLX translation model (default: `mlx-community/Qwen3-4B-Instruct-2507-4bit`)
- `--batch-size` / `-b` — segments per batch (default: 10)
- `--max-tokens` — per LLM call (default: 2048)
- `--temperature` — sampling temp (default: 0.0)
- `-v` — verbosity: `-v` = INFO, `-vv` = DEBUG
- **output** — writes bilingual subtitle file to disk

---

## Pipeline Data Flow

This is the exact sequence for processing **one video**. Each step depends on the previous one. The orchestrator runs them in order, passing intermediate files between steps.

```
tk-channel-checker (channel URL)
    │
    ▼  JSON array of video metadata
    │
    ├──► tk-comments (video URL)  →  comments JSON  →  save to DB
    │
    └──► tk-down (video URL)  →  video file path
              │
              ▼
         tk-stt (video file)  →  raw_transcription.json
              │
              ▼
         tk-punctuation (raw_transcription.json)  →  punctuated.json
              │
              ▼
         tk-aligner (video file + punctuated.json)  →  aligned.json
              │
              ▼
         tk-srt-merger (aligned.json + punctuated.json)  →  subtitles.srt
              │
              ▼
         tk-srt-translate (subtitles.srt)  →  subtitles.bilingual.vtt
```

Intermediate files (`raw_transcription.json`, `punctuated.json`, `aligned.json`, `subtitles.srt`) should be kept alongside the video file for debugging.

---

## Features

### Feature 1: Database & Models

Set up SQLite database with SQLAlchemy ORM. Tables needed:

**channels**
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | auto-increment |
| username | TEXT UNIQUE | TikTok `@username` |
| url | TEXT | full channel URL |
| added_at | DATETIME | when user added the channel |
| last_checked_at | DATETIME | last time we polled this channel |
| is_active | BOOLEAN | whether polling is enabled (default: true) |

**videos**
| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | TikTok video ID (from channel-checker `id` field) |
| channel_id | INTEGER FK | references channels.id |
| description | TEXT | video description |
| url | TEXT | TikTok video URL |
| duration | INTEGER | seconds |
| views | INTEGER | |
| likes | INTEGER | |
| comments_count | INTEGER | |
| shares | INTEGER | |
| author | TEXT | |
| author_nickname | TEXT | |
| music_title | TEXT | |
| created_at | DATETIME | video's `create_date` |
| discovered_at | DATETIME | when orchestrator first saw this video |

**comments**
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | auto-increment |
| video_id | TEXT FK | references videos.id |
| user | TEXT | display name |
| username | TEXT | handle |
| text | TEXT | comment body |
| likes | INTEGER | |
| fetched_at | DATETIME | |

**jobs**
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | auto-increment |
| video_id | TEXT FK | references videos.id |
| status | TEXT | `pending`, `running`, `completed`, `failed` |
| current_step | TEXT | which pipeline step is active (e.g. `stt`, `punctuation`) |
| failed_step | TEXT | which step failed (null if none) |
| error_message | TEXT | stderr or exception message |
| video_path | TEXT | local path to downloaded video |
| srt_path | TEXT | path to generated .srt |
| vtt_path | TEXT | path to final bilingual .vtt |
| created_at | DATETIME | |
| started_at | DATETIME | |
| completed_at | DATETIME | |

### Feature 2: Configuration

Use a single `config.py` module that reads from a YAML or TOML config file with environment variable overrides.

**Configurable values:**

| Key | Default | Description |
|-----|---------|-------------|
| `poll_interval_seconds` | 60 | how often to check channels for new videos |
| `output_dir` | `~/Public/Tiktok` | base directory for downloads and generated files |
| `video_count` | 10 | videos to fetch per channel check |
| `comment_count` | 10 | comments to fetch per video |
| `stt_model` | `mlx-community/whisper-large-v3-asr-4bit` | STT model ID |
| `aligner_model` | `mlx-community/Qwen3-ForcedAligner-0.6B-8bit` | aligner model ID |
| `translate_model` | `mlx-community/Qwen3-4B-Instruct-2507-4bit` | translation model ID |
| `translate_format` | `vtt` | output subtitle format (`srt` or `vtt`) |
| `translate_batch_size` | 10 | segments per translation batch |
| `db_path` | `./tk_orchestrator.db` | SQLite database path |

### Feature 3: CLI Interface

Use Click or Typer. The CLI is the primary user-facing interface.

**Commands:**

```
tk-orch channel add <url>          # add a channel to monitor
tk-orch channel list                # list all channels and their status
tk-orch channel remove <username>   # stop monitoring a channel
tk-orch channel check <username>    # manually trigger a channel poll (skip waiting for scheduler)

tk-orch run <video_url>             # manually queue a single video for full pipeline
tk-orch run all                     # queue all unprocessed videos

tk-orch jobs                        # list recent jobs and their status
tk-orch job <job_id>                # show detailed status of a specific job

tk-orch start                       # start the scheduler + queue worker + API server
```

`tk-orch start` is the main long-running command. It starts three things concurrently:
1. The APScheduler polling loop
2. The asyncio queue worker (processes one job at a time)
3. The FastAPI server

### Feature 4: Scheduler (Channel Polling)

Uses APScheduler to run on a configurable interval (default: 60 seconds).

**What it does each tick:**
1. For each active channel in the DB, run `tk-channel-checker <url> --count <N>`
2. Parse the JSON output. For each video:
   - If the video ID already exists in the DB: update stats (views, likes, etc.) but do nothing else
   - If the video ID is **new**: insert into DB, fetch comments with `tk-comments`, and push a new job onto the queue
3. Update `last_checked_at` on the channel

**Error handling:** If `tk-channel-checker` fails (non-zero exit), log the error and skip that channel this tick. Do not crash the scheduler.

### Feature 5: Task Queue & Pipeline Runner

An asyncio queue that processes **one job at a time** (serial execution).

**Queue behavior:**
- Jobs are added to an `asyncio.Queue` when new videos are discovered or when the user runs `tk-orch run`
- A single worker coroutine pulls jobs one at a time and runs the pipeline
- Each job tracks its `current_step` in the DB so progress is visible

**Pipeline steps for a single job:**

Each step is run via `asyncio.create_subprocess_exec`. Capture both stdout and stderr. On failure (non-zero exit code), save stderr to `jobs.error_message`, set `jobs.failed_step`, set status to `failed`, and stop.

| Step | Command | Input | Output |
|------|---------|-------|--------|
| `download` | `tk-down <video_url> --output-dir <dir>` | video URL | video file path (from stdout) |
| `stt` | `tk-stt <video_file> --output <raw.json>` | video file | `raw_transcription.json` |
| `punctuation` | `tk-punctuation --input-file <raw.json>` | raw JSON | `punctuated.json` (capture stdout, write to file) |
| `alignment` | `tk-aligner <video_file> <punctuated.json> --output <aligned.json>` | video file + punctuated JSON | `aligned.json` |
| `srt_merge` | `tk-srt-merger <aligned.json> <punctuated.json> <output.srt>` | aligned + punctuated JSONs | `subtitles.srt` |
| `translation` | `tk-srt-translate <output.srt> --format vtt` | SRT file | `subtitles.bilingual.vtt` |

**File organization per video:**
```
<output_dir>/<channel_username>/<video_id>/
    video.mp4
    raw_transcription.json
    punctuated.json
    aligned.json
    subtitles.srt
    subtitles.bilingual.vtt
```

### Feature 6: Logging

Every subprocess call must capture **both stdout and stderr**. This is critical for debugging which step failed.

- Use Python's `logging` module with a consistent format: `[timestamp] [level] [module] message`
- Each subprocess stderr should be logged line-by-line at DEBUG level while running
- On subprocess failure: log the full stderr at ERROR level
- Save a combined log file per job: `<video_dir>/job.log`
- Console output should show high-level progress: which video, which step, pass/fail

### Feature 7: REST API (placeholder for v2)

FastAPI server running alongside the scheduler and queue. Serves data from the SQLite database.

**Endpoints (define routes but implement later):**

```
GET  /channels                  — list all channels
GET  /channels/:username        — single channel + its videos
GET  /videos                    — list videos (with filters: channel, status)
GET  /videos/:id                — single video + its job status + subtitles
GET  /videos/:id/comments       — comments for a video
GET  /videos/:id/subtitles      — serve the bilingual VTT/SRT file
GET  /jobs                      — list all jobs
GET  /jobs/:id                  — single job detail
```

For v1: define the route stubs that return `{"status": "not implemented"}`. Wire up the actual DB queries later.

### Feature 8: Retry Support (placeholder for v2)

For v1, failed jobs just stay in `failed` state. The user can inspect them via `tk-orch job <id>`.

Design the job table with `failed_step` so that a future retry command can resume from that step instead of restarting the whole pipeline. Do not implement the retry logic yet — just make sure the schema supports it.

---

## Project Structure

```
tk-orchestrator/
    pyproject.toml
    config.example.yaml
    tk_orchestrator/
        __init__.py
        __main__.py          # entry: `python -m tk_orchestrator`
        cli.py               # Click/Typer commands
        config.py            # load config from file + env vars
        db.py                # SQLAlchemy models + session factory
        scheduler.py         # APScheduler setup, channel polling logic
        queue.py             # asyncio queue + worker
        pipeline.py          # subprocess calls for each pipeline step
        api.py               # FastAPI app + route stubs
        logging_config.py    # logging setup
```

---

## Implementation Order

Build in this order — each step is testable on its own before moving on:

1. **config.py + db.py** — config loading and database models. Test: can create DB, insert/query rows.
2. **pipeline.py** — subprocess wrappers for each CLI tool. Test: can run each tool in isolation.
3. **cli.py** — `channel add/list/remove` commands. Test: can manage channels via CLI.
4. **queue.py** — async queue + worker that runs pipeline.py steps. Test: can process a single video end-to-end.
5. **scheduler.py** — APScheduler polling + new video detection. Test: discovers new videos and enqueues jobs.
6. **cli.py** — add `start` command that runs scheduler + queue together.
7. **logging_config.py** — structured logging + per-job log files.
8. **api.py** — FastAPI route stubs.
