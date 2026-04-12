from __future__ import annotations

import asyncio
import fcntl
import logging
from contextlib import asynccontextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

_MLX_COMMANDS = {
    "tk-aligner",
    "tk-batch-translate",
    "tk-stt",
}
_DEFAULT_LOCK_PATH = Path("/tmp/tk-orchestrator-mlx.lock")
_process_lock = asyncio.Lock()


def is_mlx_command(cmd: list[str]) -> bool:
    return bool(cmd) and cmd[0] in _MLX_COMMANDS


class _FileLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        except Exception:
            handle.close()
            raise
        self._handle = handle

    def release(self) -> None:
        if self._handle is None:
            return
        try:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._handle.close()
            self._handle = None


@asynccontextmanager
async def mlx_job_guard(
    cmd: list[str],
    job_logger: logging.Logger,
    *,
    lock_path: Path | None = None,
):
    if not is_mlx_command(cmd):
        yield
        return

    target_lock_path = lock_path or _DEFAULT_LOCK_PATH
    async with _process_lock:
        lock = _FileLock(target_lock_path)
        job_logger.info("[mlx] waiting for exclusive slot: %s", cmd[0])
        await asyncio.to_thread(lock.acquire)
        job_logger.info("[mlx] acquired exclusive slot: %s", cmd[0])
        logger.info("MLX slot acquired for %s", cmd[0])
        try:
            yield
        finally:
            await asyncio.to_thread(lock.release)
            job_logger.info("[mlx] released exclusive slot: %s", cmd[0])
            logger.info("MLX slot released for %s", cmd[0])
