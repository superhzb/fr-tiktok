# Dependency Rule

This repo is an application workspace, not a set of independently released libraries.

- Each package `pyproject.toml` declares direct dependencies and version bounds.
- A package dependency change is made in that package's own `pyproject.toml`.
- The repo root `uv.lock` is the source of truth for exact resolved versions.
- After any package dependency change, run `uv lock` from the repo root and commit the updated `uv.lock`.
- The root `pyproject.toml` changes only when workspace members or repo-wide `uv` settings change.
- Development and CI install with `uv sync --locked --all-packages`, not ad hoc `pip install`.
- Any dependency change must update both the relevant `pyproject.toml` and `uv.lock`.
