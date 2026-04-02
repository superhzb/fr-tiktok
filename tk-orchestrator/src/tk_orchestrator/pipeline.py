from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

from .config import Config
from .db import Job, get_session
from .logging_config import get_job_logger, remove_job_logger

logger = logging.getLogger(__name__)


async def run_cmd(cmd: list[str], job_logger: logging.Logger) -> str:
    """Run a subprocess, stream stderr to the logger, and return stdout.

    Raises RuntimeError on non-zero exit code with stderr as the message.
    """
    job_logger.debug("$ %s", " ".join(cmd))
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stderr_lines: list[str] = []

    async def _drain_stderr() -> None:
        assert proc.stderr
        async for raw in proc.stderr:
            line = raw.decode().rstrip()
            stderr_lines.append(line)
            job_logger.debug("[stderr] %s", line)

    drain_task = asyncio.create_task(_drain_stderr())
    assert proc.stdout
    stdout_bytes = await proc.stdout.read()
    await drain_task
    await proc.wait()

    if proc.returncode != 0:
        raise RuntimeError(
            "\n".join(stderr_lines) or f"process exited with code {proc.returncode}"
        )

    return stdout_bytes.decode().strip()


async def run_pipeline(job_id: int, config: Config) -> None:
    """Run the full subtitle pipeline for a job."""
    with get_session() as s:
        job = s.get(Job, job_id)
        if job is None:
            logger.error("Job %d not found", job_id)
            return
        video_id = job.video_id
        video_url = job.video.url
        channel_username = job.video.channel.username

    video_dir = config.output_dir / channel_username / video_id
    video_dir.mkdir(parents=True, exist_ok=True)

    job_logger = get_job_logger(job_id, video_dir)
    job_logger.info("Starting pipeline for job %d (video %s)", job_id, video_id)

    with get_session() as s:
        j = s.get(Job, job_id)
        if j:
            j.status = "running"
            j.started_at = datetime.now(timezone.utc)

    def set_step(step: str) -> None:
        with get_session() as s:
            j = s.get(Job, job_id)
            if j:
                j.current_step = step

    def fail(step: str, error: str) -> None:
        with get_session() as s:
            j = s.get(Job, job_id)
            if j:
                j.status = "failed"
                j.failed_step = step
                j.error_message = error
                j.current_step = None

    current_step = "download"
    try:
        # ── download ──────────────────────────────────────────────────────────
        set_step("download")
        job_logger.info("[download] %s", video_url)
        video_path = Path(
            await run_cmd(["tk-down", video_url, "--output-dir", str(video_dir)], job_logger)
        )
        job_logger.info("[download] saved to %s", video_path)
        with get_session() as s:
            j = s.get(Job, job_id)
            if j:
                j.video_path = str(video_path)

        # ── speech-to-text ────────────────────────────────────────────────────
        current_step = "stt"
        raw_json = video_dir / "raw_transcription.json"
        set_step("stt")
        job_logger.info("[stt] transcribing")
        await run_cmd(
            ["tk-stt", str(video_path), "--output", str(raw_json), "--model", config.stt_model],
            job_logger,
        )

        # ── punctuation ───────────────────────────────────────────────────────
        current_step = "punctuation"
        punctuated_json = video_dir / "punctuated.json"
        set_step("punctuation")
        job_logger.info("[punctuation] adding punctuation")
        punct_out = await run_cmd(
            ["tk-punctuation", "--input-file", str(raw_json)], job_logger
        )
        punctuated_json.write_text(punct_out)

        # ── alignment ─────────────────────────────────────────────────────────
        current_step = "alignment"
        aligned_json = video_dir / "aligned.json"
        set_step("alignment")
        job_logger.info("[alignment] aligning words")
        await run_cmd(
            [
                "tk-aligner",
                str(video_path),
                str(punctuated_json),
                "--output",
                str(aligned_json),
                "--model",
                config.aligner_model,
            ],
            job_logger,
        )

        # ── SRT merge ─────────────────────────────────────────────────────────
        current_step = "srt_merge"
        srt_path = video_dir / "subtitles.srt"
        set_step("srt_merge")
        job_logger.info("[srt_merge] generating SRT")
        await run_cmd(
            ["tk-srt-merger", str(aligned_json), str(punctuated_json), str(srt_path)],
            job_logger,
        )
        with get_session() as s:
            j = s.get(Job, job_id)
            if j:
                j.srt_path = str(srt_path)

        # ── translation ───────────────────────────────────────────────────────
        current_step = "translation"
        vtt_path = video_dir / f"subtitles.bilingual.{config.translate_format}"
        set_step("translation")
        job_logger.info("[translation] translating subtitles")
        await run_cmd(
            [
                "tk-srt-translate",
                str(srt_path),
                "--output",
                str(vtt_path),
                "--format",
                config.translate_format,
                "--model",
                config.translate_model,
                "--batch-size",
                str(config.translate_batch_size),
            ],
            job_logger,
        )
        with get_session() as s:
            j = s.get(Job, job_id)
            if j:
                j.vtt_path = str(vtt_path)

        # ── done ──────────────────────────────────────────────────────────────
        with get_session() as s:
            j = s.get(Job, job_id)
            if j:
                j.status = "completed"
                j.current_step = None
                j.completed_at = datetime.now(timezone.utc)

        logger.info("Job %d completed", job_id)
        job_logger.info("Pipeline completed successfully")

    except Exception as e:
        fail(current_step, str(e))
        job_logger.error("[%s] FAILED: %s", current_step, e)
        logger.error("Job %d failed at '%s': %s", job_id, current_step, e)
    finally:
        remove_job_logger(job_id)
