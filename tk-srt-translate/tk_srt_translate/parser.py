"""Parse and format subtitle files."""
import logging
import re
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)

SubtitleFormat = Literal["srt", "vtt"]

_TIMESTAMP_RE = re.compile(
    r"(\d{2}:\d{2}:\d{2},\d{3})\s+-->\s+(\d{2}:\d{2}:\d{2},\d{3})"
)


@dataclass
class Segment:
    id: int
    start: str   # raw timestamp string, e.g. "00:00:01,000"
    end: str
    text: str


def parse_srt(content: str) -> list[Segment]:
    """Parse SRT text into a list of Segment objects."""
    blocks = re.split(r"\n{2,}", content.strip())
    segments: list[Segment] = []

    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) < 3:
            logger.debug("Skipping short block: %r", block[:60])
            continue

        try:
            seg_id = int(lines[0].strip())
        except ValueError:
            logger.warning("Could not parse segment id from line: %r", lines[0])
            continue

        ts_match = _TIMESTAMP_RE.match(lines[1].strip())
        if not ts_match:
            logger.warning("Could not parse timestamp from line: %r", lines[1])
            continue

        start, end = ts_match.group(1), ts_match.group(2)
        text = "\n".join(lines[2:]).strip()

        segments.append(Segment(id=seg_id, start=start, end=end, text=text))

    logger.debug("Parsed %d segments from SRT", len(segments))
    return segments


def format_bilingual_srt(segments: list[Segment], translations: dict[int, str]) -> str:
    """Render segments as bilingual SRT. Missing translations fall back to source-only."""
    lines: list[str] = []
    for seg in segments:
        lines.append(str(seg.id))
        lines.append(f"{seg.start} --> {seg.end}")
        lines.append(seg.text)
        zh = translations.get(seg.id)
        if zh:
            lines.append(zh)
        lines.append("")  # blank line between entries
    return "\n".join(lines).rstrip() + "\n"


def format_bilingual_vtt(segments: list[Segment], translations: dict[int, str]) -> str:
    """Render segments as bilingual WebVTT. Missing translations fall back to source-only."""
    lines = ["WEBVTT", ""]
    for seg in segments:
        lines.append(f"{_srt_timestamp_to_vtt(seg.start)} --> {_srt_timestamp_to_vtt(seg.end)}")
        lines.append(seg.text)
        zh = translations.get(seg.id)
        if zh:
            lines.append(zh)
        lines.append("")  # blank line between entries
    return "\n".join(lines).rstrip() + "\n"


def format_bilingual_subtitles(
    segments: list[Segment],
    translations: dict[int, str],
    output_format: SubtitleFormat = "srt",
) -> str:
    """Render segments in the requested subtitle format."""
    if output_format == "srt":
        return format_bilingual_srt(segments, translations)
    if output_format == "vtt":
        return format_bilingual_vtt(segments, translations)
    raise ValueError(f"Unsupported subtitle format: {output_format}")


def _srt_timestamp_to_vtt(timestamp: str) -> str:
    return timestamp.replace(",", ".")
