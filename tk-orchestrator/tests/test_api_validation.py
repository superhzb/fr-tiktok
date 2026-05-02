import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from tk_orchestrator.api import app
from tk_orchestrator.config import Config
from tk_orchestrator.models import Channel, Job, Video, get_session, init_db


def _seed_database() -> None:
    with get_session() as session:
        channel = Channel(
            username="creator.test", url="https://www.tiktok.com/@creator.test"
        )
        session.add(channel)
        session.flush()
        session.add(
            Video(
                id="7351234567890123456",
                channel_id=channel.id,
                url="https://www.tiktok.com/@creator.test/video/7351234567890123456",
                author="creator.test",
            )
        )
        session.add(Job(video_id="7351234567890123456", status="completed"))


class ApiValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        temp_path = Path(self.temp_dir.name)
        init_db(Config(db_path=temp_path / "test.db", output_dir=temp_path / "output"))
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_invalid_video_id_is_rejected(self) -> None:
        response = self.client.get("/videos/not-a-video-id")

        self.assertEqual(response.status_code, 422)

    def test_invalid_status_query_is_rejected(self) -> None:
        response = self.client.get("/videos", params={"status": "done"})

        self.assertEqual(response.status_code, 422)

    def test_videos_query_accepts_normalized_channel_filter(self) -> None:
        _seed_database()

        response = self.client.get(
            "/videos",
            params={"channel": "@creator.test", "status": "completed"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]["id"], "7351234567890123456")

    def test_health_reports_database_state(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "status": "ok",
                "service": "tk-orchestrator",
                "database": {"status": "ok"},
            },
        )

    def test_feed_orders_unwatched_videos_oldest_first(self) -> None:
        now = datetime.now(timezone.utc)
        with get_session() as session:
            channel = Channel(
                username="feed.test", url="https://www.tiktok.com/@feed.test"
            )
            session.add(channel)
            session.flush()

            old_video = Video(
                id="7351234567890123401",
                channel_id=channel.id,
                url="https://www.tiktok.com/@feed.test/video/7351234567890123401",
                author="feed.test",
                discovered_at=now - timedelta(days=2),
            )
            new_video = Video(
                id="7351234567890123402",
                channel_id=channel.id,
                url="https://www.tiktok.com/@feed.test/video/7351234567890123402",
                author="feed.test",
                discovered_at=now - timedelta(days=1),
            )
            session.add_all([new_video, old_video])
            session.add_all(
                [
                    Job(video_id=old_video.id, status="completed"),
                    Job(video_id=new_video.id, status="completed"),
                ]
            )

        response = self.client.get("/feed")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [video["id"] for video in response.json()],
            ["7351234567890123401", "7351234567890123402"],
        )


if __name__ == "__main__":
    unittest.main()
