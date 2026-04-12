"""
Full end-to-end pipeline test.

Run this once to validate the full pipeline and generate fixtures.
After it passes, run tests/test_pipeline.py --from-step <step> for targeted retests.
"""

import asyncio
import shutil
from pathlib import Path

from conftest import (
    FIXTURES_DIR,
    TEST_VIDEO_ID,
    TEST_VIDEO_URL,
    TEST_CHANNEL_URL,
)


def test_full_pipeline_happy_path(test_config):
    """
    Happy path: insert target video directly → download → stt → punctuation →
    alignment → srt_merge → translation → comments fetched and translated
    → job status = completed.
    """
    from tk_orchestrator.models import Channel, Video, Job, Comment, get_session
    from tk_orchestrator.scheduler import _run_comments, _translate_comments
    from tk_orchestrator.pipeline import run_pipeline

    # Step 1: Insert channel + target video + job directly, bypassing the channel
    # checker so we always test the specific pinned video regardless of what the
    # channel has uploaded since.
    with get_session() as s:
        channel = Channel(
            username="frances.con.romeo",
            url=TEST_CHANNEL_URL,
            is_active=True,
        )
        s.add(channel)
        s.flush()

        video = Video(
            id=TEST_VIDEO_ID,
            channel_id=channel.id,
            url=TEST_VIDEO_URL,
            description=None,
        )
        job = Job(video_id=TEST_VIDEO_ID, status="pending")
        s.add(video)
        s.add(job)
        s.flush()
        job_id = job.id

    print(f"\n→ Running pipeline for video {TEST_VIDEO_ID}")

    # Step 2: Fetch and translate comments
    comments = asyncio.run(_run_comments(TEST_VIDEO_URL, test_config))
    comments = asyncio.run(_translate_comments(comments, None, test_config))
    with get_session() as s:
        for c in comments:
            s.add(
                Comment(
                    video_id=TEST_VIDEO_ID,
                    user=c.get("user"),
                    username=c.get("username"),
                    text=c.get("text"),
                    zh=c.get("zh"),
                    likes=c.get("likes"),
                )
            )

    # Step 3: Run the pipeline to completion
    asyncio.run(run_pipeline(job_id, test_config))

    # Step 4: Assert final job state
    with get_session() as s:
        job = s.query(Job).filter(Job.id == job_id).first()
        assert job.status == "completed", (
            f"Job ended with status '{job.status}'. "
            f"Failed step: {job.failed_step}. Error: {job.error_message}"
        )
        assert job.error_message is None

    # Step 5: Assert all output files exist
    video_output_dir = (
        Path(test_config.output_dir) / "frances.con.romeo" / TEST_VIDEO_ID
    )
    expected_files = [
        "raw_transcription.json",
        "punctuated.json",
        "aligned.json",
        "subtitles.srt",
        "subtitles.vtt",
    ]
    for filename in expected_files:
        path = video_output_dir / filename
        assert path.exists(), f"Missing output file: {path}"
        assert path.stat().st_size > 0, f"Empty output file: {path}"

    video_files = list(video_output_dir.glob("*.mp4"))
    assert len(video_files) > 0, "No .mp4 file found in output directory."

    # Step 6: Assert comments in DB
    with get_session() as s:
        comments_db = s.query(Comment).filter(Comment.video_id == TEST_VIDEO_ID).all()
        assert len(comments_db) > 0, "No comments were saved to the database."
        assert any(c.zh for c in comments_db), "No comments have Chinese translation."

    # Step 7: Save all artifacts as fixtures
    fixture_dir = FIXTURES_DIR / TEST_VIDEO_ID
    fixture_dir.mkdir(parents=True, exist_ok=True)
    for filename in expected_files:
        shutil.copy2(video_output_dir / filename, fixture_dir / filename)
    shutil.copy2(video_files[0], fixture_dir / "video.mp4")
    print(f"\n✓ Fixtures saved to {fixture_dir}")
