"""Generic batch translation with recursive-split retry strategy."""
import logging
import time
from collections.abc import Callable
from pathlib import Path

from .config import TranslationConfig
from .llm import generate_text
from .validator import ValidationError, parse_and_validate

logger = logging.getLogger(__name__)

# Type alias for prompt builder: (batch, context_for_batch) -> prompt string
PromptBuilder = Callable[[list[dict], list[dict]], str]


def load_prompt_template(prompt_file: Path) -> str:
    return prompt_file.read_text(encoding="utf-8")


def _translate_batch(
    batch: list[dict],
    context: list[dict],
    config: TranslationConfig,
    build_prompt: PromptBuilder,
    source_key: str,
    batch_id: str,
) -> list[dict]:
    prompt = build_prompt(batch, context)
    last_error: Exception | None = None

    for attempt in range(config.max_retries + 1):
        if attempt > 0:
            logger.debug("Batch %s: retry %d/%d", batch_id, attempt, config.max_retries)
            time.sleep(config.retry_delay)
        try:
            raw = generate_text(
                prompt=prompt,
                model_path=config.model_path,
                max_tokens=config.max_tokens,
                temperature=config.temperature,
            )
            return parse_and_validate(raw, batch, source_key=source_key)
        except (ValidationError, Exception) as exc:
            logger.warning("Batch %s attempt %d failed: %s", batch_id, attempt, exc)
            last_error = exc

    raise last_error  # type: ignore[misc]


def _translate_with_split(
    batch: list[dict],
    context: list[dict],
    config: TranslationConfig,
    build_prompt: PromptBuilder,
    source_key: str,
    batch_id: str,
) -> list[dict]:
    try:
        return _translate_batch(batch, context, config, build_prompt, source_key, batch_id)
    except Exception:
        if len(batch) == 1:
            logger.error("Single item %d failed all retries", batch[0]["id"])
            raise

        mid = len(batch) // 2
        logger.info("Batch %s failed; splitting into %d + %d", batch_id, mid, len(batch) - mid)

        results_a = _translate_with_split(
            batch[:mid], context, config, build_prompt, source_key, f"{batch_id}_a"
        )
        results_b = _translate_with_split(
            batch[mid:], context, config, build_prompt, source_key, f"{batch_id}_b"
        )
        return results_a + results_b


def translate_all(
    items: list[dict],
    config: TranslationConfig,
    build_prompt: PromptBuilder,
    source_key: str = "fr",
    context_window: int = 0,
) -> dict[int, str]:
    """
    Translate all items in batches.

    Args:
        items: list of {"id": int, <source_key>: str} dicts
        config: TranslationConfig
        build_prompt: (batch, context_items) -> prompt string
        source_key: key name for source text ("fr" or "text")
        context_window: number of previous items to pass as context (0 = no context)

    Returns:
        dict mapping id -> translated zh string
    """
    translations: dict[int, str] = {}
    total = len(items)

    for batch_num, start in enumerate(range(0, total, config.batch_size), start=1):
        batch = items[start : start + config.batch_size]
        context = items[max(0, start - context_window) : start] if context_window else []
        batch_id = f"batch_{batch_num:02d}"

        logger.info(
            "Translating %s: items %d-%d of %d",
            batch_id, batch[0]["id"], batch[-1]["id"], total,
        )
        results = _translate_with_split(
            batch, context, config, build_prompt, source_key, batch_id
        )
        for item in results:
            translations[item["id"]] = item["zh"]

    logger.info("Translation complete: %d/%d items", len(translations), total)
    return translations
