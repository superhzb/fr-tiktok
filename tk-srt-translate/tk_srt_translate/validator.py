"""Validate and parse LLM translation responses."""
import json
import logging
import re

logger = logging.getLogger(__name__)

_SMART_QUOTE_MAP = str.maketrans({"\u201c": '"', "\u201d": '"', "\u2018": "'", "\u2019": "'"})
_CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")
_STATS_RE = re.compile(r"^[\d\s,.\-:;]+$")


def _sanitize_smart_quotes(text: str) -> str:
    """Replace smart quotes in JSON-structural positions with ASCII equivalents."""
    return text.translate(_SMART_QUOTE_MAP)


def _is_valid_translation(zh: str, fr: str) -> bool:
    if not zh or not zh.strip():
        logger.debug("Rejected: empty translation for fr=%r", fr[:40])
        return False

    if _CHINESE_RE.search(zh):
        if zh.strip() == fr.strip():
            logger.debug("Rejected: translation identical to source fr=%r", fr[:40])
            return False
        return True

    if _STATS_RE.match(zh.strip()):
        return True  # statistical data

    fr_words = fr.strip().split()
    if len(fr_words) <= 3 and zh.strip().lower() == fr.strip().lower():
        return True  # proper noun / short name

    if zh.strip().lower() != fr.strip().lower():
        return True  # different from source

    logger.debug("Rejected: same as source >3 words fr=%r", fr[:40])
    return False


class ValidationError(Exception):
    pass


def parse_and_validate(raw: str, batch: list[dict]) -> list[dict]:
    """
    Parse the LLM response and validate it against the input batch.

    Args:
        raw: raw string from the LLM
        batch: list of {"id": int, "fr": str} dicts

    Returns:
        list of {"id": int, "zh": str} dicts

    Raises:
        ValidationError on any structural or content problem
    """
    sanitized = _sanitize_smart_quotes(raw)

    # Step 1: parse JSON
    parsed = None
    try:
        parsed = json.loads(sanitized)
    except json.JSONDecodeError:
        logger.debug("Direct JSON parse failed, trying regex extraction")
        m = re.search(r"\[.*\]", sanitized, re.DOTALL)
        if m:
            try:
                parsed = json.loads(m.group())
            except json.JSONDecodeError:
                pass

    if parsed is None:
        raise ValidationError("JSON parse failed")

    # Step 2: structure validation
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

    # Step 3: content validation
    for item, expected in zip(parsed, batch):
        if not _is_valid_translation(item["zh"], expected["fr"]):
            raise ValidationError(
                f"Invalid translation for id={item['id']}: zh={item['zh']!r}"
            )

    logger.debug("Validated %d translations successfully", len(parsed))
    return parsed
