"""CLI entry point for tk-aligner."""

import json
import logging
import sys
from pathlib import Path

import click

from .aligner import DEFAULT_MODEL_ID, align

logger = logging.getLogger(__name__)


def _configure_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        level=level,
        stream=sys.stderr,
    )
    if not debug:
        for noisy in ("mlx", "mlx_audio", "httpx", "httpcore", "urllib3"):
            logging.getLogger(noisy).setLevel(logging.WARNING)


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("audio_file", type=click.Path(exists=True, path_type=Path))
@click.argument("text_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--model",
    "-m",
    default=DEFAULT_MODEL_ID,
    show_default=True,
    metavar="MODEL_ID",
    help="mlx-community forced aligner model to use.",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default=None,
    metavar="FILE",
    help="Write aligned JSON to FILE instead of stdout.",
)
@click.option("--debug", is_flag=True, help="Enable verbose debug logging.")
def main(
    audio_file: Path,
    text_file: Path,
    model: str,
    output: Path | None,
    debug: bool,
) -> None:
    """Align AUDIO_FILE to TEXT_FILE.

    TEXT_FILE must be a JSON file with a "text" key:

    \b
        {"text": "bonjour tout le monde ..."}

    Output is a JSON array of word-level timing segments:

    \b
        [{"start": 0.0, "end": 0.42, "text": "bonjour"}, ...]

    Written to stdout by default; use --output to write to a file.
    """
    _configure_logging(debug)

    # --- read and validate text JSON ---
    try:
        raw = text_file.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("Cannot read text file: %s", exc)
        sys.exit(1)

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("Text file is not valid JSON: %s", exc)
        sys.exit(1)

    if not isinstance(payload, dict) or "text" not in payload:
        logger.error('Text JSON must be an object with a "text" key.')
        sys.exit(1)

    text = payload["text"]

    if not isinstance(text, str):
        logger.error('"text" must be a string, got %s.', type(text).__name__)
        sys.exit(1)

    audio_path = audio_file

    # --- run alignment ---
    try:
        segments = align(audio_path, text, model_id=model)
    except FileNotFoundError as exc:
        logger.error("Audio file not found: %s", exc)
        sys.exit(1)
    except ValueError as exc:
        logger.error("Invalid input: %s", exc)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        logger.error("Alignment failed: %s", exc)
        logger.debug("Traceback:", exc_info=True)
        sys.exit(1)

    logger.info("Aligned %d segments.", len(segments))

    # --- write output ---
    result_json = json.dumps(segments, ensure_ascii=False, indent=2)

    if output is not None:
        try:
            output.write_text(result_json + "\n", encoding="utf-8")
            logger.info("Saved to %s", output)
        except OSError as exc:
            logger.error("Cannot write output file: %s", exc)
            sys.exit(1)
    else:
        print(result_json)


if __name__ == "__main__":
    main()
