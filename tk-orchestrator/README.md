# tk-orchestrator

CLI orchestrator for the TikTok video subtitle pipeline. Monitors channels,
downloads videos, generates bilingual subtitles, and serves them via REST API.

## Quick Start

```bash
# Install (with sibling packages available)
uv pip install -e .

# Copy and edit config
cp config.example.yaml config.yaml

# Start everything (API + scheduler + worker)
tk-orch start --refresh

# Start in frozen library mode (API only; no polling/deletes/downloads)
tk-orch start --no-refresh
# API at http://localhost:19099
```

## CLI Commands

```bash
tk-orch start --refresh             # start API server + scheduler + worker
tk-orch start --no-refresh          # start API only, keep current library fixed
tk-orch channel add <url>           # monitor a TikTok channel
tk-orch channel list                # list monitored channels
tk-orch channel remove <username>   # stop monitoring
tk-orch channel check <username>    # manually poll + process a channel
tk-orch run <video_url>             # process a single video
tk-orch run all                     # process all pending jobs
tk-orch jobs                        # list recent jobs
tk-orch job <id>                    # show job details
tk-orch reset                       # delete DB and output (destructive)
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/feed` | Videos in smart-feed order (with watch progress) |
| GET | `/channels` | List channels |
| GET | `/videos` | List videos (filterable by channel, status) |
| GET | `/videos/{id}` | Video details |
| GET | `/videos/{id}/comments` | Video comments |
| PUT | `/videos/{id}/progress` | Update watch progress |
| DELETE | `/videos/{id}` | Delete video + all related data |
| GET | `/progress` | All watch progress records |
| GET | `/jobs` | Recent jobs |

## Pipeline Steps

```
download -> stt -> punctuation -> alignment -> srt_merge -> translation
```

Each step calls an external CLI tool (`tk-down`, `tk-stt`, `tk-punctuation`,
`tk-aligner`, `tk-srt-merger`, `tk-batch-translate`). Jobs are resumable —
if interrupted, the worker resumes from the last completed step.

## Configuration

See [`config.example.yaml`](config.example.yaml). All fields can be overridden
with environment variables (`TK_POLL_INTERVAL_SECONDS`, `TK_OUTPUT_DIR`, etc.).

`refresh_enabled` controls whether automatic channel polling, retention
deletes, and background pipeline processing are enabled by default. You can
override it at startup with `tk-orch start --refresh` or `tk-orch start
--no-refresh`.

## Project Structure

```
src/tk_orchestrator/
├── cli.py              # CLI entry point (wires modules together)
├── config.py           # YAML + env config loading
├── logging_config.py   # logging setup
├── models/             # DB tables, Pydantic schemas, session management
├── api/                # FastAPI HTTP server
├── scheduler/          # Channel polling + comment fetching
└── worker/             # Pipeline execution + job queue
```

See [docs/architecture.md](docs/architecture.md) for details.

## Development

```bash
uv run --package tk-orchestrator pytest
```
