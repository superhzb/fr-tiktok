"""MLX-based LLM inference layer."""
import logging
import time

logger = logging.getLogger(__name__)

_model = None
_tokenizer = None
_loaded_path: str | None = None


def _load(model_path: str):
    global _model, _tokenizer, _loaded_path
    if _loaded_path == model_path:
        return
    logger.info("Loading model: %s", model_path)
    try:
        from mlx_lm import load  # type: ignore
        _model, _tokenizer = load(model_path)
        _loaded_path = model_path
        logger.info("Model loaded")
    except Exception as exc:
        raise RuntimeError(f"Failed to load model '{model_path}': {exc}") from exc


def generate_text(
    prompt: str,
    model_path: str,
    max_tokens: int = 2048,
    temperature: float = 0.0,
) -> str:
    _load(model_path)
    from mlx_lm import generate  # type: ignore
    from mlx_lm.sample_utils import make_sampler  # type: ignore

    messages = [{"role": "user", "content": prompt}]
    formatted = _tokenizer.apply_chat_template(
        messages, add_generation_prompt=True, tokenize=False
    )
    logger.debug("Sending %d chars to LLM", len(formatted))
    sampler = make_sampler(temperature)
    start = time.monotonic()
    response = generate(
        _model,
        _tokenizer,
        prompt=formatted,
        max_tokens=max_tokens,
        sampler=sampler,
        verbose=False,
    )
    elapsed = time.monotonic() - start
    logger.debug("LLM responded in %.2fs (%d chars)", elapsed, len(response))
    return response
