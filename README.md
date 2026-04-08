# fr-tiktok

This repo is a Python application workspace with multiple sibling packages.

## Setup

Create the shared environment from the repo root:

```bash
uv sync --locked --all-packages
cd tk-web && npm install && cd ..
uv run --package tk-channel-checker playwright install chromium
```

## Run Orchestrator

For real integration runs, start the orchestrator from the root workspace:

```bash
uv run --package tk-orchestrator tk-orch start
```

Developer defaults can be declared in [`tk-orchestrator/config.yaml`](/Users/brett/Documents/GitHub/fr-tiktok/tk-orchestrator/config.yaml) under `default_channels`. Prefer full TikTok URLs there. Those channels are inserted automatically on `tk-orch start` if they are not already present in the database.

## Full Dev Stack

To run backend and frontend together from the repo root:

```bash
./scripts/dev.sh
```

This binds the API to `0.0.0.0:8000` and the Vite frontend to `0.0.0.0:5173`, so you can open the app from:

- this machine: `http://127.0.0.1:5173`
- your LAN: `http://<your-lan-ip>:5173`
- Tailscale by IP: `http://<your-tailscale-ip>:5173`

If you want to use a Tailscale MagicDNS hostname instead of the Tailscale IP, allow it explicitly before starting:

```bash
VITE_ALLOWED_HOSTS=your-machine.your-tailnet.ts.net ./scripts/dev.sh
```

## Dependency Rule

- Each package manages its own direct dependencies in its own `pyproject.toml`.
- The repo root `uv.lock` is the source of truth for exact resolved versions.
- After any dependency change in any package, run `uv lock` from the repo root and commit `uv.lock`.
