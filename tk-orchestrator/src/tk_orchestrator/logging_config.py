from __future__ import annotations

import logging
import sys
from pathlib import Path

LOG_FORMAT = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logger with a console handler."""
    root = logging.getLogger()
    root.setLevel(level)
    if not root.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
        root.addHandler(handler)


def get_job_logger(job_id: int, log_dir: Path) -> logging.Logger:
    """Return a logger that writes to <log_dir>/job.log in addition to the root handlers."""
    logger = logging.getLogger(f"job.{job_id}")
    logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler(log_dir / "job.log")
    fh.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    logger.addHandler(fh)
    return logger


def remove_job_logger(job_id: int) -> None:
    """Close and detach all file handlers from a job logger."""
    logger = logging.getLogger(f"job.{job_id}")
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)
