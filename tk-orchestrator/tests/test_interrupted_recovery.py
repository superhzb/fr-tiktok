import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tk_orchestrator.config import Config
from tk_orchestrator.db import Channel, Job, Video, get_session, init_db
from tk_orchestrator.pipeline import run_pipeline
from tk_orchestrator.queue import _queue, recover_interrupted_jobs


class InterruptedPipelineRecoveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        temp_path = Path(self.temp_dir.name)
        self.config = Config(
            db_path=temp_path / "test.db",
            output_dir=temp_path / "output",
        )
        init_db(self.config)
        self.channel_username = "creator.test"
        self.video_id = "7351234567890123456"
        self.video_url = f"https://www.tiktok.com/@{self.channel_username}/video/{self.video_id}"
        self.job_id = self._seed_job()

    def tearDown(self) -> None:
        while True:
            try:
                _queue.get_nowait()
                _queue.task_done()
            except asyncio.QueueEmpty:
                break
        self.temp_dir.cleanup()

    def _seed_job(
        self,
        *,
        status: str = "pending",
        current_step: str | None = None,
        error_message: str | None = None,
    ) -> int:
        with get_session() as session:
            channel = Channel(username=self.channel_username, url=f"https://www.tiktok.com/@{self.channel_username}")
            session.add(channel)
            session.flush()
            session.add(
                Video(
                    id=self.video_id,
                    channel_id=channel.id,
                    url=self.video_url,
                    author=self.channel_username,
                )
            )
            job = Job(
                video_id=self.video_id,
                status=status,
                current_step=current_step,
                error_message=error_message,
            )
            session.add(job)
            session.flush()
            return job.id

    async def test_interrupted_job_resumes_from_last_step(self) -> None:
        video_dir = self.config.output_dir / self.channel_username / self.video_id
        video_path = video_dir / "video.mp4"
        raw_json = video_dir / "raw_transcription.json"
        aligned_json = video_dir / "aligned.json"
        srt_path = video_dir / "subtitles.srt"
        vtt_path = video_dir / "subtitles.vtt"
        first_run_cmds: list[str] = []

        async def interrupting_run_cmd(cmd: list[str], _job_logger) -> str:
            first_run_cmds.append(cmd[0])
            if cmd[0] == "tk-down":
                video_path.parent.mkdir(parents=True, exist_ok=True)
                video_path.write_text("video", encoding="utf-8")
                return str(video_path)
            if cmd[0] == "tk-stt":
                raise asyncio.CancelledError()
            self.fail(f"Unexpected command before interruption: {cmd[0]}")

        with patch("tk_orchestrator.pipeline.run_cmd", side_effect=interrupting_run_cmd):
            with self.assertRaises(asyncio.CancelledError):
                await run_pipeline(self.job_id, self.config)

        self.assertEqual(first_run_cmds, ["tk-down", "tk-stt"])
        with get_session() as session:
            job = session.get(Job, self.job_id)
            assert job is not None
            self.assertEqual(job.status, "interrupted")
            self.assertEqual(job.current_step, "stt")
            self.assertEqual(job.video_path, str(video_path))
            self.assertIsNone(job.failed_step)

        resumed_cmds: list[str] = []

        async def successful_run_cmd(cmd: list[str], _job_logger) -> str:
            resumed_cmds.append(cmd[0])
            if cmd[0] == "tk-stt":
                raw_json.write_text("{}", encoding="utf-8")
                return ""
            if cmd[0] == "tk-punctuation":
                return "{}"
            if cmd[0] == "tk-aligner":
                aligned_json.write_text("{}", encoding="utf-8")
                return ""
            if cmd[0] == "tk-srt-merger":
                srt_path.write_text("1\n00:00:00,000 --> 00:00:01,000\nhello\n", encoding="utf-8")
                return ""
            if cmd[0] == "tk-batch-translate":
                vtt_path.write_text("WEBVTT\n", encoding="utf-8")
                return ""
            self.fail(f"Unexpected command during resume: {cmd[0]}")

        with patch("tk_orchestrator.pipeline.run_cmd", side_effect=successful_run_cmd):
            await run_pipeline(self.job_id, self.config)

        self.assertEqual(
            resumed_cmds,
            ["tk-stt", "tk-punctuation", "tk-aligner", "tk-srt-merger", "tk-batch-translate"],
        )
        with get_session() as session:
            job = session.get(Job, self.job_id)
            assert job is not None
            self.assertEqual(job.status, "completed")
            self.assertIsNone(job.current_step)
            self.assertEqual(job.srt_path, str(srt_path))
            self.assertEqual(job.vtt_path, str(vtt_path))
            self.assertIsNone(job.error_message)


class QueueRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        temp_path = Path(self.temp_dir.name)
        self.config = Config(
            db_path=temp_path / "test.db",
            output_dir=temp_path / "output",
        )
        init_db(self.config)
        self.channel_username = "creator.test"

    def tearDown(self) -> None:
        while True:
            try:
                _queue.get_nowait()
                _queue.task_done()
            except asyncio.QueueEmpty:
                break
        self.temp_dir.cleanup()

    def test_recover_interrupted_jobs_requeues_resumable_work(self) -> None:
        with get_session() as session:
            channel = Channel(username=self.channel_username, url=f"https://www.tiktok.com/@{self.channel_username}")
            session.add(channel)
            session.flush()
            video_one = Video(
                id="7351234567890123456",
                channel_id=channel.id,
                url=f"https://www.tiktok.com/@{self.channel_username}/video/7351234567890123456",
                author=self.channel_username,
            )
            video_two = Video(
                id="7351234567890123457",
                channel_id=channel.id,
                url=f"https://www.tiktok.com/@{self.channel_username}/video/7351234567890123457",
                author=self.channel_username,
            )
            session.add(video_one)
            session.add(video_two)
            job_one = Job(video_id=video_one.id, status="running", current_step="alignment")
            job_two = Job(
                video_id=video_two.id,
                status="interrupted",
                current_step="translation",
                error_message="Interrupted during translation",
            )
            session.add(job_one)
            session.add(job_two)
            session.flush()
            running_job_id = job_one.id
            interrupted_job_id = job_two.id

        recovered = recover_interrupted_jobs()

        self.assertEqual(recovered, [running_job_id, interrupted_job_id])
        queued = [_queue.get_nowait(), _queue.get_nowait()]
        _queue.task_done()
        _queue.task_done()
        self.assertEqual(queued, [running_job_id, interrupted_job_id])
        with get_session() as session:
            running_job = session.get(Job, running_job_id)
            interrupted_job = session.get(Job, interrupted_job_id)
            assert running_job is not None
            assert interrupted_job is not None
            self.assertEqual(running_job.status, "interrupted")
            self.assertEqual(
                running_job.error_message,
                "Interrupted during previous shutdown",
            )
            self.assertEqual(interrupted_job.status, "interrupted")
            self.assertEqual(
                interrupted_job.error_message,
                "Interrupted during translation",
            )
