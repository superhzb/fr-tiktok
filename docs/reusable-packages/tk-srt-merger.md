# tk-srt-merger

## Purpose

`tk-srt-merger` combines word-level timestamps and a punctuated transcript into SRT subtitle text.

Core module:

- `src/tk_srt_merger/merger.py`

Public API:

- `merge_srt(timestamps, punct_text) -> str`

## Runtime Requirements

- Python 3.11+
- no heavy model dependency

## Input / Output Contract

Library input:

- `timestamps`: list of `{"text", "start", "end"}`
- `punct_text`: punctuated transcript string

Library output:

- SRT content as a string

CLI output:

- writes `.srt` file

## Key Snippet

```python
from tk_srt_merger import merge_srt

timestamps = [
    {"text": "bonjour", "start": 0.0, "end": 0.4},
    {"text": "tout", "start": 0.4, "end": 0.7},
    {"text": "le", "start": 0.7, "end": 0.8},
    {"text": "monde", "start": 0.8, "end": 1.2},
]

srt = merge_srt(timestamps, "Bonjour tout le monde.")
print(srt)
```

## How It Works

1. align punctuated words back onto timestamp words
2. group words into subtitle segments
3. render SRT text

The split and merge heuristics are the valuable part of this package.

## How To Recreate In Another Project

Preserve:

- the timestamp schema
- punctuation-aware word matching
- subtitle split and merge heuristics
- SRT rendering

This is the easiest package in the set to recreate from scratch.
