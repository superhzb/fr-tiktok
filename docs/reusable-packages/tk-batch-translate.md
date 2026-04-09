# tk-batch-translate

## Purpose

`tk-batch-translate` batch-translates subtitle files or comment-style item lists using a local MLX LLM.

Core modules:

- `src/tk_batch_translate/batcher.py`
- `src/tk_batch_translate/srt/translator.py`
- `src/tk_batch_translate/comments/translator.py`

Key reusable API surface:

- `translate_all(items, config, build_prompt, source_key=..., context_window=...) -> dict[int, str]`
- `translate_srt(...) -> Path`
- `translate_comments(...) -> list[dict]`

## Runtime Requirements

- Python 3.10+
- `mlx`
- `mlx-lm`
- a local model compatible with `mlx_lm.load()`

## Input / Output Contract

Generic batch layer input:

- list of items with `id` plus a source text field
- prompt-builder function
- translation config

Generic batch layer output:

- mapping of item id to translated text

SRT translator output:

- bilingual `.srt` or `.vtt`

Comment translator output:

- original array plus `zh` field

## Key Snippet

```python
from tk_batch_translate.batcher import translate_all
from tk_batch_translate.config import TranslationConfig

items = [
    {"id": 1, "fr": "bonjour"},
    {"id": 2, "fr": "comment ca va"},
]

config = TranslationConfig()

def build_prompt(batch, context):
    context_text = "\n".join(item["fr"] for item in context)
    return f"Context:\n{context_text}\n\nTranslate these items:\n{batch}"

translations = translate_all(
    items,
    config,
    build_prompt=build_prompt,
    source_key="fr",
    context_window=2,
)
```

## How It Works

1. group items into batches
2. build prompts
3. call the local LLM
4. validate the response
5. retry on failure
6. split failed batches into smaller batches

The recursive split-on-failure behavior is the main reusable idea here.

## How To Recreate In Another Project

If you only want the architecture, keep:

- `TranslationConfig`
- a `generate_text()` backend wrapper
- response validation
- `translate_all()` with retry and recursive split behavior

The generic batch engine is portable. The prompts and output rules are the parts most likely to need rewriting.
