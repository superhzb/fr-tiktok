# Architecture Review: fr-tiktok

**Date:** 2026-04-03  
**Scope:** Full repository structure, all 10 Python microservices + React frontend

---

## Project Summary

A TikTok video processing pipeline: 10 Python microservices + 1 React/TypeScript frontend. Downloads TikTok videos, transcribes (Whisper/MLX), adds bilingual subtitles (FR→ZH), fetches/translates comments, and serves everything via a web UI. Designed for Apple Silicon with MLX.

### Data Flow

```
TikTok Channel URL
    → tk-channel-checker  → video metadata (JSON)
    → tk-comment-checker  → comments (JSON)
    → tk-comment-translator → translated comments (JSON)
    → tk-down             → video file (MP4)
    → tk-stt              → raw transcription (JSON)
    → tk-punctuation      → punctuated text (JSON)
    → tk-aligner          → word-level timestamps (JSON)
    → tk-srt-merger       → subtitle file (SRT)
    → tk-srt-translate    → bilingual subtitles (VTT)
```

---

## What's Already Well-Designed

1. **Clean pipeline decomposition.** Each service does one thing (download, transcribe, punctuate, align, merge, translate). Textbook Unix philosophy — small, composable tools communicating via stdin/stdout/files.

2. **Subprocess-based service communication.** Using CLI tools invoked via `asyncio.create_subprocess_exec` is a smart choice for this scale. Each service can be developed, tested, and debugged independently.

3. **Orchestrator config pattern.** The `Config` dataclass with YAML + env-var override + legacy key migration (`config.py`) is well-engineered. Layered config with sensible defaults.

4. **Database session management.** The `get_session()` context manager with auto-commit/rollback (`db.py`) is clean and prevents leaked sessions.

5. **Job tracking granularity.** Tracking `current_step`, `failed_step`, `error_message` on the Job model gives excellent debuggability when a pipeline run fails.

6. **Lean frontend.** ~500 LOC React, small component count, custom hooks (`useVtt`, `useWakeLock`), utility extraction (`parseVtt`). No over-engineering.

---

## Issues

### 1. Duplicated Code: `llm.py` is Copy-Pasted

**Severity:** High  
**Effort:** Medium

**Problem:** `tk-srt-translate/tk_srt_translate/llm.py` and `tk-comment-translator/tk_comment_translator/llm.py` are character-for-character identical (54 lines each). The `config.py`, `validator.py`, and `batcher.py` files also share substantial patterns. When you fix a bug or upgrade MLX, you have to remember to update both.

**Fix:** Extract a shared package:

```
fr-tiktok/
├── tk-llm-core/                # NEW shared library
│   ├── src/tk_llm_core/
│   │   ├── __init__.py
│   │   ├── llm.py              # the single copy
│   │   └── config.py           # shared TranslationConfig
│   └── pyproject.toml
├── tk-srt-translate/           # depends on tk-llm-core
├── tk-comment-translator/      # depends on tk-llm-core
```

In each consumer's `pyproject.toml`:

```toml
dependencies = ["tk-llm-core @ file:///${PROJECT_ROOT}/../tk-llm-core"]
```

---

### 2. Inconsistent CLI Frameworks

**Severity:** Low  
**Effort:** Medium

**Problem:** 6 services use Click, 4 use argparse. This creates cognitive overhead when switching between services and inconsistent UX (help formatting, error messages, argument parsing behavior).

| Click | argparse |
|-------|----------|
| tk-stt, tk-aligner, tk-down, tk-srt-merger, tk-orchestrator | tk-punctuation, tk-channel-checker, tk-comment-checker, tk-srt-translate, tk-comment-translator |

**Fix:** Standardize on Click — it's already the majority choice, it's declarative, and it produces better help output. Do it incrementally when you touch each service.

---

### 3. Inconsistent Package Layouts

**Severity:** Medium  
**Effort:** Medium

**Problem:** Some services use `src/` layout, others don't:

```
tk-aligner/src/tk_aligner/              # src layout
tk-channel-checker/tk_channel_checker/  # flat layout
tk-srt-translate/tk_srt_translate/      # flat layout
```

**Why it matters:** The `src/` layout prevents accidental imports of the local directory instead of the installed package. Mixed layouts make the repo harder to navigate and script against.

**Fix:** Standardize on `src/` layout for all services. It's the modern Python packaging recommendation (PEP 517/518).

---

### 4. Inconsistent Build Systems

**Severity:** Medium  
**Effort:** Medium

**Problem:** 7 services use Hatchling, 4 use Setuptools. Same divergence issue as CLI frameworks.

**Fix:** Standardize on Hatchling (already the majority). Simpler and works well with `src/` layout.

---

### 5. No Dependency Pinning / Lock Files

**Severity:** Medium  
**Effort:** Low

**Problem:** Almost no version pins in `pyproject.toml` files. `click`, `playwright`, `httpx`, `torch`, `beautifulsoup4` are all unpinned. A `pip install` today and tomorrow can produce different environments.

**Fix:** Add a lock file at the repo root using `pip-tools` or `uv`:

```bash
uv pip compile --all-extras pyproject.toml -o requirements-lock.txt
```

At minimum, pin major versions in each `pyproject.toml`:

```toml
dependencies = [
    "playwright>=1.40,<2",
    "click>=8,<9",
]
```

---

### 6. No Shared Interface Contract Between Services

**Severity:** Medium  
**Effort:** Medium

**Problem:** Services communicate via JSON, but the schema is implicit. The orchestrator trusts that `tk-stt` outputs `{"text": "..."}`, but there's no validation at the boundary. If a service changes its output format, the pipeline silently breaks or produces garbled results.

**Fix:** Add a lightweight shared schema, even just as a `tk-schemas/` directory with JSON Schema files or Python TypedDicts:

```python
# tk-schemas/schemas.py
from typing import TypedDict

class TranscriptionResult(TypedDict):
    text: str

class AlignedWord(TypedDict):
    start: float
    end: float
    text: str
```

Services can optionally validate their output against these. The orchestrator can validate inputs between steps.

---

### 7. Hardcoded API Port in Frontend

**Severity:** Medium  
**Effort:** Low

**Problem:** In `tk-web/src/api.ts`:

```typescript
const BASE = `${window.location.protocol}//${window.location.hostname}:8000`
```

Port 8000 is hardcoded. If you deploy behind a reverse proxy, change the port, or run on a non-standard setup, you must rebuild the frontend.

**Fix:** Use a Vite environment variable:

```typescript
const BASE = import.meta.env.VITE_API_BASE
  ?? `${window.location.protocol}//${window.location.hostname}:8000`
```

---

### 8. SQLite Database Committed to Git

**Severity:** High  
**Effort:** Low

**Problem:** `tk-orchestrator/tk_orchestrator.db` is in the repo. The `.gitignore` doesn't exclude `*.db` files. This causes merge conflicts, bloats the repo, and could leak data.

**Fix:** Add to `.gitignore`:

```
*.db
*.db-journal
*.db-wal
```

Then remove the tracked file:

```bash
git rm --cached tk-orchestrator/tk_orchestrator.db
```

---

### 9. No Tests

**Severity:** High  
**Effort:** Medium

**Problem:** There are zero automated tests. The existing `test.sh` files are manual smoke tests that print output for human inspection. No pytest, no CI, no assertions.

**Why it matters:** Each service is small enough to test easily. The translation pipeline is particularly fragile (prompt-dependent LLM output), and regressions will be silent.

**Fix (incremental):**

1. Add a root-level `pytest.ini` or `pyproject.toml` with pytest config
2. Start with the pure-logic services that don't need ML models: `tk-srt-merger`, `tk-punctuation` (mock the transformer), the parsers in `tk-channel-checker` and `tk-comment-checker`
3. Add fixture data from the existing `artifact-reference/` directory

```
tk-srt-merger/
├── tests/
│   ├── test_merger.py          # unit tests with sample data
│   └── fixtures/
│       ├── aligned.json
│       └── punctuated.json
```

---

### 10. Pipeline Has No Retry or Idempotency

**Severity:** High  
**Effort:** Low

**Problem:** In `pipeline.py`, if step 5 (translation) fails after steps 1-4 succeeded, you must re-run the entire pipeline from scratch — re-downloading, re-transcribing, re-aligning. Each ML step is expensive (minutes on Apple Silicon).

**Fix:** Add step-level resume. Check for existing artifacts before running each step:

```python
# In pipeline.py, before each step:
if not raw_json.exists():
    set_step("stt")
    await run_cmd(["tk-stt", ...], job_logger)
else:
    job_logger.info("[stt] skipping — %s already exists", raw_json)
```

This is simple, file-based idempotency. The artifacts are already well-defined paths.

---

### 11. `output/` Directory Couples Orchestrator to Deployment

**Severity:** Low  
**Effort:** Low

**Problem:** The `output/` directory lives inside `tk-orchestrator/` and is served as static files by FastAPI. This means the orchestrator's working directory matters, and you can't easily separate compute from serving.

**Fix:** Make `output_dir` default to an absolute path and mount it explicitly in the API:

```python
output_dir: Path = dataclasses.field(
    default_factory=lambda: Path("./output").resolve()
)
```

---

### 12. CORS Wide Open

**Severity:** Low  
**Effort:** Low

**Problem:** The API enables CORS for all origins (`*`). Fine for local dev, risky if ever exposed to a network.

**Fix:** Make allowed origins configurable:

```python
origins = config.cors_origins or ["http://localhost:5173"]
app.add_middleware(CORSMiddleware, allow_origins=origins, ...)
```

---

### 13. `.DS_Store` Committed

**Severity:** Low  
**Effort:** Low

**Problem:** `.DS_Store` is tracked in git despite being in `.gitignore`. It was committed before the gitignore rule was added.

**Fix:**

```bash
git rm --cached .DS_Store
git rm --cached tk-orchestrator/.DS_Store  # if present
```

---

## Prioritization Matrix

| Priority | Issue | Effort |
|----------|-------|--------|
| **High** | #1 — Extract shared `llm.py` into `tk-llm-core` | Medium |
| **High** | #8 — Remove `.db` and `.DS_Store` from git, fix `.gitignore` | Low |
| **High** | #10 — Add step-level resume to pipeline | Low |
| **High** | #9 — Add basic pytest tests for pure-logic services | Medium |
| **Medium** | #3 + #4 — Standardize `src/` layout + Hatchling | Medium |
| **Medium** | #5 — Pin dependency versions | Low |
| **Medium** | #7 — Make API port configurable in frontend | Low |
| **Medium** | #6 — Add shared JSON schema contracts | Medium |
| **Low** | #2 — Standardize CLI framework (Click) | Medium |
| **Low** | #12 — Configure CORS properly | Low |
| **Low** | #11 — Decouple output directory | Low |
| **Low** | #13 — Remove `.DS_Store` from tracking | Low |
