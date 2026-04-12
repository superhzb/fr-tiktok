from __future__ import annotations

import logging
import shutil
from pathlib import Path

from .models import Video, get_session

logger = logging.getLogger(__name__)


def delete_video_and_files(video_id: str, output_dir: Path) -> bool:
    with get_session() as s:
        v = s.get(Video, video_id)
        if v is None:
            return False
        channel_username = v.channel.username if v.channel else v.author
        s.delete(v)

    if channel_username:
        video_dir = output_dir / channel_username / video_id
        if video_dir.is_dir():
            try:
                shutil.rmtree(video_dir)
                logger.info("Removed output directory %s", video_dir)
            except OSError as exc:
                logger.error("Failed to remove output directory %s: %s", video_dir, exc)

    logger.info("Deleted video %s", video_id)
    return True
