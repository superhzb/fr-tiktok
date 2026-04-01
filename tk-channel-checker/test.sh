#!/usr/bin/env bash
# Run tk-channel-checker for each URL in channel.md and save output as JSON.

set -euo pipefail

# Activate venv if not already active
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  source "$SCRIPT_DIR/.venv/bin/activate"
fi

INPUT="channel.md"
OUTPUT_DIR="test_output"
mkdir -p "$OUTPUT_DIR"

while IFS= read -r url || [[ -n "$url" ]]; do
  [[ -z "$url" || "$url" == \#* ]] && continue

  # Derive a filename from the @username in the URL
  username=$(echo "$url" | grep -oE '@[^?/]+' | head -1 | tr -d '@')
  outfile="$OUTPUT_DIR/${username:-channel}.json"

  echo "Fetching $url -> $outfile"
  python -m tk_channel_checker.cli "$url" > "$outfile"
  echo "Saved $outfile"
done < "$INPUT"
