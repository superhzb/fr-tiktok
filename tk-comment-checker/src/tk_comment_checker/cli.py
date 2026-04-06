"""CLI entry point for tk-comment-checker."""

import json
import logging
import sys
from pathlib import Path

import click

from . import get_comments

log = logging.getLogger(__name__)


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("url")
@click.option(
    "--count",
    type=int,
    default=10,
    show_default=True,
    metavar="N",
    help="Number of top comments to return.",
)
@click.option(
    "--output",
    "-o",
    default="-",
    type=click.Path(path_type=Path),
    metavar="FILE",
    help="Output file path; use - for stdout.",
)
@click.option("--debug", is_flag=True, help="Enable debug logging.")
def main(url: str, count: int, output: Path, debug: bool) -> None:
    """Fetch top comments from a TikTok video, sorted by likes."""
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    try:
        comments = get_comments(url, count)
    except (ValueError, RuntimeError) as exc:
        log.error("%s", exc)
        sys.exit(1)

    if not comments:
        log.warning("No comments found.")
        sys.exit(1)

    result = json.dumps(comments, ensure_ascii=False, indent=2)

    if str(output) == "-":
        print(result)
    else:
        output.write_text(result, encoding="utf-8")
        log.info("Saved %d comments to %s", len(comments), output)
