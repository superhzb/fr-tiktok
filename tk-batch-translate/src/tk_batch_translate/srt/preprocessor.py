"""Filter, sort, and re-number segments before translation."""
import logging
import re

from .parser import Segment

logger = logging.getLogger(__name__)

_EMPTY_PATTERNS = re.compile(r"^\.{3}|^\s*$")


def preprocess(segments: list[Segment]) -> tuple[list[Segment], list[dict]]:
    before = len(segments)
    segments = [s for s in segments if not _EMPTY_PATTERNS.match(s.text)]
    logger.debug("Filtered %d empty/ellipsis segments", before - len(segments))

    segments = sorted(segments, key=lambda s: s.id)

    for new_id, seg in enumerate(segments, start=1):
        seg.id = new_id

    translation_input = [{"id": s.id, "fr": s.text} for s in segments]
    return segments, translation_input
