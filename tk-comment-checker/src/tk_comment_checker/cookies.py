"""Cookie extraction via yt-dlp for TikTok session auth."""

import json
import logging
import subprocess

logger = logging.getLogger(__name__)


def obtain_cookies(url: str) -> list[dict]:
    """Run yt-dlp once to extract a valid TikTok session (cookies)."""
    logger.debug("Running yt-dlp to extract cookies for: %s", url)
    result = subprocess.run(
        ["yt-dlp", "--dump-json", "--skip-download", url],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        logger.warning("yt-dlp failed (exit %d): %s — proceeding without cookies", result.returncode, result.stderr.strip())
        return []

    data = json.loads(result.stdout)

    cookie_str = next(
        (fmt["cookies"] for fmt in data.get("formats", []) if fmt.get("cookies")),
        "",
    )
    logger.debug("Raw cookie string length: %d chars", len(cookie_str))

    cookies = []
    current: dict = {}
    for part in cookie_str.split(";"):
        part = part.strip()
        if not part or part.startswith(("Domain=", "Path=", "Secure", "Expires=")):
            continue
        if "=" in part:
            if current.get("name"):
                cookies.append(current)
            key, val = part.split("=", 1)
            current = {
                "name": key.strip(),
                "value": val.strip(),
                "domain": ".tiktok.com",
                "path": "/",
                "secure": True,
            }
    if current.get("name"):
        cookies.append(current)

    logger.debug("Parsed %d cookies", len(cookies))
    return cookies
