# Testing

## Setup

```bash
cd tk-orchestrator
uv sync --group dev
```

## Run a stage test (fast, uses fixtures)

```bash
uv run pytest tests/test_pipeline.py --from-step translation -v
uv run pytest tests/test_pipeline.py --from-step srt_merge -v
uv run pytest tests/test_pipeline.py --from-step alignment -v
uv run pytest tests/test_pipeline.py --from-step punctuation -v
uv run pytest tests/test_pipeline.py --from-step stt -v
```

Pass the step you changed — it loads saved fixtures and runs everything from that point forward.

## Run the full E2E test (slow, ~2 min)

```bash
rm -rf tests/output/
uv run pytest tests/test_pipeline_e2e.py -v -s
```

This downloads and processes the real video, then saves new fixtures to `tests/fixtures/`.
