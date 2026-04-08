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
- For all new packages, follow the full package standard in [`docs/package-creation-standard.md`](/Users/brett/Documents/GitHub/fr-tiktok/docs/package-creation-standard.md).

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

All service CLIs must follow this contract:

- `stdout` is tool output only: JSON, file path, or empty when writing to a file.
- `stderr` is logs only: one JSON object per line.
- Every log entry must include `time`, `level`, `service`, `event`, and `message`.
- When present, propagate `TK_JOB_ID`, `TK_VIDEO_ID`, and `TK_PIPELINE_STEP` as `job_id`, `video_id`, and `pipeline_step`.
- Each package owns its own `_JSONFormatter` in `cli.py`; do not create a shared repo-level logging package.
- Before exiting non-zero, log at least one `ERROR` entry that makes the failure obvious.
