import json
from mlx_audio.stt import load

# Load forced aligner
model = load("mlx-community/Qwen3-ForcedAligner-0.6B-8bit")

# Align text to audio (model.align is also available as an alias)
with open("STT_test/output-large-v3.txt", "r") as f:
    text = f.read()

result = model.generate(
    audio="test_audio/awkward-urologist-appointment.mp3",
    text=text
)

with open("output.json", "w") as f:
    json.dump([{"start": item.start_time, "end": item.end_time, "text": item.text} for item in result], f, indent=2)

print("Saved to output.json")