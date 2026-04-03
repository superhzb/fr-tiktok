"""Unified CLI: tk-batch-translate {comments,srt}."""
import argparse
import json
import logging
import sys
from pathlib import Path

from .config import TranslationConfig


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    defaults = TranslationConfig()
    parser.add_argument("-o", "--output", type=Path, default=None, help="Output file path")
    parser.add_argument("-m", "--model", default=defaults.model_path, help="MLX model path")
    parser.add_argument("-b", "--batch-size", type=int, default=defaults.batch_size)
    parser.add_argument("--max-tokens", type=int, default=defaults.max_tokens)
    parser.add_argument("--temperature", type=float, default=defaults.temperature)
    parser.add_argument("--prompt", type=Path, default=None, help="Custom prompt template")
    parser.add_argument("-v", "--verbose", action="count", default=0)


def _config_from_args(args: argparse.Namespace) -> TranslationConfig:
    return TranslationConfig(
        model_path=args.model,
        batch_size=args.batch_size,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
    )


def _configure_logging(verbosity: int) -> None:
    levels = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    logging.basicConfig(
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        level=levels.get(verbosity, logging.DEBUG),
    )


def _cmd_comments(args: argparse.Namespace) -> None:
    from .comments.translator import translate_comments

    config = _config_from_args(args)
    merged = translate_comments(
        args.input, args.output, config,
        prompt_file=args.prompt,
        description_file=args.description,
    )
    if not args.output:
        print(json.dumps(merged, ensure_ascii=False, indent=2))


def _cmd_srt(args: argparse.Namespace) -> None:
    from .srt.translator import translate_srt

    config = _config_from_args(args)
    output_format = args.format
    output_path = args.output or args.input.with_suffix("").with_suffix(f".bilingual.{output_format}")

    translate_srt(
        args.input, output_path, config,
        output_format=output_format,
        prompt_file=args.prompt,
    )
    print(f"Done: {output_path}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="tk-batch-translate",
        description="Batch-translate French TikTok content to Chinese.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ── comments ──────────────────────────────────────────────────────────
    p_comments = sub.add_parser("comments", help="Translate comment JSON")
    p_comments.add_argument("input", type=Path, help="Input JSON file")
    p_comments.add_argument(
        "--description", type=Path, default=None,
        help="Video description file for translation context",
    )
    _add_common_args(p_comments)
    p_comments.set_defaults(func=_cmd_comments)

    # ── srt ───────────────────────────────────────────────────────────────
    p_srt = sub.add_parser("srt", help="Translate SRT subtitles")
    p_srt.add_argument("input", type=Path, help="Input SRT file")
    p_srt.add_argument(
        "--format", dest="format", choices=("srt", "vtt"), default="srt",
        help="Output subtitle format (default: srt)",
    )
    _add_common_args(p_srt)
    p_srt.set_defaults(func=_cmd_srt)

    args = parser.parse_args(argv)
    _configure_logging(args.verbose)

    try:
        args.func(args)
    except Exception as exc:
        logging.getLogger(__name__).error("Failed: %s", exc)
        logging.getLogger(__name__).debug("Traceback:", exc_info=True)
        sys.exit(1)
