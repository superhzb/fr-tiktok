from __future__ import annotations

import asyncio
import logging

from .config import Config
from .models import Job, get_session
from .pipeline import run_pipeline

logger = logging.getLogger(__name__)

_queue: asyncio.Queue[int] = asyncio.Queue()


def enqueue(job_id: int) -> None:
    """Add a job ID to the processing queue."""
    _queue.put_nowait(job_id)
    logger.info("Enqueued job %d", job_id)


def recover_interrupted_jobs() -> list[int]:
    """Mark stale running jobs as interrupted and re-enqueue resumable work."""
    with get_session() as s:
        jobs = (
            s.query(Job)
            .filter(Job.status.in_(["running", "interrupted"]))
            .order_by(Job.created_at.asc(), Job.id.asc())
            .all()
        )
        job_ids = [job.id for job in jobs]
        for job in jobs:
            if job.status == "running":
                job.status = "interrupted"
                if not job.error_message:
                    job.error_message = "Interrupted during previous shutdown"
                logger.warning(
                    "Recovered stale running job %d as interrupted at step %s",
                    job.id,
                    job.current_step or "download",
                )
            else:
                logger.info(
                    "Re-enqueueing interrupted job %d from step %s",
                    job.id,
                    job.current_step or "download",
                )

    for job_id in job_ids:
        enqueue(job_id)
    return job_ids


async def worker(config: Config) -> None:
    """Single worker coroutine — processes one job at a time."""
    logger.info("Queue worker started")
    while True:
        job_id = await _queue.get()
        logger.info("Processing job %d", job_id)
        try:
            await run_pipeline(job_id, config)
        except Exception:
            logger.exception("Unexpected error processing job %d", job_id)
        finally:
            _queue.task_done()
