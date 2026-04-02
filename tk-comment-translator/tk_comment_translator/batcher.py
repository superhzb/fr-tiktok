import json
import logging
import time
from pathlib import Path

from tk_comment_translator.llm import generate_text
from tk_comment_translator.validator import parse_model_json, validate_translation_rows

logger = logging.getLogger(__name__)

_DEFAULT_PROMPT_FILE = Path(__file__).parent.parent / "prompt.txt"


def load_prompt_template(prompt_file: Path | None = None) -> str:
    path = prompt_file or _DEFAULT_PROMPT_FILE
    return path.read_text(encoding="utf-8")


def build_prompt(batch: list[dict], prompt_template: str, context: str = "") -> str:
    payload = json.dumps(batch, ensure_ascii=False)
    return (
        prompt_template
        .replace("{context}", context)
        .replace("{payload}", payload)
        .strip()
    )


def translate_all_batches(
    items: list[dict], config, prompt_template: str, context: str = ""
) -> dict[int, str]:
    results = {}

    for start in range(0, len(items), config.batch_size):
        batch = items[start : start + config.batch_size]
        logger.info(
            "Translating batch %d-%d (%d items)",
            start + 1,
            start + len(batch),
            len(batch),
        )
        batch_result = translate_batch_with_retry(
            batch, config, prompt_template=prompt_template, context=context
        )
        results.update(batch_result)

    return results


def translate_batch_with_retry(
    batch: list[dict], config, depth: int = 0, prompt_template: str = "", context: str = ""
) -> dict[int, str]:
    if not batch:
        return {}

    last_error = None

    for attempt in range(config.max_retries + 1):
        try:
            prompt = build_prompt(batch, prompt_template, context)
            raw_response = generate_text(
                prompt,
                model_path=config.model_path,
                max_tokens=config.max_tokens,
                temperature=config.temperature,
            )
            rows = parse_model_json(raw_response)
            validate_translation_rows(rows, batch)
            return {row["id"]: row["zh"] for row in rows}
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Batch attempt %d/%d failed (depth=%d): %s",
                attempt + 1,
                config.max_retries + 1,
                depth,
                exc,
            )
            if attempt < config.max_retries:
                time.sleep(config.retry_delay)

    # All retries exhausted — if single item, give up
    if len(batch) == 1:
        raise RuntimeError(
            f"Single comment translation failed for id={batch[0]['id']}: {last_error}"
        )

    # Split batch in half and retry each side recursively
    logger.info("Splitting batch of %d and retrying (depth=%d)", len(batch), depth + 1)
    mid = len(batch) // 2
    left = translate_batch_with_retry(batch[:mid], config, depth + 1, prompt_template, context)
    right = translate_batch_with_retry(batch[mid:], config, depth + 1, prompt_template, context)
    return left | right
