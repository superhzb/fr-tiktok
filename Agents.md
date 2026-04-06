# Dependency Rule

This repo is an application workspace, not a set of independently released libraries.

- Each package `pyproject.toml` declares direct dependencies and version bounds.
- A package dependency change is made in that package's own `pyproject.toml`.
- The repo root `uv.lock` is the source of truth for exact resolved versions.
- After any package dependency change, run `uv lock` from the repo root and commit the updated `uv.lock`.
- The root `pyproject.toml` changes only when workspace members or repo-wide `uv` settings change.
- Development and CI install with `uv sync --locked --all-packages`, not ad hoc `pip install`.
- Any dependency change must update both the relevant `pyproject.toml` and `uv.lock`.

# Package Layout Rule

- All Python packages must use `src/` layout: source code lives under `src/<package_name>/`, not at the project root.

# Build System Rule

- All packages must use **Hatchling** as the build backend.
- Use `requires = ["hatchling"]` and `build-backend = "hatchling.build"` in `[build-system]`.
- Declare the package under `[tool.hatch.build.targets.wheel]` with `packages = ["src/<package_name>"]`.
- Do not use setuptools. Hatchling includes all files within the package directory (including non-Python data files) automatically.

# CLI Framework Rule

- All service CLIs must use **Click** (not argparse).
- Use `@click.command()` for single-command CLIs, `@click.group()` for subcommands.
- Always set `context_settings={"help_option_names": ["-h", "--help"]}`.
- Use `show_default=True` on options with defaults.

# CLI Logging Contract

All service CLIs must follow this contract so the orchestrator can attribute failures to the right package, job, and pipeline step.

**stdout** — tool result only (JSON or file path). No log lines, status messages, or progress output.

**stderr** — logs only, one JSON object per line. Each log entry must include:

```json
{"time": "...", "level": "INFO", "service": "tk-stt", "event": "tk_stt.cli", "message": "..."}
```

Required fields: `time` (ISO 8601 UTC), `level`, `service` (the package name, e.g. `"tk-stt"`), `event` (the Python logger name), `message`.

**Orchestrator context** — when the env vars below are present, include them in every log entry:

| Env var | Log field | Set by |
|---|---|---|
| `TK_JOB_ID` | `job_id` | tk-orchestrator |
| `TK_VIDEO_ID` | `video_id` | tk-orchestrator |
| `TK_PIPELINE_STEP` | `pipeline_step` | tk-orchestrator |

**Implementation** — each package owns its own small `_JSONFormatter` class in `cli.py`. Do not create a shared repo-level logging package. Duplication is intentional so packages stay independent.

**Failure logs** — before exiting with a non-zero code, log at least one `ERROR` entry that makes it obvious which service failed and why.
