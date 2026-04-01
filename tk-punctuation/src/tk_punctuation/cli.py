"""CLI entry point for tk-punctuation."""

import argparse
import json
import logging
import sys
from pathlib import Path

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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tk-punctuation",
        description="Punctuate raw transcription text. "
        "Reads JSON {\"text\": \"...\"} from --input-file or stdin; "
        "writes JSON {\"text\": \"...\"} to stdout.",
    )
    parser.add_argument(
        "--input-file",
        type=Path,
        metavar="FILE",
        help="JSON file containing {\"text\": \"transcription\"}. "
             "Defaults to stdin.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL_ID,
        metavar="MODEL_ID",
        help=f"Hugging Face model id (default: {DEFAULT_MODEL_ID}).",
    )
    parser.add_argument(
        "--chunk-words",
        type=int,
        default=DEFAULT_CHUNK_WORDS,
        metavar="N",
        help=f"Words per processing chunk (default: {DEFAULT_CHUNK_WORDS}).",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging.",
    )
    return parser


def _read_input(args: argparse.Namespace) -> str:
    if args.input_file is not None:
        logger.debug("Reading input from file: %s", args.input_file)
        raw = args.input_file.read_text(encoding="utf-8")
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


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    _configure_logging(args.debug)

    text = _read_input(args).strip()
    if not text:
        logger.warning("Input text is empty; writing empty result.")
        print(json.dumps({"text": ""}, ensure_ascii=False))
        return

    logger.info("Starting punctuation (model=%s, chunk_words=%d).", args.model, args.chunk_words)
    result = punctuate_text(text, model_id=args.model, chunk_words=args.chunk_words)
    logger.info("Done. Output length: %d chars.", len(result))

    print(json.dumps({"text": result}, ensure_ascii=False))


if __name__ == "__main__":
    main()
