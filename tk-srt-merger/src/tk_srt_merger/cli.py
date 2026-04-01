"""CLI entry point for tk-srt-merger."""

import json
import logging
import sys
from pathlib import Path

import click

from .merger import merge_srt


def _configure_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )


@click.command()
@click.argument("aligned", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("punctuated", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("output", type=click.Path(dir_okay=False, writable=True, path_type=Path), default="output.srt")
@click.option("--debug", is_flag=True, help="Enable debug logging.")
def main(aligned: Path, punctuated: Path, output: Path, debug: bool) -> None:
    """Merge word-level ALIGNED timestamps with PUNCTUATED text into an SRT file.

    \b
    ALIGNED     JSON array of {text, start, end} word timestamps
    PUNCTUATED  JSON object with a "text" key containing the punctuated transcript
    OUTPUT      Destination .srt file (default: output.srt)
    """
    _configure_logging(debug)
    logger = logging.getLogger(__name__)

    logger.debug("loading timestamps from %s", aligned)
    with aligned.open(encoding="utf-8") as f:
        timestamps = json.load(f)

    logger.debug("loading punctuated text from %s", punctuated)
    with punctuated.open(encoding="utf-8") as f:
        data = json.load(f)
    punct_text: str = data["text"]

    srt_content = merge_srt(timestamps, punct_text)

    logger.debug("writing output to %s", output)
    output.write_text(srt_content, encoding="utf-8")

    sub_count = srt_content.count("\n\n")
    click.echo(f"Written {sub_count} subtitles to {output}")
