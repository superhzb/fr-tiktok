"""Core STT logic: ffmpeg conversion + mlx-audio Whisper inference."""

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "mlx-community/whisper-large-v3-asr-4bit"

# Extensions treated as audio-only (no video stream to strip)
_AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac", ".opus"}


def _to_wav(input_path: Path, tmp_dir: str) -> Path:
    """Convert any audio/video file to a 16 kHz mono WAV via ffmpeg."""
    out = Path(tmp_dir) / "audio.wav"
    cmd = [
        "ffmpeg",
        "-y",           # overwrite without asking
        "-i", str(input_path),
        "-vn",          # drop video stream
        "-ar", "16000", # 16 kHz – Whisper's native rate
        "-ac", "1",     # mono
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


def transcribe(
    input_path: str | Path,
    model_id: str = _DEFAULT_MODEL,
) -> str:
    """Transcribe an audio or video file and return the plain text.

    Parameters
    ----------
    input_path:
        Path to an audio or video file.  Any format understood by ffmpeg is
        accepted (mp4, mov, mp3, wav, m4a, …).
    model_id:
        mlx-community Whisper model to use.

    Returns
    -------
    str
        Transcribed text.
    """
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(input_path)

    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found on PATH – install it with: brew install ffmpeg")

    logger.info("Loading STT model: %s", model_id)
    from mlx_audio.stt import load  # lazy import – model is large

    model = load(model_id)
    logger.debug("Model loaded.")

    with tempfile.TemporaryDirectory() as tmp:
        wav = _to_wav(input_path, tmp)
        logger.info("Running transcription on %s …", input_path.name)
        result = model.generate(str(wav))
        text = result.text
        logger.debug("Raw result: %r", text)

    return text
