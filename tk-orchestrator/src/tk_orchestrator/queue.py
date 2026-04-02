from __future__ import annotations

import asyncio
import logging

from .config import Config
from .pipeline import run_pipeline

logger = logging.getLogger(__name__)

_queue: asyncio.Queue[int] = asyncio.Queue()


def enqueue(job_id: int) -> None:
    """Add a job ID to the processing queue."""
    _queue.put_nowait(job_id)
    logger.info("Enqueued job %d", job_id)


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
