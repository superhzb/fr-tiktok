"""
Stage pipeline test.

Run from any pipeline step using saved fixtures:

    pytest tests/test_pipeline.py --from-step translation
    pytest tests/test_pipeline.py --from-step alignment
    pytest tests/test_pipeline.py --from-step punctuation
    pytest tests/test_pipeline.py --from-step stt
    pytest tests/test_pipeline.py --from-step download

Without --from-step it runs all steps from the beginning using the video fixture.
"""
import json
import subprocess
import pytest
from pathlib import Path

from conftest import (
    FIXTURE_DIR, OUTPUT_DIR, PIPELINE_STEPS,
    TEST_VIDEO_ID, TEST_VIDEO_URL,
)


# ---------------------------------------------------------------------------
# State passed between steps within a single test run.
# Each step function reads inputs from here and writes its output path here.
# ---------------------------------------------------------------------------
class PipelineState:
    def __init__(self, fixture_dir: Path, output_dir: Path):
        self.fixture_dir = fixture_dir
        self.output_dir  = output_dir
        # These are populated as steps run
        self.video_path       : Path | None = None
        self.raw_json_path    : Path | None = None
        self.punctuated_path  : Path | None = None
        self.aligned_path     : Path | None = None
        self.srt_path         : Path | None = None
        self.vtt_path         : Path | None = None

    def load_fixture(self, filename: str) -> Path:
        """Return the fixture path and assert it exists."""
        path = self.fixture_dir / filename
        assert path.exists(), (
            f"Fixture not found: {path}\n"
            "Run test_pipeline_e2e.py first to generate fixtures."
        )
        return path


# ---------------------------------------------------------------------------
# One function per pipeline step.
# Each receives the shared PipelineState and updates it with its output.
# ---------------------------------------------------------------------------

def step_download(state: PipelineState, config):
    result = subprocess.run(
        ["tk-down", TEST_VIDEO_URL, "--output-dir", str(state.output_dir)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"tk-down failed:\n{result.stderr}"
    # tk-down prints the saved file path to stdout
    saved_path = Path(result.stdout.strip())
    assert saved_path.exists() and saved_path.stat().st_size > 0
    state.video_path = saved_path


def step_stt(state: PipelineState, config):
    # If download was skipped, load video from fixtures
    if state.video_path is None:
        state.video_path = state.load_fixture("video.mp4")
    output = state.output_dir / "raw_transcription.json"
    result = subprocess.run(
        ["tk-stt", str(state.video_path), "--output", str(output), "--model", config.stt_model],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"tk-stt failed:\n{result.stderr}"
    assert output.exists() and output.stat().st_size > 0
    data = json.loads(output.read_text())
    assert "text" in data and len(data["text"].strip()) > 0, "STT output missing text."
    state.raw_json_path = output


def step_punctuation(state: PipelineState, config):
    if state.raw_json_path is None:
        state.raw_json_path = state.load_fixture("raw_transcription.json")
    result = subprocess.run(
        ["tk-punctuation", "--input-file", str(state.raw_json_path)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"tk-punctuation failed:\n{result.stderr}"
    output = state.output_dir / "punctuated.json"
    output.write_text(result.stdout)
    data = json.loads(result.stdout)
    assert "text" in data and len(data["text"].strip()) > 0, "Punctuation output missing text."
    state.punctuated_path = output


def step_alignment(state: PipelineState, config):
    if state.video_path is None:
        state.video_path = state.load_fixture("video.mp4")
    if state.punctuated_path is None:
        state.punctuated_path = state.load_fixture("punctuated.json")
    output = state.output_dir / "aligned.json"
    result = subprocess.run(
        [
            "tk-aligner", str(state.video_path), str(state.punctuated_path),
            "--output", str(output),
            "--model", config.aligner_model,
        ],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"tk-aligner failed:\n{result.stderr}"
    assert output.exists() and output.stat().st_size > 0
    segments = json.loads(output.read_text())
    assert isinstance(segments, list) and len(segments) > 0, "Alignment output is empty."
    state.aligned_path = output


def step_srt_merge(state: PipelineState, config):
    if state.aligned_path is None:
        state.aligned_path = state.load_fixture("aligned.json")
    if state.punctuated_path is None:
        state.punctuated_path = state.load_fixture("punctuated.json")
    output = state.output_dir / "subtitles.srt"
    result = subprocess.run(
        ["tk-srt-merger", str(state.aligned_path), str(state.punctuated_path), str(output)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"tk-srt-merger failed:\n{result.stderr}"
    assert output.exists() and output.stat().st_size > 0
    state.srt_path = output


def step_translation(state: PipelineState, config):
    if state.srt_path is None:
        state.srt_path = state.load_fixture("subtitles.srt")
    output = state.output_dir / "subtitles.vtt"
    result = subprocess.run(
        [
            "tk-batch-translate", "srt", str(state.srt_path),
            "--output", str(output),
            "--format", "vtt",
            "--model", config.translate_model,
            "--batch-size", str(config.translate_batch_size),
        ],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"tk-batch-translate failed:\n{result.stderr}"
    assert output.exists() and output.stat().st_size > 0
    content = output.read_text()
    assert content.startswith("WEBVTT"), "Output does not look like a valid VTT file."
    state.vtt_path = output


# Map step names to functions — order matters
STEP_FUNCTIONS = {
    "download"    : step_download,
    "stt"         : step_stt,
    "punctuation" : step_punctuation,
    "alignment"   : step_alignment,
    "srt_merge"   : step_srt_merge,
    "translation" : step_translation,
}


# ---------------------------------------------------------------------------
# The test
# ---------------------------------------------------------------------------

def test_pipeline_from_step(from_step, test_config):
    """
    Run pipeline from --from-step onward.
    If --from-step is not given, runs all steps from 'download'.
    """
    start = from_step or "download"
    start_index = PIPELINE_STEPS.index(start)
    steps_to_run = PIPELINE_STEPS[start_index:]

    state = PipelineState(fixture_dir=FIXTURE_DIR, output_dir=OUTPUT_DIR)

    for step_name in steps_to_run:
        print(f"\n→ Running step: {step_name}")
        STEP_FUNCTIONS[step_name](state, test_config)
        print(f"  ✓ {step_name} passed")
