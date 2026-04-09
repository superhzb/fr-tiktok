# tk-punctuation

## Purpose

`tk-punctuation` adds punctuation back to raw transcription text using a token-classification model.

Core module:

- `src/tk_punctuation/punctuator.py`

Public API:

- `punctuate_text(text, classifier=None, model_id=..., chunk_words=...) -> str`

## Runtime Requirements

- Python 3.11+
- `transformers`
- `torch`
- a compatible punctuation model

## Input / Output Contract

Library input:

- raw transcription string

Library output:

- punctuated string

CLI input:

- JSON object with a `text` field

CLI output:

- JSON object with a `text` field

## Key Snippet

```python
from tk_punctuation import punctuate_text

raw = "bonjour tout le monde comment ca va aujourd hui"
result = punctuate_text(raw)
print(result)
```

## How It Works

1. strip existing punctuation
2. split text into chunks
3. run token classification
4. map labels to punctuation marks
5. normalize the final text

The normalization helpers are important. This package is not just one model call.

## How To Recreate In Another Project

Preserve:

- chunked processing
- label-to-punctuation mapping
- text normalization heuristics

The easiest stable contract is still:

- `str -> str`
