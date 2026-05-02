import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tk_orchestrator.config import Config
from tk_orchestrator.models import (
    Channel,
    DeletedVideo,
    Job,
    Video,
    WatchProgress,
    get_session,
    init_db,
)
from tk_orchestrator.scheduler import polling
from tk_orchestrator.scheduler.polling import (
    _find_new_videos,
    _run_retention_if_needed,
    _select_retention_candidates,
    _total_video_count,
    _watched_video_count,
    _watched_ratio,
)
from tk_orchestrator.video_retention import delete_video_and_files


@pytest.fixture
def tmp_env(tmp_path):
    db_path = tmp_path / "test.db"
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    config = Config(
        db_path=db_path,
        output_dir=output_dir,
        max_videos_total=200,
        max_videos_per_channel=20,
        retention_enabled=True,
        retention_watched_ratio_threshold=0.5,
        retention_delete_batch_size=10,
        retention_keep_newest_per_channel=2,
        retention_min_age_hours=0,
    )
    init_db(config)
    return config, output_dir


def _make_channel(s, username="testuser", idx=1):
    ch = Channel(
        id=idx,
        username=username,
        url=f"https://www.tiktok.com/@{username}",
        is_active=True,
    )
    s.add(ch)
    s.flush()
    return ch


def _make_video(s, video_id, channel, discovered_at=None):
    v = Video(
        id=video_id,
        channel_id=channel.id,
        url=f"https://www.tiktok.com/@{channel.username}/video/{video_id}",
    )
    if discovered_at:
        v.discovered_at = discovered_at
    s.add(v)
    s.flush()
    return v


def _make_job(s, video_id, status="completed"):
    j = Job(video_id=video_id, status=status)
    s.add(j)
    s.flush()
    return j


def _make_watch_progress(s, video_id, seen=False, loop_count=0, updated_at=None):
    wp = WatchProgress(
        video_id=video_id,
        seen=seen,
        loop_count=loop_count,
        play_percentage=0,
    )
    if updated_at:
        wp.updated_at = updated_at
    s.add(wp)
    s.flush()
    return wp


class TestRetentionConfig:
    def test_defaults(self):
        c = Config()
        assert c.retention_enabled is True
        assert c.retention_watched_ratio_threshold == 0.5
        assert c.retention_delete_batch_size == 10
        assert c.retention_keep_newest_per_channel == 2
        assert c.retention_min_age_hours == 24


class TestDeleteVideoAndFiles:
    def test_removes_db_row_and_directory(self, tmp_env):
        config, output_dir = tmp_env
        with get_session() as s:
            ch = _make_channel(s)
            v = _make_video(s, "100", ch)
            _make_job(s, "100")
            _make_watch_progress(s, "100", seen=True)
            channel_username = ch.username

        video_dir = output_dir / channel_username / "100"
        video_dir.mkdir(parents=True)
        (video_dir / "video.mp4").write_text("fake")

        assert delete_video_and_files("100", output_dir)
        assert not video_dir.exists()
        with get_session() as s:
            assert s.get(Video, "100") is None
            deleted = s.get(DeletedVideo, "100")
            assert deleted is not None
            assert deleted.channel_username == channel_username

    def test_returns_false_for_missing(self, tmp_env):
        config, output_dir = tmp_env
        assert delete_video_and_files("nonexistent", output_dir) is False

    async def test_poll_scanner_skips_deleted_video_ids(self, tmp_env, monkeypatch):
        config, output_dir = tmp_env
        config.videos_per_poll = 1
        with get_session() as s:
            ch = _make_channel(s)
            _make_video(s, "100", ch)

        assert delete_video_and_files("100", output_dir)

        async def fake_channel_checker(channel_url, count):
            return [
                {"id": "100", "url": "https://example.test/deleted"},
                {"id": "101", "url": "https://example.test/new"},
            ]

        monkeypatch.setattr(
            polling, "_run_channel_checker_count", fake_channel_checker
        )

        videos = await _find_new_videos("https://example.test/@testuser", config)

        assert [video["id"] for video in videos] == ["101"]


class TestRetentionMetrics:
    def test_watched_count_uses_seen_or_loop(self, tmp_env):
        config, output_dir = tmp_env
        with get_session() as s:
            ch = _make_channel(s)
            for i, (seen, loops) in enumerate(
                [(True, 0), (False, 1), (False, 0), (True, 2)], start=1
            ):
                _make_video(s, str(i), ch)
                _make_watch_progress(s, str(i), seen=seen, loop_count=loops)

        assert _watched_video_count() == 3
        assert _total_video_count() == 4

    def test_watched_ratio_zero_when_empty(self, tmp_env):
        config, output_dir = tmp_env
        assert _watched_ratio() == 0.0


class TestSelectRetentionCandidates:
    def test_excludes_unwatched(self, tmp_env):
        config, output_dir = tmp_env
        with get_session() as s:
            ch = _make_channel(s)
            for i in range(1, 6):
                _make_video(s, str(i), ch)
                _make_job(s, str(i))
            _make_watch_progress(s, "1", seen=True)
            _make_watch_progress(s, "2", loop_count=1)
            _make_watch_progress(s, "3", seen=False, loop_count=0)
            _make_watch_progress(s, "4", seen=False, loop_count=0)
            _make_watch_progress(s, "5", seen=True)

        candidates = _select_retention_candidates(config, 10)
        assert "3" not in candidates
        assert "4" not in candidates

    def test_protects_newest_per_channel(self, tmp_env):
        config, output_dir = tmp_env
        config.retention_keep_newest_per_channel = 2
        with get_session() as s:
            ch = _make_channel(s)
            for i in range(1, 6):
                discovered = datetime.now(timezone.utc) - timedelta(hours=i)
                _make_video(s, str(i), ch, discovered_at=discovered)
                _make_job(s, str(i))
                _make_watch_progress(s, str(i), seen=True)

        candidates = _select_retention_candidates(config, 10)
        assert "1" not in candidates
        assert "2" not in candidates
        assert "3" in candidates
        assert "4" in candidates
        assert "5" in candidates

    def test_excludes_non_completed_jobs(self, tmp_env):
        config, output_dir = tmp_env
        config.retention_keep_newest_per_channel = 0
        config.retention_min_age_hours = 0
        with get_session() as s:
            ch = _make_channel(s)
            _make_video(s, "10", ch)
            _make_job(s, "10", status="pending")
            _make_watch_progress(s, "10", seen=True)
            _make_video(s, "11", ch)
            _make_job(s, "11", status="completed")
            _make_watch_progress(s, "11", seen=True)

        candidates = _select_retention_candidates(config, 10)
        assert "10" not in candidates
        assert "11" in candidates

    def test_respects_min_age(self, tmp_env):
        config, output_dir = tmp_env
        config.retention_keep_newest_per_channel = 0
        config.retention_min_age_hours = 24
        with get_session() as s:
            ch = _make_channel(s)
            recent = datetime.now(timezone.utc) - timedelta(hours=1)
            old = datetime.now(timezone.utc) - timedelta(hours=48)
            _make_video(s, "20", ch, discovered_at=recent)
            _make_job(s, "20")
            _make_watch_progress(s, "20", seen=True)
            _make_video(s, "21", ch, discovered_at=old)
            _make_job(s, "21")
            _make_watch_progress(s, "21", seen=True)

        candidates = _select_retention_candidates(config, 10)
        assert "20" not in candidates
        assert "21" in candidates

    def test_orders_by_loop_count_then_updated_at_then_discovered(self, tmp_env):
        config, output_dir = tmp_env
        config.retention_keep_newest_per_channel = 0
        config.retention_min_age_hours = 0
        now = datetime.now(timezone.utc)
        with get_session() as s:
            ch = _make_channel(s)
            _make_video(s, "30", ch, discovered_at=now - timedelta(hours=3))
            _make_job(s, "30")
            _make_watch_progress(
                s, "30", seen=True, loop_count=5, updated_at=now - timedelta(hours=1)
            )

            _make_video(s, "31", ch, discovered_at=now - timedelta(hours=1))
            _make_job(s, "31")
            _make_watch_progress(
                s, "31", seen=True, loop_count=1, updated_at=now - timedelta(hours=2)
            )

            _make_video(s, "32", ch, discovered_at=now - timedelta(hours=2))
            _make_job(s, "32")
            _make_watch_progress(
                s, "32", seen=True, loop_count=5, updated_at=now - timedelta(hours=3)
            )

        candidates = _select_retention_candidates(config, 10)
        assert candidates[0] == "32"
        assert candidates[1] == "30"
        assert candidates[2] == "31"

    def test_deduplicates_videos_with_multiple_completed_jobs(self, tmp_env):
        config, output_dir = tmp_env
        config.retention_keep_newest_per_channel = 0
        config.retention_min_age_hours = 0
        with get_session() as s:
            ch = _make_channel(s)
            _make_video(s, "40", ch)
            _make_job(s, "40", status="completed")
            _make_job(s, "40", status="completed")
            _make_watch_progress(s, "40", seen=True)

        candidates = _select_retention_candidates(config, 10)
        assert candidates.count("40") == 1


class TestRunRetentionIfNeeded:
    def test_no_retention_when_ratio_below_threshold(self, tmp_env):
        config, output_dir = tmp_env
        with get_session() as s:
            ch = _make_channel(s)
            for i in range(1, 11):
                _make_video(s, str(i), ch)
                _make_job(s, str(i))
            for i in range(1, 5):
                _make_watch_progress(s, str(i), seen=True)

        deleted = _run_retention_if_needed(config)
        assert deleted == 0
        assert _total_video_count() == 10

    def test_retention_triggers_at_threshold(self, tmp_env):
        config, output_dir = tmp_env
        config.retention_keep_newest_per_channel = 0
        config.retention_min_age_hours = 0
        with get_session() as s:
            ch = _make_channel(s)
            for i in range(1, 11):
                _make_video(s, str(i), ch)
                _make_job(s, str(i))
            for i in range(1, 6):
                _make_watch_progress(s, str(i), seen=True)

        deleted = _run_retention_if_needed(config)
        assert deleted == 5
        assert _total_video_count() == 5

    def test_disabled_retention(self, tmp_env):
        config, output_dir = tmp_env
        config.retention_enabled = False
        with get_session() as s:
            ch = _make_channel(s)
            for i in range(1, 11):
                _make_video(s, str(i), ch)
                _make_job(s, str(i))
                _make_watch_progress(s, str(i), seen=True)

        deleted = _run_retention_if_needed(config)
        assert deleted == 0

    def test_only_watched_videos_deleted(self, tmp_env):
        config, output_dir = tmp_env
        config.retention_keep_newest_per_channel = 0
        config.retention_min_age_hours = 0
        with get_session() as s:
            ch = _make_channel(s)
            for i in range(1, 11):
                _make_video(s, str(i), ch)
                _make_job(s, str(i))
            for i in range(1, 11):
                if i <= 6:
                    _make_watch_progress(s, str(i), seen=True)
                else:
                    _make_watch_progress(s, str(i), seen=False, loop_count=0)

        deleted = _run_retention_if_needed(config)
        assert deleted == 6
        remaining = _total_video_count()
        assert remaining == 4
        with get_session() as s:
            for i in range(7, 11):
                assert s.get(Video, str(i)) is not None

    def test_deletes_filesystem_directory(self, tmp_env):
        config, output_dir = tmp_env
        config.retention_keep_newest_per_channel = 0
        config.retention_min_age_hours = 0
        with get_session() as s:
            ch = _make_channel(s)
            channel_username = ch.username
            for i in range(1, 4):
                _make_video(s, str(i), ch)
                _make_job(s, str(i))
                _make_watch_progress(s, str(i), seen=True)
                vd = output_dir / channel_username / str(i)
                vd.mkdir(parents=True)
                (vd / "video.mp4").write_text("fake")

        _run_retention_if_needed(config)
        for i in range(1, 4):
            assert not (output_dir / channel_username / str(i)).exists()
