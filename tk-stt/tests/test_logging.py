"""Logging contract tests for tk-stt.

Verifies:
- stdout contains only machine-readable JSON on success
- logs go to stderr, not stdout
- error logs include 'service' field
- TK_JOB_ID / TK_VIDEO_ID / TK_PIPELINE_STEP appear in logs when set
"""

import json
import logging
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from tk_stt.cli import main

SERVICE = "tk-stt"


@pytest.fixture(autouse=True)
def reset_logging():
    yield
    root = logging.getLogger()
    root.handlers.clear()


def test_stdout_is_valid_json_on_success(tmp_path):
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"fake")
    with patch("tk_stt.cli.transcribe", return_value="bonjour monde"):
        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(main, [str(audio)])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data == {"text": "bonjour monde"}


def test_logs_do_not_leak_to_stdout(tmp_path):
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"fake")
    with patch("tk_stt.cli.transcribe", return_value="hello"):
        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(main, [str(audio), "--debug"])
    assert result.exit_code == 0
    # stdout must be parseable JSON with no extra lines
    json.loads(result.output)


def test_error_log_is_json_with_service(tmp_path):
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"fake")
    with patch("tk_stt.cli.transcribe", side_effect=RuntimeError("model failed")):
        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(main, [str(audio)])
    assert result.exit_code == 1
    error_entries = [
        json.loads(line)
        for line in result.stderr.splitlines()
        if line.strip()
    ]
    error_logs = [e for e in error_entries if e.get("level") == "ERROR"]
    assert error_logs, "Expected at least one ERROR entry on stderr"
    for entry in error_logs:
        assert entry["service"] == SERVICE


def test_orchestrator_context_appears_in_error_logs(tmp_path, monkeypatch):
    monkeypatch.setenv("TK_JOB_ID", "99")
    monkeypatch.setenv("TK_VIDEO_ID", "vid123")
    monkeypatch.setenv("TK_PIPELINE_STEP", "stt")

    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"fake")
    with patch("tk_stt.cli.transcribe", side_effect=RuntimeError("boom")):
        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(main, [str(audio)])
    assert result.exit_code == 1
    entries = [
        json.loads(line)
        for line in result.stderr.splitlines()
        if line.strip()
    ]
    error_logs = [e for e in entries if e.get("level") == "ERROR"]
    assert error_logs
    for entry in error_logs:
        assert entry.get("job_id") == "99"
        assert entry.get("video_id") == "vid123"
        assert entry.get("pipeline_step") == "stt"
