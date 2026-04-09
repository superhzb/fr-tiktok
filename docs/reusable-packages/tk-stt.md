# tk-stt

## Purpose

`tk-stt` turns an audio or video file into plain transcription text using `ffmpeg` plus `mlx-audio` Whisper.

Core module:

- `src/tk_stt/stt.py`

Public API:

- `transcribe(input_path, model_id=...) -> str`

## Runtime Requirements

- Python 3.11+
- `ffmpeg` on `PATH`
- `mlx-audio`
- MLX-compatible runtime if you want the same backend

## Input / Output Contract

Library input:

- path to audio or video file

Library output:

- plain transcription string

CLI output:

- JSON object: `{"text": "..."}`

## Key Snippet

```python
from tk_stt import transcribe

text = transcribe("input.mp4")
print(text)
```

## How It Works

1. validate the input path
2. convert media to 16 kHz mono WAV with `ffmpeg`
3. lazily load the MLX Whisper model
4. run inference
5. return `result.text`

## How To Recreate In Another Project

Keep the public contract small:

- `transcribe(path) -> str`

If you swap out MLX later, keep the same API and only replace the backend.
