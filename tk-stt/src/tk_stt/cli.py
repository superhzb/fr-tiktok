"""CLI entry point: tk-stt <input> [options]"""

import json
import logging
import sys
from pathlib import Path

import click

from .stt import transcribe, _DEFAULT_MODEL


def _configure_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        level=level,
        stream=sys.stderr,
    )
    if not debug:
        for noisy in ("httpx", "httpcore", "urllib3"):
            logging.getLogger(noisy).setLevel(logging.WARNING)


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--model",
    "-m",
    default=_DEFAULT_MODEL,
    show_default=True,
    metavar="MODEL_ID",
    help="mlx-community Whisper model to use.",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default=None,
    metavar="FILE",
    help="Write JSON output to FILE instead of stdout.",
)
@click.option("--debug", is_flag=True, help="Enable verbose debug logging.")
def main(input_file: Path, model: str, output: Path | None, debug: bool) -> None:
    """Transcribe an audio or video file to text.

    Accepts any format ffmpeg can read (mp4, mov, mp3, wav, m4a, …).
    Outputs JSON: {\"text\": \"...\"}

    Examples:

    \b
        tk-stt video.mp4
        tk-stt audio.mp3 --output result.json
        tk-stt video.mp4 --debug
    """
    _configure_logging(debug)
    logger = logging.getLogger(__name__)

    try:
        text = transcribe(input_file, model_id=model)
    except FileNotFoundError as exc:
        logger.error("File not found: %s", exc)
        sys.exit(1)
    except RuntimeError as exc:
        logger.error("%s", exc)
        sys.exit(1)
    except Exception as exc:
        logger.exception("Unexpected error: %s", exc)
        sys.exit(1)

    payload = json.dumps({"text": text}, ensure_ascii=False, indent=2)

    if output:
        output.write_text(payload, encoding="utf-8")
        logger.info("Saved to %s", output)
    else:
        print(payload)
