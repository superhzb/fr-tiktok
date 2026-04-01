"""Batch translation with recursive-split retry strategy."""
import json
import logging
import time

from .config import TranslationConfig
from .llm import generate_text
from .validator import ValidationError, parse_and_validate

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = """\
你是一名专业法语字幕译员，任务是将法语字幕翻译成准确、贴近原句结构的中文，用于语言学习。

翻译规则：

1. 只输出 JSON 数组，格式严格如下：
  [{{"id": 1, "zh": "翻译内容"}}, ...]

2. 必须保留并按顺序输出所有id： 每一条输出的 id 必须原样复制自输入字幕；
   注意: 输出条目与 原字幕 必须一一对应，禁止跳过、重复或错位；

翻译要求：

1. 尽量直译，保持原句逻辑和语序
2. 中文需通顺，但允许保留轻微"外语感"
3. 可参考【前文提要】理解语境
4. 输出必须是单个完整JSON数组，格式严格为：[{{...}}, {{...}}, {{...}}]，不要分行输出多个数组。

输入示例：
[{{"id": 1, "fr": "Et il faut être vraiment fort pour aller jusqu'au bout."}}]

输出示例：
[{{"id": 1, "zh": "而且要走到最后，真的需要很强"}}]

前文提要：
{context}

待处理字幕：
{segments}"""


def _build_prompt(context_segments: list[dict], batch: list[dict]) -> str:
    context_text = "\n".join(s["fr"] for s in context_segments)
    segments_json = json.dumps(batch, ensure_ascii=False)
    return _PROMPT_TEMPLATE.format(context=context_text, segments=segments_json)


def _translate_batch(
    batch: list[dict],
    context_segments: list[dict],
    config: TranslationConfig,
    batch_id: str,
) -> list[dict]:
    """Translate one batch with retries. Raises ValidationError on total failure."""
    prompt = _build_prompt(context_segments, batch)
    logger.debug("Batch %s: translating %d segments", batch_id, len(batch))

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
            return parse_and_validate(raw, batch)
        except ValidationError as exc:
            logger.warning("Batch %s attempt %d failed: %s", batch_id, attempt, exc)
            last_error = exc

    raise last_error  # type: ignore[misc]


def _translate_with_split(
    batch: list[dict],
    context_segments: list[dict],
    config: TranslationConfig,
    batch_id: str,
) -> list[dict]:
    """Recursively split and retry failing batches down to single segments."""
    try:
        return _translate_batch(batch, context_segments, config, batch_id)
    except ValidationError:
        if len(batch) == 1:
            logger.error(
                "Single segment %d failed all retries — giving up", batch[0]["id"]
            )
            raise

        mid = len(batch) // 2
        half_a, half_b = batch[:mid], batch[mid:]
        logger.info(
            "Batch %s failed; splitting into %s_a (%d) and %s_b (%d)",
            batch_id, batch_id, len(half_a), batch_id, len(half_b),
        )

        results_a = _translate_with_split(half_a, context_segments, config, f"{batch_id}_a")
        results_b = _translate_with_split(half_b, context_segments, config, f"{batch_id}_b")
        return results_a + results_b


def translate_all(
    segments: list[dict],
    config: TranslationConfig,
) -> dict[int, str]:
    """
    Translate all segments in batches.

    Args:
        segments: list of {"id": int, "fr": str}
        config: TranslationConfig

    Returns:
        dict mapping id → translated zh string
    """
    translations: dict[int, str] = {}
    total = len(segments)
    batch_size = config.batch_size

    for batch_num, start in enumerate(range(0, total, batch_size), start=1):
        batch = segments[start : start + batch_size]
        context = segments[max(0, start - 3) : start]
        batch_id = f"batch_{batch_num:02d}"

        logger.info(
            "Translating %s: segments %d–%d of %d",
            batch_id, batch[0]["id"], batch[-1]["id"], total,
        )
        results = _translate_with_split(batch, context, config, batch_id)
        for item in results:
            translations[item["id"]] = item["zh"]

    logger.info("Translation complete: %d/%d segments", len(translations), total)
    return translations
