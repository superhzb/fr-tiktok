# fr-tiktok

This repo is a Python application workspace with multiple sibling packages.

## Setup

Create the shared environment from the repo root:

```bash
uv sync --locked --all-packages
```

## Run Orchestrator

For real integration runs, start the orchestrator from the root workspace:

```bash
uv run --package tk-orchestrator tk-orch start
```

Developer defaults can be declared in [`tk-orchestrator/config.yaml`](/Users/brett/Documents/GitHub/fr-tiktok/tk-orchestrator/config.yaml) under `default_channels`. Prefer full TikTok URLs there. Those channels are inserted automatically on `tk-orch start` if they are not already present in the database.

## Dependency Rule

- Each package manages its own direct dependencies in its own `pyproject.toml`.
- The repo root `uv.lock` is the source of truth for exact resolved versions.
- After any dependency change in any package, run `uv lock` from the repo root and commit `uv.lock`.
