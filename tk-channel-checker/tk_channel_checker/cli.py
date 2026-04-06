"""CLI entry point for tk-channel-checker."""

import json
import logging
import sys

import click

from .constants import DEFAULT_TOP_N
from .scraper import scrape_channel

log = logging.getLogger(__name__)


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("url")
@click.option(
    "--count",
    type=int,
    default=DEFAULT_TOP_N,
    show_default=True,
    metavar="N",
    help="Number of videos to fetch.",
)
@click.option("--debug", is_flag=True, help="Enable debug logging to stderr.")
def main(url: str, count: int, debug: bool) -> None:
    """Fetch TikTok channel video metadata as JSON.

    URL is a TikTok channel URL, e.g. https://www.tiktok.com/@username
    """
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        stream=sys.stderr,
    )

    try:
        videos = scrape_channel(url, max_videos=count)
    except ValueError as exc:
        log.error("%s", exc)
        raise click.ClickException(str(exc))

    print(json.dumps(videos, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
