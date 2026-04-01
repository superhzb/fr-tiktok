"""High-level translate_srt entry point."""
import logging
from pathlib import Path

from .batcher import translate_all
from .config import TranslationConfig
from .parser import SubtitleFormat, format_bilingual_subtitles, parse_srt
from .preprocessor import preprocess

logger = logging.getLogger(__name__)


def translate_srt(
    input_path: str | Path,
    output_path: str | Path,
    config: TranslationConfig | None = None,
    output_format: SubtitleFormat = "srt",
) -> Path:
    """
    Translate an SRT file and write bilingual subtitles to output_path.

    Args:
        input_path:  path to the source SRT file
        output_path: path where the bilingual subtitle file will be written
        config:      TranslationConfig (defaults used if None)
        output_format: subtitle format to render, "srt" or "vtt"

    Returns:
        Resolved output path
    """
    if config is None:
        config = TranslationConfig()

    input_path = Path(input_path)
    output_path = Path(output_path)

    logger.info("Reading SRT: %s", input_path)
    content = input_path.read_text(encoding="utf-8")

    segments = parse_srt(content)
    logger.info("Parsed %d raw segments", len(segments))

    segments, translation_input = preprocess(segments)
    logger.info("After preprocessing: %d segments", len(segments))

    translations = translate_all(translation_input, config)

    bilingual = format_bilingual_subtitles(segments, translations, output_format=output_format)
    output_path.write_text(bilingual, encoding="utf-8")
    logger.info("Wrote bilingual %s: %s", output_format.upper(), output_path)

    return output_path
