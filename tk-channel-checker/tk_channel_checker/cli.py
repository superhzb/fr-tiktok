"""CLI entry point for tk-channel-checker."""

import argparse
import json
import logging
import sys

from .constants import DEFAULT_TOP_N
from .scraper import scrape_channel

log = logging.getLogger(__name__)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="tk-channel-checker",
        description="Fetch TikTok channel video metadata as JSON.",
    )
    parser.add_argument(
        "url",
        help="TikTok channel URL, e.g. https://www.tiktok.com/@username",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=DEFAULT_TOP_N,
        metavar="N",
        help=f"Number of videos to fetch (default: {DEFAULT_TOP_N})",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging to stderr",
    )

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        stream=sys.stderr,
    )

    try:
        videos = scrape_channel(args.url, max_videos=args.count)
    except ValueError as exc:
        log.error("%s", exc)
        parser.error(str(exc))

    print(json.dumps(videos, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
