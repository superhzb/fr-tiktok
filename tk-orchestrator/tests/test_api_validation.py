import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from tk_orchestrator.api import app, register_scheduler
from tk_orchestrator.config import Config
from tk_orchestrator.db import Channel, Job, Video, get_session, init_db


def _seed_database() -> None:
    with get_session() as session:
        channel = Channel(username="creator.test", url="https://www.tiktok.com/@creator.test")
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
        register_scheduler(None)
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

    def test_health_reports_database_and_scheduler_state(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "status": "ok",
                "service": "tk-orchestrator",
                "database": {"status": "ok"},
                "scheduler": {
                    "status": "not_configured",
                    "running": False,
                    "jobs": 0,
                },
            },
        )


if __name__ == "__main__":
    unittest.main()
