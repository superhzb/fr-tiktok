"""CLI entry point for tk-comment-checker."""

import argparse
import json
import logging
import sys

from . import get_comments


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tk-comments",
        description="Fetch top comments from a TikTok video, sorted by likes.",
    )
    parser.add_argument("url", help="TikTok video URL")
    parser.add_argument(
        "--count", type=int, default=10, metavar="N",
        help="Number of top comments to return (default: 10)",
    )
    parser.add_argument(
        "--output", default="-", metavar="FILE",
        help="Output file path; use - for stdout (default: -)",
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    try:
        comments = get_comments(args.url, args.count)
    except ValueError as exc:
        logging.getLogger(__name__).error("%s", exc)
        sys.exit(1)
    except RuntimeError as exc:
        logging.getLogger(__name__).error("%s", exc)
        sys.exit(1)

    if not comments:
        logging.getLogger(__name__).warning("No comments found.")
        sys.exit(1)

    output = json.dumps(comments, ensure_ascii=False, indent=2)

    if args.output == "-":
        print(output)
    else:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        logging.getLogger(__name__).info("Saved %d comments to %s", len(comments), args.output)
