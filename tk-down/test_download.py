"""
Quick integration test: download the URL from link.md and print the result.
Run from the tk-down directory with the local venv active.
"""
import logging
import sys
from pathlib import Path

logging.basicConfig(
    format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    level=logging.DEBUG,
    stream=sys.stderr,
)

LINK_FILE = Path(__file__).parent / "link.md"
url = LINK_FILE.read_text().strip().strip('"')

print(f"URL: {url}", flush=True)

from tk_down import download

result = download(url)
print(f"SAVED: {result}", flush=True)
