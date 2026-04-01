"""tk-aligner: Forced audio-text alignment library using mlx-audio Qwen3-ForcedAligner."""

from .aligner import DEFAULT_MODEL_ID, align

__all__ = ["align", "DEFAULT_MODEL_ID"]
