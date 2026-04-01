from mlx_audio.stt import load

model = load("mlx-community/whisper-large-v3-asr-4bit")

result = model.generate("qwen3-asr/awkward-urologist-appointment.mp3")
print(result.text)

with open("output.txt", "w") as f:
    f.write(result.text)

print("Saved to output.txt")
