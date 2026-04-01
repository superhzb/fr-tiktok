"""Test merge_srt using aligned.json and punctuated.json, saves output to output.srt."""

import json
import pathlib

from tk_srt_merger.merger import merge_srt

BASE = pathlib.Path(__file__).parent

aligned = json.loads((BASE / "aligned.json").read_text())
punct_text = json.loads((BASE / "punctuated.json").read_text())["text"]

srt = merge_srt(aligned, punct_text)

output_path = BASE / "output.srt"
output_path.write_text(srt)
print(srt)
print(f"\nSaved to {output_path}")
