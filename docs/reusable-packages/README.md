# Reusable Packages

This directory contains one markdown file per reusable processing package from this repo.

Excluded on purpose:

- `tk-orchestrator`
- `tk-web`
- `tk-down`
- `tk-channel-checker`
- `tk-comment-checker`

Included here:

- [tk-stt](./tk-stt.md)
- [tk-punctuation](./tk-punctuation.md)
- [tk-aligner](./tk-aligner.md)
- [tk-srt-merger](./tk-srt-merger.md)
- [tk-batch-translate](./tk-batch-translate.md)

## Core Pipeline

```python
from tk_stt import transcribe
from tk_punctuation import punctuate_text
from tk_aligner import align
from tk_srt_merger import merge_srt

text = transcribe("video.mp4")
punctuated = punctuate_text(text)
segments = align("video.mp4", punctuated)
srt = merge_srt(segments, punctuated)
```

## Suggested Extraction Order

1. `tk-srt-merger`
2. `tk-punctuation`
3. `tk-stt`
4. `tk-aligner`
5. `tk-batch-translate`
