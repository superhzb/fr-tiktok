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
    start: str
    end: str
    text: str


def parse_srt(content: str) -> list[Segment]:
    blocks = re.split(r"\n{2,}", content.strip())
    segments: list[Segment] = []

    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) < 3:
            continue

        try:
            seg_id = int(lines[0].strip())
        except ValueError:
            continue

        ts_match = _TIMESTAMP_RE.match(lines[1].strip())
        if not ts_match:
            continue

        start, end = ts_match.group(1), ts_match.group(2)
        text = "\n".join(lines[2:]).strip()
        segments.append(Segment(id=seg_id, start=start, end=end, text=text))

    return segments


def format_bilingual_srt(segments: list[Segment], translations: dict[int, str]) -> str:
    lines: list[str] = []
    for seg in segments:
        lines.append(str(seg.id))
        lines.append(f"{seg.start} --> {seg.end}")
        lines.append(seg.text)
        zh = translations.get(seg.id)
        if zh:
            lines.append(zh)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def format_bilingual_vtt(segments: list[Segment], translations: dict[int, str]) -> str:
    lines = ["WEBVTT", ""]
    for seg in segments:
        lines.append(f"{seg.start.replace(',', '.')} --> {seg.end.replace(',', '.')}")
        lines.append(seg.text)
        zh = translations.get(seg.id)
        if zh:
            lines.append(zh)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def format_bilingual_subtitles(
    segments: list[Segment],
    translations: dict[int, str],
    output_format: SubtitleFormat = "srt",
) -> str:
    if output_format == "srt":
        return format_bilingual_srt(segments, translations)
    if output_format == "vtt":
        return format_bilingual_vtt(segments, translations)
    raise ValueError(f"Unsupported subtitle format: {output_format}")
