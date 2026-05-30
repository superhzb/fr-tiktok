"""Logging contract tests for tk-batch-translate.

Verifies:
- stdout is clean (no log leakage) on success
- logs go to stderr, not stdout
- error logs include 'service' field
- TK_JOB_ID / TK_VIDEO_ID / TK_PIPELINE_STEP appear in logs when set
"""

import json
import logging
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from tk_batch_translate.cli import main

SERVICE = "tk-batch-translate"


@pytest.fixture(autouse=True)
def reset_logging():
    yield
    root = logging.getLogger()
    root.handlers.clear()


def test_srt_success_stdout_is_empty(tmp_path):
    """The srt subcommand writes to a file; stdout must be empty."""
    srt_file = tmp_path / "subtitles.srt"
    srt_file.write_text("1\n00:00:00,000 --> 00:00:01,000\nBonjour\n", encoding="utf-8")
    out_file = tmp_path / "out.vtt"
    with patch("tk_batch_translate.srt.translator.translate_srt"):
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["srt", str(srt_file), "--output", str(out_file), "--format", "vtt"],
        )
    assert result.exit_code == 0
    assert result.stdout.strip() == ""


def test_srt_logs_do_not_leak_to_stdout(tmp_path):
    srt_file = tmp_path / "subtitles.srt"
    srt_file.write_text("1\n00:00:00,000 --> 00:00:01,000\nBonjour\n", encoding="utf-8")
    out_file = tmp_path / "out.vtt"
    with patch("tk_batch_translate.srt.translator.translate_srt"):
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["srt", str(srt_file), "--output", str(out_file), "--format", "vtt", "-v"],
        )
    assert result.exit_code == 0
    assert result.stdout.strip() == ""


def test_srt_error_log_has_service(tmp_path):
    srt_file = tmp_path / "subtitles.srt"
    srt_file.write_text("1\n00:00:00,000 --> 00:00:01,000\nBonjour\n", encoding="utf-8")
    out_file = tmp_path / "out.vtt"
    with patch(
        "tk_batch_translate.srt.translator.translate_srt",
        side_effect=RuntimeError("model failed"),
    ):
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["srt", str(srt_file), "--output", str(out_file), "--format", "vtt", "-v"],
        )
    assert result.exit_code == 1
    entries = [
        json.loads(line)
        for line in result.stderr.splitlines()
        if line.strip()
    ]
    error_logs = [e for e in entries if e.get("level") == "ERROR"]
    assert error_logs, "Expected at least one ERROR entry on stderr"
    for entry in error_logs:
        assert entry["service"] == SERVICE


def test_orchestrator_context_appears_in_error_logs(tmp_path, monkeypatch):
    monkeypatch.setenv("TK_JOB_ID", "3")
    monkeypatch.setenv("TK_VIDEO_ID", "def456")
    monkeypatch.setenv("TK_PIPELINE_STEP", "translation")

    srt_file = tmp_path / "subtitles.srt"
    srt_file.write_text("1\n00:00:00,000 --> 00:00:01,000\nBonjour\n", encoding="utf-8")
    out_file = tmp_path / "out.vtt"
    with patch(
        "tk_batch_translate.srt.translator.translate_srt",
        side_effect=RuntimeError("boom"),
    ):
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["srt", str(srt_file), "--output", str(out_file), "--format", "vtt", "-v"],
        )
    assert result.exit_code == 1
    entries = [
        json.loads(line)
        for line in result.stderr.splitlines()
        if line.strip()
    ]
    error_logs = [e for e in entries if e.get("level") == "ERROR"]
    assert error_logs
    for entry in error_logs:
        assert entry.get("job_id") == "3"
        assert entry.get("video_id") == "def456"
        assert entry.get("pipeline_step") == "translation"
