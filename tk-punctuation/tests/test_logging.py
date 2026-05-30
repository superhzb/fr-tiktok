"""Logging contract tests for tk-punctuation.

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

from tk_punctuation.cli import main

SERVICE = "tk-punctuation"


@pytest.fixture(autouse=True)
def reset_logging():
    yield
    root = logging.getLogger()
    root.handlers.clear()


def test_stdout_is_valid_json_on_success(tmp_path):
    input_file = tmp_path / "input.json"
    input_file.write_text('{"text": "bonjour monde"}', encoding="utf-8")
    with patch("tk_punctuation.cli.punctuate_text", return_value="Bonjour monde."):
        runner = CliRunner()
        result = runner.invoke(main, ["--input-file", str(input_file)])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "text" in data


def test_logs_do_not_leak_to_stdout(tmp_path):
    input_file = tmp_path / "input.json"
    input_file.write_text('{"text": "hello"}', encoding="utf-8")
    with patch("tk_punctuation.cli.punctuate_text", return_value="Hello."):
        runner = CliRunner()
        result = runner.invoke(main, ["--input-file", str(input_file), "--debug"])
    assert result.exit_code == 0
    json.loads(result.stdout)


def test_invalid_json_error_log_has_service(tmp_path):
    input_file = tmp_path / "bad.json"
    input_file.write_text("not json", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(main, ["--input-file", str(input_file)])
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
    monkeypatch.setenv("TK_JOB_ID", "7")
    monkeypatch.setenv("TK_VIDEO_ID", "abc")
    monkeypatch.setenv("TK_PIPELINE_STEP", "punctuation")

    input_file = tmp_path / "bad.json"
    input_file.write_text("not json", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(main, ["--input-file", str(input_file)])
    assert result.exit_code == 1
    entries = [
        json.loads(line)
        for line in result.stderr.splitlines()
        if line.strip()
    ]
    error_logs = [e for e in entries if e.get("level") == "ERROR"]
    assert error_logs
    for entry in error_logs:
        assert entry.get("job_id") == "7"
        assert entry.get("video_id") == "abc"
        assert entry.get("pipeline_step") == "punctuation"
