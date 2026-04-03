"""Validate and parse LLM translation responses."""
import json
import logging
import re

logger = logging.getLogger(__name__)

_SMART_QUOTE_MAP = str.maketrans({"\u201c": '"', "\u201d": '"', "\u2018": "'", "\u2019": "'"})
_CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")
_STATS_RE = re.compile(r"^[\d\s,.\-:;]+$")


class ValidationError(Exception):
    pass


def _sanitize_smart_quotes(text: str) -> str:
    return text.translate(_SMART_QUOTE_MAP)


def _extract_json_array(raw: str) -> list:
    sanitized = _sanitize_smart_quotes(raw)
    try:
        return json.loads(sanitized)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\[.*\]", sanitized, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    raise ValidationError("JSON parse failed")


def _is_valid_translation(zh: str, source: str) -> bool:
    if not zh or not zh.strip():
        logger.debug("Rejected: empty translation for source=%r", source[:40])
        return False

    if _CHINESE_RE.search(zh):
        if zh.strip() == source.strip():
            logger.debug("Rejected: translation identical to source=%r", source[:40])
            return False
        return True

    if _STATS_RE.match(zh.strip()):
        return True

    source_words = source.strip().split()
    if len(source_words) <= 3 and zh.strip().lower() == source.strip().lower():
        return True

    if zh.strip().lower() != source.strip().lower():
        return True

    logger.debug("Rejected: same as source >3 words source=%r", source[:40])
    return False


def parse_and_validate(raw: str, batch: list[dict], source_key: str = "fr") -> list[dict]:
    """
    Parse LLM response and validate against the input batch.

    Args:
        raw: raw string from the LLM
        batch: list of {"id": int, <source_key>: str} dicts
        source_key: key name for the source text field ("fr" or "text")

    Returns:
        list of {"id": int, "zh": str} dicts

    Raises:
        ValidationError on any structural or content problem
    """
    parsed = _extract_json_array(raw)

    if not isinstance(parsed, list):
        raise ValidationError(f"Expected JSON array, got {type(parsed).__name__}")

    if len(parsed) != len(batch):
        raise ValidationError(
            f"Length mismatch: expected {len(batch)}, got {len(parsed)}"
        )

    for item, expected in zip(parsed, batch):
        if not isinstance(item, dict):
            raise ValidationError(f"Item is not a dict: {item!r}")
        if "id" not in item or "zh" not in item:
            raise ValidationError(f"Missing id/zh keys in item: {item!r}")
        if not isinstance(item["id"], int):
            raise ValidationError(f"id is not int: {item['id']!r}")
        if item["id"] != expected["id"]:
            raise ValidationError(
                f"ID mismatch: expected {expected['id']}, got {item['id']}"
            )

    for item, expected in zip(parsed, batch):
        if not _is_valid_translation(item["zh"], expected[source_key]):
            raise ValidationError(
                f"Invalid translation for id={item['id']}: zh={item['zh']!r}"
            )

    logger.debug("Validated %d translations successfully", len(parsed))
    return parsed
