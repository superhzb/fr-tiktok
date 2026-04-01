#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

INPUT="test_input.json"
OUTPUT="test_output.json"
VENV="venv"

# Create venv if needed
if [ ! -d "$VENV" ]; then
    echo "Creating venv..."
    python3 -m venv "$VENV"
fi

# Install package in editable mode
echo "Installing tk-aligner..."
"$VENV/bin/pip" install -q -e .

# Run alignment
echo "Running alignment..."
"$VENV/bin/tk-aligner" \
    "$INPUT" \
    --output "$OUTPUT" \
    --debug

echo ""
echo "Output saved to $OUTPUT"
echo "First 3 segments:"
"$VENV/bin/python" -c "
import json
data = json.load(open('$OUTPUT'))
for seg in data[:5]:
    print(f\"  {seg['start']:.3f}s – {seg['end']:.3f}s  {seg['text']!r}\")
print(f'  ... ({len(data)} total segments)')
"
