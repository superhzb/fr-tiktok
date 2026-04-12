# Architecture

## Overview

tk-orchestrator is the central coordinator for a TikTok video subtitle pipeline.
It monitors channels, discovers videos, generates bilingual subtitles through a
chain of CLI tools, and serves everything via a REST API.

```
                        +-----------+
                        |  Frontend |
                        |  (tk-web) |
                        +-----+-----+
                              |  HTTP
                              v
+----------------------------------------------------------+
|                     tk-orchestrator                       |
|                                                          |
|  cli.py  (integration point — wires modules at startup)  |
|     |                                                    |
|     +-----> api/         reads DB, serves files & feed   |
|     +-----> scheduler/   polls channels, writes DB       |
|     +-----> worker/      runs pipeline, reads/writes DB  |
|     |                                                    |
|     +-----> models/      shared contract (tables,        |
|     |                    schemas, session)                |
|     +-----> config.py    YAML + env config               |
|     +-----> logging_config.py                            |
+----------------------------------------------------------+
       |           |           |
       v           v           v
   SQLite     output/     CLI tools
    (.db)    (mp4,srt,   (tk-down, tk-stt,
              vtt)        tk-aligner, ...)
```

## Module Dependency Rule

```
api/        --> models/, config
scheduler/  --> models/, config
worker/     --> models/, config, logging_config

cli.py      --> all of the above (the only integration point)
```

Modules never import each other. They communicate through the database:
- Scheduler writes `Job(status="pending")` rows.
- Worker polls for pending jobs and processes them.
- API reads whatever is in the DB.

## Data Flow

```
1. Scheduler polls TikTok channels (via tk-channel-checker CLI)
2. New videos discovered --> Video + Job(pending) rows created in DB
3. Comments fetched & translated --> Comment rows created
4. Worker picks up pending Job --> runs 6-step pipeline:

   download --> stt --> punctuation --> alignment --> srt_merge --> translation
   (tk-down)  (tk-stt) (tk-punct.)   (tk-aligner) (tk-srt-merger) (tk-batch-translate)

5. Output files written to: output/<username>/<video_id>/
6. API serves video metadata + static files to frontend
7. Frontend reports watch progress --> API stores in watch_progress table
8. GET /feed returns videos sorted by watch state (unwatched > started > completed)
```

## Database Schema

```
channels ──1:N──> videos ──1:N──> comments
                    |──1:N──> jobs
                    |──1:1──> watch_progress
```

| Table | Purpose |
|-------|---------|
| channels | Monitored TikTok accounts |
| videos | Discovered video metadata |
| comments | Translated comments per video |
| jobs | Pipeline execution state (pending/running/completed/failed/interrupted) |
| watch_progress | Per-video play percentage, loop count, saved position |

Deleting a video cascades to comments, jobs, and watch_progress.

## Key Design Decisions

- **SQLite** — single-file DB, no external services needed. Foreign keys
  enforced via `PRAGMA foreign_keys=ON`.
- **DB as message bus** — scheduler and worker communicate through job rows,
  not in-process queues. This makes the system restartable and debuggable.
- **CLI tool chain** — each pipeline step is a standalone CLI tool. The
  orchestrator shells out to them. Tools can be developed, tested, and
  versioned independently.
- **Single-user** — watch_progress has `video_id` as PK (no user column).
  Multi-user would add a composite PK.
