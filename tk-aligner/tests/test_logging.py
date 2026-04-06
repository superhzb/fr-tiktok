"""Logging contract tests for tk-aligner.

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

from tk_aligner.cli import main

SERVICE = "tk-aligner"


@pytest.fixture(autouse=True)
def reset_logging():
    yield
    root = logging.getLogger()
    root.handlers.clear()


def test_stdout_is_valid_json_on_success(tmp_path):
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"fake")
    text_file = tmp_path / "text.json"
    text_file.write_text('{"text": "bonjour monde"}', encoding="utf-8")
    segments = [{"start": 0.0, "end": 0.5, "text": "bonjour"}]
    with patch("tk_aligner.cli.align", return_value=segments):
        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(main, [str(audio), str(text_file)])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert data[0]["text"] == "bonjour"


def test_logs_do_not_leak_to_stdout(tmp_path):
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"fake")
    text_file = tmp_path / "text.json"
    text_file.write_text('{"text": "hello"}', encoding="utf-8")
    with patch("tk_aligner.cli.align", return_value=[]):
        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(main, [str(audio), str(text_file), "--debug"])
    assert result.exit_code == 0
    json.loads(result.output)


def test_invalid_text_file_error_log_has_service(tmp_path):
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"fake")
    text_file = tmp_path / "bad.json"
    text_file.write_text("not json", encoding="utf-8")
    runner = CliRunner(mix_stderr=False)
    result = runner.invoke(main, [str(audio), str(text_file)])
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
    monkeypatch.setenv("TK_JOB_ID", "5")
    monkeypatch.setenv("TK_VIDEO_ID", "xyz")
    monkeypatch.setenv("TK_PIPELINE_STEP", "alignment")

    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"fake")
    text_file = tmp_path / "text.json"
    text_file.write_text('{"text": "hello"}', encoding="utf-8")
    with patch("tk_aligner.cli.align", side_effect=ValueError("bad alignment")):
        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(main, [str(audio), str(text_file)])
    assert result.exit_code == 1
    entries = [
        json.loads(line)
        for line in result.stderr.splitlines()
        if line.strip()
    ]
    error_logs = [e for e in entries if e.get("level") == "ERROR"]
    assert error_logs
    for entry in error_logs:
        assert entry.get("job_id") == "5"
        assert entry.get("video_id") == "xyz"
        assert entry.get("pipeline_step") == "alignment"
