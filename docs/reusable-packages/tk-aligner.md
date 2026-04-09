# tk-aligner

## Purpose

`tk-aligner` performs forced alignment between audio and transcript text and returns word-level timing segments.

Core module:

- `src/tk_aligner/aligner.py`

Public API:

- `align(audio_path, text, model_id=...) -> list[dict]`

## Runtime Requirements

- Python 3.11+
- `ffmpeg`
- `mlx-audio`
- a compatible forced-aligner model

## Input / Output Contract

Library input:

- media file path
- transcript text string

Library output:

- list of dicts shaped like:

```python
[
    {"start": 0.0, "end": 0.42, "text": "bonjour"},
    {"start": 0.43, "end": 0.78, "text": "tout"},
]
```

CLI input:

- media file path
- JSON file containing `{"text": "..."}`

CLI output:

- JSON array of timestamped word segments

## Key Snippet

```python
from tk_aligner import align

segments = align("input.mp4", "bonjour tout le monde")
print(segments[0])
```

## How It Works

1. validate inputs
2. convert media to WAV
3. load the aligner model lazily
4. run alignment
5. normalize output into plain dicts

## How To Recreate In Another Project

Keep the segment schema unchanged if you want downstream compatibility:

```python
{"start": float, "end": float, "text": str}
```

That shape is what makes `tk-srt-merger` reusable downstream.
