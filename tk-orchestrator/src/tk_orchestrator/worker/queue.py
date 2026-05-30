from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text

from ..config import Config
from ..models import Job, get_session
from .pipeline import run_pipeline

logger = logging.getLogger(__name__)

_CLAIM_CANDIDATE_SQL = text("""
    SELECT id, status FROM jobs
    WHERE status IN ('pending', 'interrupted')
    ORDER BY created_at ASC, id ASC
    LIMIT 1
""")

_CLAIM_BY_ID_SQL = text("""
    UPDATE jobs
    SET status = 'running'
    WHERE id = :id AND status IN ('pending', 'interrupted')
""")


async def worker(config: Config) -> None:
    logger.info("Worker started — polling for pending jobs")
    while True:
        claimed = _claim_next_job()
        if claimed:
            job_id, prior_status = claimed
            logger.info("Claimed job %d", job_id)
            try:
                await run_pipeline(job_id, config, prior_status=prior_status)
            except Exception:
                logger.exception("Unexpected error processing job %d", job_id)
        else:
            await asyncio.sleep(5)


def _claim_next_job() -> tuple[int, str] | None:
    """Atomically claim the oldest eligible job.

    Returns ``(job_id, prior_status)`` so the pipeline can distinguish a
    fresh run from a resume, or ``None`` if nothing is claimable or another
    runner won the race.
    """
    with get_session() as s:
        row = s.execute(_CLAIM_CANDIDATE_SQL).fetchone()
        if row is None:
            return None
        job_id, prior_status = row[0], row[1]
        result = s.execute(_CLAIM_BY_ID_SQL, {"id": job_id})
        if result.rowcount == 0:
            return None
        return job_id, prior_status


def claim_job(job_id: int) -> str | None:
    """Atomically claim a specific job by id.

    Returns the job's prior status (``pending``/``interrupted``), or ``None``
    if the job is missing or already claimed by another runner.
    """
    with get_session() as s:
        row = s.execute(
            text("SELECT status FROM jobs WHERE id = :id"), {"id": job_id}
        ).fetchone()
        if row is None:
            return None
        prior_status = row[0]
        if prior_status not in ("pending", "interrupted"):
            return None
        result = s.execute(_CLAIM_BY_ID_SQL, {"id": job_id})
        if result.rowcount == 0:
            return None
        return prior_status


def recover_interrupted_jobs() -> list[int]:
    with get_session() as s:
        stuck = (
            s.query(Job)
            .filter(Job.status == "running")
            .order_by(Job.created_at.asc(), Job.id.asc())
            .all()
        )
        ids = []
        for j in stuck:
            j.status = "interrupted"
            if not j.error_message:
                j.error_message = "Interrupted during previous shutdown"
            logger.warning(
                "Recovered stale running job %d as interrupted at step %s",
                j.id,
                j.current_step or "download",
            )
            ids.append(j.id)
        return ids
