# Architecture Issues & Improvements

## 1. No API Authentication

**Severity:** High
**Area:** Backend (tk-orchestrator)

CORS allows all origins and there is no authentication on any endpoints, including admin operations like `add-channel`. Any client can add channels, view all data, and trigger processing.

**Recommendation:** Add API key or session-based auth, at minimum for write operations. FastAPI supports dependency-injection-based auth guards natively.

---

## 2. No Retry / Backoff on Failed Jobs

**Severity:** High
**Area:** Backend (tk-orchestrator/pipeline.py)

Failed jobs are marked as `failed` with no recovery path. TikTok downloads and ML inference are inherently flaky — transient failures are expected.

**Recommendation:** Add a configurable retry count and exponential backoff in `pipeline.py`. Track `retry_count` on the `jobs` table so retries are auditable.

---

## 3. No Tests

**Severity:** High
**Area:** All packages

No test files exist anywhere in the repo. Regressions can go unnoticed across all 11 services.

**Recommendation:** Add at least:
- Unit tests for utility functions (`parseVtt`, config loading, SRT parsing)
- Integration tests for each `tk-*` CLI tool (valid input → expected output)
- API endpoint tests for `tk-orchestrator` using FastAPI's `TestClient`

---

## 4. No CI/CD Pipeline

**Severity:** High
**Area:** Repository

No GitHub Actions or equivalent CI configuration. No automated linting, type checking, or testing on push/PR.

**Recommendation:** Add a GitHub Actions workflow that runs:
- `tsc --noEmit` for the frontend
- `mypy` or `pyright` for Python packages
- Test suites for all packages
- Linting (`ruff` for Python, `eslint` for TypeScript)

---

## 5. Sequential Processing Only

**Severity:** Medium
**Area:** Backend (tk-orchestrator/queue.py)

Videos are processed one at a time via `asyncio.Queue`. This bottlenecks throughput as the number of monitored channels grows.

**Recommendation:** Replace the single worker with a worker pool using `asyncio.Semaphore(N)` to allow configurable concurrency. For larger scale, consider an external task queue (Redis + Celery or similar).

---

## 6. No Frontend Routing

**Severity:** Medium
**Area:** Frontend (tk-web)

The app is a single page with no URL state. Users cannot deep-link to a specific video or share URLs.

**Recommendation:** Add `react-router` with routes like `/video/:id`. Persist the active video index in the URL so links are shareable and browser back/forward work as expected.

---

## 7. Prop Drilling in Frontend

**Severity:** Medium
**Area:** Frontend (tk-web)

`subtitleSettings` is passed through 3+ component levels (VideoFeed → VideoPlayer → SubtitleOverlay / SubtitleSettingsPanel).

**Recommendation:** Extract shared settings into a React Context provider. This simplifies the component tree and makes it easier to add new settings without threading props through every layer.

---

## 8. No Input Validation on API Endpoints

**Severity:** Medium
**Area:** Backend (tk-orchestrator/api.py)

API endpoints do not validate path parameters or query parameters. Malformed `video_id` values are passed directly to database queries.

**Recommendation:** Use Pydantic models for request validation. FastAPI supports this natively with `Path()`, `Query()`, and request body models.

---

## 9. No Structured Logging

**Severity:** Low
**Area:** All Python packages

Logging is inconsistent across services — mixed `print()` statements and Python `logging` calls with no standard format.

**Recommendation:** Standardize on Python's `logging` module with a structured JSON format. This enables log aggregation, filtering by service/level, and easier debugging of pipeline failures.

---

## 10. No Health Check Endpoint

**Severity:** Low
**Area:** Backend (tk-orchestrator/api.py)

No `/health` endpoint exists. This makes it difficult to monitor service availability or integrate with container orchestration (Docker, Kubernetes).

**Recommendation:** Add a `GET /health` endpoint that returns service status, DB connectivity, and scheduler state. This is essential for any deployment beyond local development.
