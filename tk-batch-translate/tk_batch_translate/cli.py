"""Unified CLI: tk-batch-translate {comments,srt}."""
import json
import logging
import sys
from pathlib import Path

import click

from .config import TranslationConfig

_defaults = TranslationConfig()


def _configure_logging(verbosity: int) -> None:
    levels = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    logging.basicConfig(
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        level=levels.get(verbosity, logging.DEBUG),
    )


def _common_options(fn):
    """Shared options for both subcommands."""
    fn = click.option("-o", "--output", type=click.Path(path_type=Path), default=None, help="Output file path")(fn)
    fn = click.option("-m", "--model", default=_defaults.model_path, show_default=True, help="MLX model path")(fn)
    fn = click.option("-b", "--batch-size", type=int, default=_defaults.batch_size, show_default=True)(fn)
    fn = click.option("--max-tokens", type=int, default=_defaults.max_tokens, show_default=True)(fn)
    fn = click.option("--temperature", type=float, default=_defaults.temperature, show_default=True)(fn)
    fn = click.option("--prompt", type=click.Path(exists=True, path_type=Path), default=None, help="Custom prompt template")(fn)
    fn = click.option("-v", "--verbose", count=True, help="Increase verbosity (-v info, -vv debug).")(fn)
    return fn


def _config_from_kwargs(kwargs: dict) -> TranslationConfig:
    return TranslationConfig(
        model_path=kwargs["model"],
        batch_size=kwargs["batch_size"],
        max_tokens=kwargs["max_tokens"],
        temperature=kwargs["temperature"],
    )


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def main() -> None:
    """Batch-translate French TikTok content to Chinese."""


@main.command()
@click.argument("input", type=click.Path(exists=True, path_type=Path))
@click.option("--description", type=click.Path(exists=True, path_type=Path), default=None, help="Video description file for translation context")
@_common_options
def comments(input: Path, description: Path | None, output: Path | None, verbose: int, prompt: Path | None, **kwargs) -> None:
    """Translate comment JSON."""
    _configure_logging(verbose)
    from .comments.translator import translate_comments

    config = _config_from_kwargs(kwargs)
    try:
        merged = translate_comments(
            input, output, config,
            prompt_file=prompt,
            description_file=description,
        )
        if not output:
            print(json.dumps(merged, ensure_ascii=False, indent=2))
    except Exception as exc:
        logging.getLogger(__name__).error("Failed: %s", exc)
        logging.getLogger(__name__).debug("Traceback:", exc_info=True)
        sys.exit(1)


@main.command()
@click.argument("input", type=click.Path(exists=True, path_type=Path))
@click.option("--format", "output_format", type=click.Choice(["srt", "vtt"]), default="srt", show_default=True, help="Output subtitle format.")
@_common_options
def srt(input: Path, output_format: str, output: Path | None, verbose: int, prompt: Path | None, **kwargs) -> None:
    """Translate SRT subtitles."""
    _configure_logging(verbose)
    from .srt.translator import translate_srt

    config = _config_from_kwargs(kwargs)
    output_path = output or input.with_suffix("").with_suffix(f".bilingual.{output_format}")

    try:
        translate_srt(
            input, output_path, config,
            output_format=output_format,
            prompt_file=prompt,
        )
        print(f"Done: {output_path}")
    except Exception as exc:
        logging.getLogger(__name__).error("Failed: %s", exc)
        logging.getLogger(__name__).debug("Traceback:", exc_info=True)
        sys.exit(1)
