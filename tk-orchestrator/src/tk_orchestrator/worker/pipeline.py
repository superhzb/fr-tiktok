from __future__ import annotations

import asyncio
import logging
import os
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path

from ..config import Config
from ..mlx import mlx_job_guard
from ..models import Job, get_session
from ..logging_config import get_job_logger, remove_job_logger

logger = logging.getLogger(__name__)
PIPELINE_STEPS = (
    "download",
    "stt",
    "punctuation",
    "alignment",
    "srt_merge",
    "translation",
)


def _step_index(step: str) -> int:
    return PIPELINE_STEPS.index(step)


def _resolve_resume_step(job, video_dir: Path) -> str:
    last_done = getattr(job, "last_completed_step", None)
    if last_done and last_done in PIPELINE_STEPS:
        idx = PIPELINE_STEPS.index(last_done)
        if idx + 1 < len(PIPELINE_STEPS):
            return PIPELINE_STEPS[idx + 1]
        return PIPELINE_STEPS[-1]

    if job.current_step in PIPELINE_STEPS and job.status in {"running", "interrupted"}:
        return job.current_step

    video_path = Path(job.video_path) if job.video_path else None
    raw_json = video_dir / "raw_transcription.json"
    punctuated_json = video_dir / "punctuated.json"
    aligned_json = video_dir / "aligned.json"
    srt_path = Path(job.srt_path) if job.srt_path else video_dir / "subtitles.srt"

    if srt_path.exists():
        return "translation"
    if aligned_json.exists() and punctuated_json.exists():
        return "srt_merge"
    if punctuated_json.exists() and video_path and video_path.exists():
        return "alignment"
    if raw_json.exists() and video_path and video_path.exists():
        return "punctuation"
    if video_path and video_path.exists():
        return "stt"
    return "download"


def _should_run(resume_step: str, step: str) -> bool:
    return _step_index(step) >= _step_index(resume_step)


async def run_cmd(
    cmd: list[str],
    job_logger: logging.Logger,
    *,
    extra_env: dict[str, str] | None = None,
) -> str:
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


async def run_pipeline(job_id: int, config: Config) -> None:
    with get_session() as s:
        job = s.get(Job, job_id)
        if job is None:
            logger.error("Job %d not found", job_id)
            return
        video_id = job.video_id
        video_url = job.video.url
        channel_username = job.video.channel.username
        previous_status = job.status
        job_current_step = job.current_step
        job_status = job.status
        job_video_path = job.video_path
        job_srt_path = job.srt_path
        job_last_completed_step = job.last_completed_step

    video_dir = config.output_dir / channel_username / video_id
    video_dir.mkdir(parents=True, exist_ok=True)
    raw_json = video_dir / "raw_transcription.json"
    punctuated_json = video_dir / "punctuated.json"
    aligned_json = video_dir / "aligned.json"
    srt_path = video_dir / "subtitles.srt"
    vtt_path = video_dir / "subtitles.vtt"

    job_logger = get_job_logger(job_id, video_dir)

    class _JobSnapshot:
        current_step = job_current_step
        status = job_status
        video_path = job_video_path
        srt_path = job_srt_path
        last_completed_step = job_last_completed_step

    resume_step = _resolve_resume_step(_JobSnapshot(), video_dir)
    if previous_status == "interrupted":
        job_logger.info(
            "Resuming interrupted pipeline for job %d (video %s) from %s",
            job_id,
            video_id,
            resume_step,
        )
    else:
        job_logger.info("Starting pipeline for job %d (video %s)", job_id, video_id)

    with get_session() as s:
        j = s.get(Job, job_id)
        if j:
            j.status = "running"
            j.failed_step = None
            j.error_message = None
            if j.started_at is None:
                j.started_at = datetime.now(timezone.utc)
            if previous_status == "interrupted":
                logger.info(
                    "Job %d state changed: interrupted -> running (resume from %s)",
                    job_id,
                    resume_step,
                )
            else:
                logger.info(
                    "Job %d state changed: %s -> running", job_id, previous_status
                )

    def set_step(step: str) -> None:
        with get_session() as s:
            j = s.get(Job, job_id)
            if j:
                j.current_step = step

    def interrupt(step: str, error: str) -> None:
        with get_session() as s:
            j = s.get(Job, job_id)
            if j:
                j.status = "interrupted"
                j.current_step = step
                j.failed_step = None
                j.error_message = error
                logger.warning(
                    "Job %d state changed: running -> interrupted at %s",
                    job_id,
                    step,
                )

    def fail(step: str, error: str) -> None:
        with get_session() as s:
            j = s.get(Job, job_id)
            if j:
                j.status = "failed"
                j.failed_step = step
                j.error_message = error
                j.current_step = None
                logger.error(
                    "Job %d state changed: running -> failed at %s", job_id, step
                )

    video_path = Path(job_video_path) if job_video_path else None
    current_step = resume_step
    ctx_env = {"TK_JOB_ID": str(job_id), "TK_VIDEO_ID": video_id}

    def _step_env(step: str) -> dict[str, str]:
        return {**ctx_env, "TK_PIPELINE_STEP": step}

    try:
        if _should_run(resume_step, "download"):
            current_step = "download"
            set_step("download")
            job_logger.info("[download] %s", video_url)
            video_path = Path(
                await run_cmd(
                    ["tk-down", video_url, "--output-dir", str(video_dir)],
                    job_logger,
                    extra_env=_step_env("download"),
                )
            )
            job_logger.info("[download] saved to %s", video_path)
            with get_session() as s:
                j = s.get(Job, job_id)
                if j:
                    j.video_path = str(video_path)
                    j.last_completed_step = "download"
        elif video_path is None:
            mp4s = sorted(video_dir.glob("*.mp4"))
            video_path = mp4s[0] if mp4s else None

        if video_path is None:
            raise RuntimeError("missing downloaded video for resumed job")

        if _should_run(resume_step, "stt"):
            current_step = "stt"
            set_step("stt")
            job_logger.info("[stt] transcribing")
            await run_cmd(
                [
                    "tk-stt",
                    str(video_path),
                    "--output",
                    str(raw_json),
                    "--model",
                    config.stt_model,
                ],
                job_logger,
                extra_env=_step_env("stt"),
            )
            with get_session() as s:
                j = s.get(Job, job_id)
                if j:
                    j.last_completed_step = "stt"

        if _should_run(resume_step, "punctuation"):
            current_step = "punctuation"
            set_step("punctuation")
            job_logger.info("[punctuation] adding punctuation")
            punct_out = await run_cmd(
                ["tk-punctuation", "--input-file", str(raw_json)],
                job_logger,
                extra_env=_step_env("punctuation"),
            )
            punctuated_json.write_text(punct_out)
            with get_session() as s:
                j = s.get(Job, job_id)
                if j:
                    j.last_completed_step = "punctuation"

        if _should_run(resume_step, "alignment"):
            current_step = "alignment"
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
                extra_env=_step_env("alignment"),
            )
            with get_session() as s:
                j = s.get(Job, job_id)
                if j:
                    j.last_completed_step = "alignment"

        if _should_run(resume_step, "srt_merge"):
            current_step = "srt_merge"
            set_step("srt_merge")
            job_logger.info("[srt_merge] generating SRT")
            await run_cmd(
                [
                    "tk-srt-merger",
                    str(aligned_json),
                    str(punctuated_json),
                    str(srt_path),
                ],
                job_logger,
                extra_env=_step_env("srt_merge"),
            )
            with get_session() as s:
                j = s.get(Job, job_id)
                if j:
                    j.srt_path = str(srt_path)
                    j.last_completed_step = "srt_merge"

        if _should_run(resume_step, "translation"):
            current_step = "translation"
            set_step("translation")
            job_logger.info("[translation] translating subtitles")
            await run_cmd(
                [
                    "tk-batch-translate",
                    "srt",
                    str(srt_path),
                    "--output",
                    str(vtt_path),
                    "--format",
                    "vtt",
                    "--model",
                    config.translate_model,
                    "--batch-size",
                    str(config.translate_batch_size),
                ],
                job_logger,
                extra_env=_step_env("translation"),
            )
            with get_session() as s:
                j = s.get(Job, job_id)
                if j:
                    j.vtt_path = str(vtt_path)
                    j.last_completed_step = "translation"

        with get_session() as s:
            j = s.get(Job, job_id)
            if j:
                j.status = "completed"
                j.current_step = None
                j.failed_step = None
                j.error_message = None
                j.completed_at = datetime.now(timezone.utc)
                logger.info("Job %d state changed: running -> completed", job_id)

        logger.info("Job %d completed", job_id)
        job_logger.info("Pipeline completed successfully")

    except asyncio.CancelledError:
        interrupt(current_step, f"Interrupted during {current_step}")
        job_logger.warning("[%s] INTERRUPTED", current_step)
        logger.warning("Job %d interrupted at '%s'", job_id, current_step)
        raise
    except Exception as e:
        fail(current_step, str(e))
        job_logger.error("[%s] FAILED: %s", current_step, e)
        logger.error("Job %d failed at '%s': %s", job_id, current_step, e)
    finally:
        remove_job_logger(job_id)
