import asyncio
import logging
import tempfile
import unittest
from pathlib import Path

from tk_orchestrator.mlx import is_mlx_command, mlx_job_guard


class MlxQueueTests(unittest.IsolatedAsyncioTestCase):
    async def test_mlx_commands_are_serialized(self) -> None:
        logger = logging.getLogger("tk_orchestrator.tests.mlx_queue")
        entered_first = asyncio.Event()
        order: list[str] = []

        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / "mlx.lock"

            async def first() -> None:
                async with mlx_job_guard(["tk-stt"], logger, lock_path=lock_path):
                    order.append("first-enter")
                    entered_first.set()
                    await asyncio.sleep(0.1)
                    order.append("first-exit")

            async def second() -> None:
                await entered_first.wait()
                async with mlx_job_guard(
                    ["tk-batch-translate"], logger, lock_path=lock_path
                ):
                    order.append("second-enter")
                    order.append("second-exit")

            await asyncio.gather(first(), second())

        self.assertEqual(
            order,
            ["first-enter", "first-exit", "second-enter", "second-exit"],
        )

    async def test_non_mlx_commands_skip_queue(self) -> None:
        logger = logging.getLogger("tk_orchestrator.tests.mlx_queue")
        order: list[str] = []

        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / "mlx.lock"

            async def first() -> None:
                async with mlx_job_guard(["tk-stt"], logger, lock_path=lock_path):
                    order.append("mlx-enter")
                    await asyncio.sleep(0.1)
                    order.append("mlx-exit")

            async def second() -> None:
                await asyncio.sleep(0.01)
                async with mlx_job_guard(["tk-comments"], logger, lock_path=lock_path):
                    order.append("non-mlx-enter")
                    order.append("non-mlx-exit")

            await asyncio.gather(first(), second())

        self.assertEqual(order[:3], ["mlx-enter", "non-mlx-enter", "non-mlx-exit"])
        self.assertEqual(order[-1], "mlx-exit")

    def test_mlx_command_detection(self) -> None:
        self.assertTrue(is_mlx_command(["tk-stt"]))
        self.assertTrue(is_mlx_command(["tk-aligner"]))
        self.assertTrue(is_mlx_command(["tk-batch-translate", "comments"]))
        self.assertFalse(is_mlx_command(["tk-comments"]))
        self.assertFalse(is_mlx_command([]))
