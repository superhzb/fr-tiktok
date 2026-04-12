from __future__ import annotations

import asyncio
import logging
import os
from contextlib import suppress

from ..mlx import mlx_job_guard


async def run_cli(
    cmd: list[str],
    job_logger: logging.Logger,
    *,
    extra_env: dict[str, str] | None = None,
) -> str:
    """Run a subprocess, stream stderr to the logger, and return stdout.

    Raises RuntimeError on non-zero exit code.
    """
    job_logger.debug("$ %s", " ".join(cmd))
    run_env = {**os.environ, **(extra_env or {})}
    async with mlx_job_guard(cmd, job_logger):
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=run_env,
        )
        stderr_lines: list[str] = []

        async def _drain_stderr() -> None:
            assert proc.stderr
            async for raw in proc.stderr:
                line = raw.decode().rstrip()
                stderr_lines.append(line)
                job_logger.debug("[stderr] %s", line)

        drain_task = asyncio.create_task(_drain_stderr())
        stdout_bytes = b""
        try:
            assert proc.stdout
            stdout_bytes = await proc.stdout.read()
            await drain_task
            await proc.wait()
        except asyncio.CancelledError:
            job_logger.warning("Command interrupted, terminating subprocess")
            if proc.returncode is None:
                with suppress(ProcessLookupError):
                    proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except asyncio.TimeoutError:
                    with suppress(ProcessLookupError):
                        proc.kill()
                    await proc.wait()
            drain_task.cancel()
            with suppress(asyncio.CancelledError):
                await drain_task
            raise

        if proc.returncode != 0:
            raise RuntimeError(
                "\n".join(stderr_lines) or f"process exited with code {proc.returncode}"
            )

        return stdout_bytes.decode().strip()
