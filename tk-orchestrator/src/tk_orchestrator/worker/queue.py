from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text

from ..config import Config
from ..models import Job, get_session
from .pipeline import run_pipeline

logger = logging.getLogger(__name__)

_CLAIM_SQL = text("""
    UPDATE jobs
    SET status = 'running'
    WHERE id = (
        SELECT id FROM jobs
        WHERE status IN ('pending', 'interrupted')
        ORDER BY created_at ASC, id ASC
        LIMIT 1
    )
    AND status IN ('pending', 'interrupted')
    RETURNING id
""")


async def worker(config: Config) -> None:
    logger.info("Worker started — polling for pending jobs")
    while True:
        job_id = _claim_next_job()
        if job_id:
            logger.info("Claimed job %d", job_id)
            try:
                await run_pipeline(job_id, config)
            except Exception:
                logger.exception("Unexpected error processing job %d", job_id)
        else:
            await asyncio.sleep(5)


def _claim_next_job() -> int | None:
    with get_session() as s:
        row = s.execute(_CLAIM_SQL).fetchone()
        if row:
            return row[0]
    return None


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
