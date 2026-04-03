"""SRT subtitle translation: SRT file -> bilingual SRT/VTT."""
import json
import logging
from pathlib import Path

from ..batcher import load_prompt_template, translate_all
from ..config import TranslationConfig
from .parser import SubtitleFormat, format_bilingual_subtitles, parse_srt
from .preprocessor import preprocess

logger = logging.getLogger(__name__)

_DEFAULT_PROMPT = Path(__file__).with_name("prompt.txt")


def _build_prompt(batch: list[dict], context: list[dict], template: str) -> str:
    context_text = "\n".join(s["fr"] for s in context)
    segments_json = json.dumps(batch, ensure_ascii=False)
    return template.format(context=context_text, segments=segments_json)


def translate_srt(
    input_path: str | Path,
    output_path: str | Path,
    config: TranslationConfig | None = None,
    output_format: SubtitleFormat = "srt",
    prompt_file: str | Path | None = None,
) -> Path:
    if config is None:
        config = TranslationConfig()

    input_path = Path(input_path)
    output_path = Path(output_path)

    content = input_path.read_text(encoding="utf-8")
    segments = parse_srt(content)
    logger.info("Parsed %d raw segments", len(segments))

    segments, translation_input = preprocess(segments)
    logger.info("After preprocessing: %d segments", len(segments))

    template = load_prompt_template(Path(prompt_file) if prompt_file else _DEFAULT_PROMPT)
    prompt_builder = lambda batch, ctx: _build_prompt(batch, ctx, template)

    translations = translate_all(
        translation_input, config, build_prompt=prompt_builder,
        source_key="fr", context_window=3,
    )

    bilingual = format_bilingual_subtitles(segments, translations, output_format=output_format)
    output_path.write_text(bilingual, encoding="utf-8")
    logger.info("Wrote bilingual %s: %s", output_format.upper(), output_path)

    return output_path
