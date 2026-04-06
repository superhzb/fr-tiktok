"""Comment translation: JSON array of comments -> JSON array with zh field."""
import json
import logging
from pathlib import Path

from ..batcher import load_prompt_template, translate_all
from ..config import TranslationConfig

logger = logging.getLogger(__name__)

_DEFAULT_PROMPT = Path(__file__).with_name("prompt.txt")


def _parse_comments(raw_items: list[dict]) -> list[dict]:
    if not isinstance(raw_items, list):
        raise ValueError("Input must be a JSON array")

    parsed = []
    for index, item in enumerate(raw_items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Comment #{index} is not an object")
        for field in ("user", "username", "text", "likes"):
            if field not in item:
                raise ValueError(f"Comment #{index} missing field: {field}")
        parsed.append({
            "id": index,
            "user": item["user"],
            "username": item["username"],
            "text": str(item["text"]),
            "likes": item["likes"],
        })
    return parsed


def _preprocess(comments: list[dict]) -> tuple[list[dict], list[dict]]:
    translation_items = []
    for comment in comments:
        comment["text"] = comment["text"].strip()
        if comment["text"]:
            translation_items.append({"id": comment["id"], "text": comment["text"]})
    return comments, translation_items


def _build_prompt(batch: list[dict], context: list[dict], template: str, video_description: str) -> str:
    payload = json.dumps(batch, ensure_ascii=False)
    return template.replace("{context}", video_description).replace("{payload}", payload).strip()


def _merge(comments: list[dict], translations: dict[int, str]) -> list[dict]:
    return [
        {
            "user": c["user"],
            "username": c["username"],
            "text": c["text"],
            "likes": c["likes"],
            "zh": translations.get(c["id"], ""),
        }
        for c in comments
    ]


def translate_comments(
    input_path: Path,
    output_path: Path | None,
    config: TranslationConfig | None = None,
    prompt_file: Path | None = None,
    description_file: Path | None = None,
) -> list[dict]:
    """
    Translate comments from a JSON file.

    Returns the merged list (original fields + zh).
    If output_path is given, also writes to that file.
    """
    if config is None:
        config = TranslationConfig()

    raw_items = json.loads(input_path.read_text(encoding="utf-8"))
    template = load_prompt_template(prompt_file or _DEFAULT_PROMPT)
    video_description = description_file.read_text(encoding="utf-8").strip() if description_file else ""

    comments = _parse_comments(raw_items)
    comments, translation_items = _preprocess(comments)

    prompt_builder = lambda batch, ctx: _build_prompt(batch, ctx, template, video_description)

    translations = translate_all(
        translation_items, config, build_prompt=prompt_builder, source_key="text",
    )
    merged = _merge(comments, translations)

    if output_path:
        output_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Wrote output to %s", output_path)

    return merged
