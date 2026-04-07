import os
import tempfile
import unittest
from pathlib import Path

from tk_orchestrator.cli import _seed_default_channels
from tk_orchestrator.config import Config, load_config
from tk_orchestrator.db import Channel, get_session, init_db


class ConfigDiscoveryTests(unittest.TestCase):
    def test_load_config_reads_default_channels(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "poll_interval_seconds: 15",
                        "default_channels:",
                        '  - "@creator.test"',
                        '  - "https://www.tiktok.com/@bonjour.lemonde"',
                    ]
                ),
                encoding="utf-8",
            )

            config = load_config(config_path)

            self.assertEqual(config.poll_interval_seconds, 15)
            self.assertEqual(
                config.default_channels,
                ["@creator.test", "https://www.tiktok.com/@bonjour.lemonde"],
            )

    def test_load_config_finds_workspace_config_when_run_from_repo_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_dir = temp_path / "tk-orchestrator"
            config_dir.mkdir()
            (config_dir / "config.yaml").write_text(
                "\n".join(
                    [
                        "poll_interval_seconds: 7",
                        "default_channels:",
                        '  - "@creator.test"',
                    ]
                ),
                encoding="utf-8",
            )
            original_cwd = Path.cwd()
            try:
                os.chdir(temp_path)
                config = load_config()
            finally:
                os.chdir(original_cwd)

            self.assertEqual(config.poll_interval_seconds, 7)
            self.assertEqual(config.default_channels, ["@creator.test"])


class DefaultChannelSeedingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        temp_path = Path(self.temp_dir.name)
        self.config = Config(
            db_path=temp_path / "test.db",
            output_dir=temp_path / "output",
            default_channels=[
                "@creator.test",
                "https://www.tiktok.com/@bonjour.lemonde",
            ],
        )
        init_db(self.config)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_seed_default_channels_is_idempotent(self) -> None:
        first_seed_count = _seed_default_channels(self.config)
        second_seed_count = _seed_default_channels(self.config)

        self.assertEqual(first_seed_count, 2)
        self.assertEqual(second_seed_count, 0)
        with get_session() as session:
            channels = session.query(Channel).order_by(Channel.username.asc()).all()
            usernames = [channel.username for channel in channels]
            urls = [channel.url for channel in channels]

        self.assertEqual(usernames, ["bonjour.lemonde", "creator.test"])
        self.assertEqual(
            urls,
            [
                "https://www.tiktok.com/@bonjour.lemonde",
                "https://www.tiktok.com/@creator.test",
            ],
        )


if __name__ == "__main__":
    unittest.main()
