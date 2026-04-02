"""Command-line interface for tk-srt-translate."""
import argparse
import logging
import sys
from pathlib import Path

from .config import TranslationConfig
from .parser import SubtitleFormat
from .translator import translate_srt


def _configure_logging(verbosity: int) -> None:
    levels = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    level = levels.get(verbosity, logging.DEBUG)
    logging.basicConfig(
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        level=level,
    )


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tk-srt-translate",
        description="Translate an SRT subtitle file into bilingual subtitles (French → Chinese).",
    )
    p.add_argument("input", type=Path, help="Input SRT file path")
    p.add_argument(
        "-o", "--output", type=Path, default=None,
        help="Output subtitle file path (default: <input>.bilingual.<format>)",
    )
    p.add_argument(
        "--format",
        dest="output_format",
        choices=("srt", "vtt"),
        default="srt",
        help="Output subtitle format (default: srt)",
    )
    p.add_argument(
        "-m", "--model", default=None,
        help="MLX model path or HuggingFace repo (default: mlx-community/Qwen3-4B-Instruct-2507-4bit)",
    )
    p.add_argument(
        "-b", "--batch-size", type=int, default=None,
        help="Segments per translation batch (default: 10)",
    )
    p.add_argument(
        "--max-tokens", type=int, default=None,
        help="Max tokens per LLM call (default: 2048)",
    )
    p.add_argument(
        "--temperature", type=float, default=None,
        help="LLM sampling temperature (default: 0)",
    )
    p.add_argument(
        "--prompt", type=Path, default=None,
        help="Path to prompt template file (default: packaged prompt.txt)",
    )
    p.add_argument(
        "-v", "--verbose", action="count", default=0,
        help="Increase verbosity: -v = INFO, -vv = DEBUG",
    )
    return p


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    _configure_logging(args.verbose)
    log = logging.getLogger(__name__)

    input_path: Path = args.input
    if not input_path.exists():
        log.error("Input file not found: %s", input_path)
        sys.exit(1)

    output_format: SubtitleFormat = args.output_format
    output_suffix = f".bilingual.{output_format}"
    output_path: Path = args.output or input_path.with_suffix("").with_suffix(output_suffix)

    config = TranslationConfig()
    if args.model:
        config.model_path = args.model
    if args.batch_size is not None:
        config.batch_size = args.batch_size
    if args.max_tokens is not None:
        config.max_tokens = args.max_tokens
    if args.temperature is not None:
        config.temperature = args.temperature

    log.info("Input:  %s", input_path)
    log.info("Output: %s", output_path)
    log.info("Format: %s", output_format)
    log.info("Model:  %s", config.model_path)
    if args.prompt:
        log.info("Prompt: %s", args.prompt)

    try:
        translate_srt(
            input_path,
            output_path,
            config,
            output_format=output_format,
            prompt_file=args.prompt,
        )
    except Exception as exc:
        log.error("Translation failed: %s", exc)
        log.debug("Traceback:", exc_info=True)
        sys.exit(1)

    print(f"Done: {output_path}")


if __name__ == "__main__":
    main()
