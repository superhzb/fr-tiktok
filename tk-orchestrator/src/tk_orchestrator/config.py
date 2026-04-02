from __future__ import annotations

import dataclasses
import os
from pathlib import Path
from typing import Any

import yaml

_DEFAULT_CONFIG_PATHS = [
    Path("./config.yaml"),
    Path("~/.config/tk-orchestrator/config.yaml").expanduser(),
]

_ENV_MAP: dict[str, tuple[str, type]] = {
    "TK_POLL_INTERVAL_SECONDS": ("poll_interval_seconds", int),
    "TK_OUTPUT_DIR": ("output_dir", Path),
    "TK_VIDEO_COUNT": ("video_count", int),
    "TK_CHANNEL_FETCH_LIMIT": ("channel_fetch_limit", int),
    "TK_CHANNEL_SCAN_LIMIT": ("channel_scan_limit", int),
    "TK_COMMENT_COUNT": ("comment_count", int),
    "TK_STT_MODEL": ("stt_model", str),
    "TK_ALIGNER_MODEL": ("aligner_model", str),
    "TK_TRANSLATE_MODEL": ("translate_model", str),
    "TK_TRANSLATE_BATCH_SIZE": ("translate_batch_size", int),
    "TK_DB_PATH": ("db_path", Path),
}


@dataclasses.dataclass
class Config:
    poll_interval_seconds: int = 60
    output_dir: Path = dataclasses.field(
        default_factory=lambda: Path("./output")
    )
    video_count: int = 1
    channel_fetch_limit: int = 20
    channel_scan_limit: int = 200
    comment_count: int = 10
    stt_model: str = "mlx-community/whisper-large-v3-asr-4bit"
    aligner_model: str = "mlx-community/Qwen3-ForcedAligner-0.6B-8bit"
    translate_model: str = "mlx-community/Qwen3-4B-Instruct-2507-4bit"
    translate_batch_size: int = 10
    db_path: Path = dataclasses.field(
        default_factory=lambda: Path("./tk_orchestrator.db").resolve()
    )

    def __post_init__(self) -> None:
        if isinstance(self.output_dir, str):
            self.output_dir = Path(self.output_dir).expanduser()
        if isinstance(self.db_path, str):
            self.db_path = Path(self.db_path).expanduser()


def load_config(path: Path | None = None) -> Config:
    """Load config from YAML file with environment variable overrides."""
    data: dict[str, Any] = {}
    base_dir = Path.cwd()

    if path is None:
        env_path = os.environ.get("TK_CONFIG_FILE")
        if env_path:
            path = Path(env_path)
        else:
            for p in _DEFAULT_CONFIG_PATHS:
                if p.exists():
                    path = p
                    break

    if path is not None:
        path = path.expanduser()
        base_dir = path.parent.resolve()

    if path is not None and path.exists():
        with path.open() as f:
            data = yaml.safe_load(f) or {}

    for env_key, (field_name, cast) in _ENV_MAP.items():
        val = os.environ.get(env_key)
        if val is not None:
            data[field_name] = cast(val)

    for key in ("output_dir", "db_path"):
        value = data.get(key)
        if isinstance(value, str):
            candidate = Path(value).expanduser()
            if not candidate.is_absolute():
                data[key] = base_dir / candidate

    known = {f.name for f in dataclasses.fields(Config)}
    return Config(**{k: v for k, v in data.items() if k in known})
