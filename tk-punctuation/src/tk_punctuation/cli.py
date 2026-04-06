"""CLI entry point for tk-punctuation."""

import json
import logging
import sys
from pathlib import Path

import click

from .punctuator import DEFAULT_CHUNK_WORDS, DEFAULT_MODEL_ID, punctuate_text

logger = logging.getLogger(__name__)


def _configure_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stderr,
    )
    # Suppress noisy third-party loggers unless in debug mode
    if not debug:
        for noisy in ("transformers", "torch", "filelock", "urllib3"):
            logging.getLogger(noisy).setLevel(logging.WARNING)


def _read_input(input_file: Path | None) -> str:
    if input_file is not None:
        logger.debug("Reading input from file: %s", input_file)
        raw = input_file.read_text(encoding="utf-8")
    else:
        logger.debug("Reading input from stdin.")
        raw = sys.stdin.read()

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("Input is not valid JSON: %s", exc)
        sys.exit(1)

    if not isinstance(payload, dict) or "text" not in payload:
        logger.error('Input JSON must have a "text" key, got: %s', list(payload.keys()) if isinstance(payload, dict) else type(payload).__name__)
        sys.exit(1)

    text = payload["text"]
    if not isinstance(text, str):
        logger.error('"text" must be a string, got %s', type(text).__name__)
        sys.exit(1)

    return text


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--input-file",
    type=click.Path(exists=True, path_type=Path),
    metavar="FILE",
    help='JSON file containing {"text": "transcription"}. Defaults to stdin.',
)
@click.option(
    "--model",
    default=DEFAULT_MODEL_ID,
    show_default=True,
    metavar="MODEL_ID",
    help="Hugging Face model id.",
)
@click.option(
    "--chunk-words",
    type=int,
    default=DEFAULT_CHUNK_WORDS,
    show_default=True,
    metavar="N",
    help="Words per processing chunk.",
)
@click.option("--debug", is_flag=True, help="Enable debug logging.")
def main(input_file: Path | None, model: str, chunk_words: int, debug: bool) -> None:
    """Punctuate raw transcription text.

    Reads JSON {"text": "..."} from --input-file or stdin;
    writes JSON {"text": "..."} to stdout.
    """
    _configure_logging(debug)

    text = _read_input(input_file).strip()
    if not text:
        logger.warning("Input text is empty; writing empty result.")
        print(json.dumps({"text": ""}, ensure_ascii=False))
        return

    logger.info("Starting punctuation (model=%s, chunk_words=%d).", model, chunk_words)
    result = punctuate_text(text, model_id=model, chunk_words=chunk_words)
    logger.info("Done. Output length: %d chars.", len(result))

    print(json.dumps({"text": result}, ensure_ascii=False))


if __name__ == "__main__":
    main()
