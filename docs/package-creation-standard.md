# Package Creation Standard

This document defines the default standard for creating new Python service packages in this workspace.

It is based on the patterns that worked well in this repo and the gaps that created avoidable workflow drift.

## Purpose

Every new package should be:

- easy to run
- easy to understand
- easy to validate
- easy to orchestrate

The goal is consistency, not cleverness.

## Scope

This standard applies to new Python packages added to the workspace.

It does not require existing packages to be refactored immediately, but new packages should follow it from day one.

## Required package structure

Each new package should start with this layout:

```text
tk-new-service/
  pyproject.toml
  README.md
  src/tk_new_service/__init__.py
  src/tk_new_service/cli.py
  src/tk_new_service/<core_module>.py
  tests/test_cli.py
  tests/test_logging.py
```

Rules:

- Use `src/` layout only.
- Keep import package names underscore-based, matching existing repo conventions.
- Put CLI entrypoints in `src/<package_name>/cli.py`.
- Put tests in a top-level `tests/` directory.

## Packaging and dependencies

Each package must:

- use Hatchling as the build backend
- declare direct dependencies in its own `pyproject.toml`
- avoid repo-root dependency declarations except for workspace membership and repo-wide `uv` config
- update the repo-root `uv.lock` after any dependency change

Recommended baseline:

- add a `test` dependency group with `pytest`
- add a `dev` dependency group only when truly needed

## Linting and type checking

All new Python packages must be created with linting and static type checking in mind from day one.

Rules:

- `ruff` is required
- `pyright` is required
- new package code should be typed by default
- public functions, CLI helpers, and data boundaries should have explicit type annotations

Best-practice baseline:

- the repo should provide a canonical `ruff check` command
- the repo should provide a canonical `pyright` command
- local development and CI should run the same commands

Do not treat linting and type checking as optional future cleanup for new packages.

## CLI standard

All service CLIs must use Click.

Rules:

- use `@click.command()` for single-command CLIs
- use `@click.group()` for multi-command CLIs
- always set `context_settings={"help_option_names": ["-h", "--help"]}`
- use `show_default=True` on options that have defaults

Every package should expose one obvious command through `[project.scripts]`.

The package should be runnable with one command from the workspace, for example:

```bash
uv run --package tk-new-service tk-new-service --help
```

## stdout and stderr contract

Every service package must keep machine output and logs separate.

Rules:

- `stdout` is for tool output only
- `stderr` is for logs only
- do not print progress messages or human status lines to `stdout`

Allowed `stdout` patterns:

- JSON payload
- file path
- empty output when the result is written to a file

Failure behavior:

- exit non-zero
- emit at least one `ERROR` log entry before exit

## Logging contract

Each package must implement its own small `_JSONFormatter` in `cli.py`.

Do not create a shared logging helper package for this.

Each stderr log line must be a single JSON object with:

- `time`
- `level`
- `service`
- `event`
- `message`

When present, also include:

- `job_id` from `TK_JOB_ID`
- `video_id` from `TK_VIDEO_ID`
- `pipeline_step` from `TK_PIPELINE_STEP`

Use ISO 8601 UTC timestamps.

## Testing standard

Every new package must include tests from the beginning.

Minimum required tests:

### `tests/test_logging.py`

Validate:

- stdout contains no log leakage
- stderr log lines are valid JSON
- `service` is present
- orchestrator context fields propagate when set
- failures emit at least one `ERROR` log

### `tests/test_cli.py`

Validate:

- happy-path invocation succeeds
- invalid input fails cleanly
- output shape is correct

Prefer validating the output contract over exact string snapshots.

In addition to tests, new packages are expected to pass the repo-standard lint and type-check commands.

## README standard

Each package must have a short `README.md` that answers:

- what the package does
- expected inputs
- produced outputs
- required setup, if any
- one command to run it
- one command to test it

Keep package docs operational and brief.

Repo-wide architecture and workflow belong in root docs, not package READMEs.

## Definition of done for a new package

A new package is not considered complete until all of the following are true:

- the package is added to workspace members
- `pyproject.toml` is complete
- the package uses `src/` layout
- the CLI exists and follows the Click and logging standards
- `README.md` exists
- `tests/test_logging.py` exists
- at least one happy-path CLI test exists
- the package runs via `uv run --package ...`

## Anti-patterns

Avoid these:

- printing human status messages to `stdout`
- custom CLI conventions that differ from the rest of the repo
- adding a package without tests
- adding a package without a README
- hidden setup steps not documented in the package README
- bypassing the workspace dependency workflow

## Recommended rollout for existing packages

When bringing older packages up to standard, prioritize in this order:

1. stdout/stderr contract
2. JSON logging
3. logging contract tests
4. basic CLI smoke tests
5. package README

This order improves orchestration reliability first, then legibility.
