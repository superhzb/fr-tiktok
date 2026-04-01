"""Core alignment logic: forced audio-text alignment via mlx-audio Qwen3-ForcedAligner."""

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_MODEL_ID = "mlx-community/Qwen3-ForcedAligner-0.6B-8bit"

# miniaudio (used internally by mlx-audio) only handles plain audio containers
_AUDIO_EXTS = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac", ".opus"}


def _to_wav(input_path: Path, tmp_dir: str) -> Path:
    """Convert any audio/video file to 16 kHz mono WAV via ffmpeg."""
    out = Path(tmp_dir) / "audio.wav"
    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-vn",
        "-ar", "16000",
        "-ac", "1",
        "-f", "wav",
        str(out),
    ]
    logger.debug("ffmpeg cmd: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.debug("ffmpeg stderr:\n%s", result.stderr)
        raise RuntimeError(f"ffmpeg failed (exit {result.returncode}): {result.stderr[-300:]}")
    logger.debug("ffmpeg finished → %s", out)
    return out


def align(
    audio_path: str | Path,
    text: str,
    model_id: str = DEFAULT_MODEL_ID,
) -> list[dict]:
    """Align text to audio and return word-level timing segments.

    Args:
        audio_path: Path to the audio or video file.
        text: Transcription text to align.
        model_id: mlx-community forced aligner model to use.

    Returns:
        List of dicts with keys ``start``, ``end``, ``text``.
    """
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(audio_path)

    text = text.strip()
    if not text:
        raise ValueError("text must not be empty")

    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found on PATH – install with: brew install ffmpeg")

    logger.info("Loading aligner model: %s", model_id)
    from mlx_audio.stt import load  # lazy import — model is large

    model = load(model_id)
    logger.debug("Model loaded.")

    with tempfile.TemporaryDirectory() as tmp:
        wav = _to_wav(audio_path, tmp)
        logger.info("Aligning %s …", audio_path.name)
        result = model.generate(audio=str(wav), text=text)

    logger.debug("Alignment returned %d segments.", len(result))

    segments = [
        {"start": item.start_time, "end": item.end_time, "text": item.text}
        for item in result
    ]
    return segments
