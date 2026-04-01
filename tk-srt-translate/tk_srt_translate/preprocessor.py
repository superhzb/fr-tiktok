"""Filter, sort, and re-number segments before translation."""
import logging
import re

from .parser import Segment

logger = logging.getLogger(__name__)

_EMPTY_PATTERNS = re.compile(r"^\.{3}|^\s*$")


def preprocess(segments: list[Segment]) -> tuple[list[Segment], list[dict]]:
    """
    Returns:
        filtered_segments: cleaned Segment list with sequential ids
        translation_input: [{"id": N, "fr": "..."}] ready for the LLM
    """
    # 1. Filter empties / ellipsis-only
    before = len(segments)
    segments = [s for s in segments if not _EMPTY_PATTERNS.match(s.text)]
    logger.debug("Filtered %d empty/ellipsis segments", before - len(segments))

    # 2. Sort by original id
    segments = sorted(segments, key=lambda s: s.id)

    # 3. Renumber sequentially
    for new_id, seg in enumerate(segments, start=1):
        if seg.id != new_id:
            logger.debug("Renumbering segment %d → %d", seg.id, new_id)
            seg.id = new_id

    # 4. Build translation input
    translation_input = [{"id": s.id, "fr": s.text} for s in segments]

    logger.debug("Preprocessed to %d segments", len(segments))
    return segments, translation_input
