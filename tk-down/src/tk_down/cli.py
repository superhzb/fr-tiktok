"""CLI entry point: tk-down <url> [options]"""
import logging
import sys
from pathlib import Path

import click

from .downloader import download


def _configure_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        level=level,
        stream=sys.stderr,
    )
    # Suppress noisy third-party loggers unless debugging
    if not debug:
        for noisy in ("httpx", "httpcore", "playwright"):
            logging.getLogger(noisy).setLevel(logging.WARNING)


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("url")
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(path_type=Path),
    default=None,
    metavar="DIR",
    help="Destination directory (default: ~/Public/Tiktok).",
)
@click.option("--debug", is_flag=True, help="Enable verbose debug logging.")
def main(url: str, output_dir: Path | None, debug: bool) -> None:
    """Download a TikTok video from URL.

    Tries a Playwright browser flow first; falls back to HTTP-only if that fails.
    Skips the download if the post was already saved locally.
    Prints the saved file path on success.

    Example:

        tk-down https://www.tiktok.com/@user/video/1234567890
    """
    _configure_logging(debug)
    logger = logging.getLogger(__name__)

    try:
        result = download(url, output_dir)
        click.echo(str(result))
    except ValueError as e:
        logger.error("%s", e)
        sys.exit(1)
    except RuntimeError as e:
        logger.error("%s", e)
        sys.exit(1)
    except Exception as e:
        logger.exception("Unexpected error: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
