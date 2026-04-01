"""HTTP-only ssstik.io fallback (no browser required)."""
import re
import logging
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

SSSTIK_URL = "https://ssstik.io/"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
_BASE_HEADERS = {
    "User-Agent": _UA,
    "Referer": SSSTIK_URL,
}


def _scrape_config() -> dict:
    """Fetch the ssstik.io homepage and extract s_n, s_furl, s_tt."""
    logger.debug("Fetching ssstik.io homepage for config values")
    with httpx.Client(headers=_BASE_HEADERS, follow_redirects=True, timeout=15) as client:
        resp = client.get(SSSTIK_URL)
        resp.raise_for_status()
        html = resp.text

    def _find(key: str) -> str:
        m = re.search(rf"{re.escape(key)}\s*=\s*[\"']([^\"']+)[\"']", html)
        if not m:
            raise RuntimeError(f"ssstik config key '{key}' not found in homepage")
        return m.group(1)

    config = {
        "host": _find("s_n"),
        "form_path": _find("s_furl"),
        "token": _find("s_tt"),
    }
    logger.debug("ssstik config: %s", config)
    return config


def _post_for_result(config: dict, tiktok_url: str) -> BeautifulSoup:
    """POST the TikTok URL to ssstik and return parsed HTML."""
    post_url = f"https://{config['host']}/{config['form_path'].lstrip('/')}?url=dl"
    logger.debug("POST %s", post_url)

    headers = {
        **_BASE_HEADERS,
        "HX-Request": "true",
        "HX-Current-URL": SSSTIK_URL,
        "HX-Target": "target",
    }
    data = {
        "id": tiktok_url,
        "locale": "en",
        "tt": config["token"],
    }

    with httpx.Client(headers=headers, follow_redirects=True, timeout=30) as client:
        resp = client.post(post_url, data=data)
        resp.raise_for_status()

    return BeautifulSoup(resp.text, "html.parser")


def _parse_result(soup: BeautifulSoup) -> str:
    """Extract the non-HD without-watermark download URL from parsed SSSTik HTML."""
    for a in soup.find_all("a", class_="download_link"):
        classes = " ".join(a.get("class", []))
        text = a.get_text(strip=True)
        if (
            text == "Without watermark"
            and "without_watermark" in classes
            and "quality-best" not in classes
            and "without_watermark_hd" not in classes
        ):
            url = a.get("href")
            logger.debug("Download URL: %s", url)
            return url

    raise RuntimeError("No non-HD 'Without watermark' link in SSSTik response")


def _filename_from_response(resp: httpx.Response, fallback: str) -> str:
    """Pull filename from Content-Disposition header, or use fallback."""
    cd = resp.headers.get("content-disposition", "")
    m = re.search(r'filename\*?=["\']?(?:UTF-8\'\')?([^"\';\r\n]+)', cd, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # Fall back to last path segment of the URL
    path = resp.url.path
    name = path.rstrip("/").rsplit("/", 1)[-1]
    return name or fallback


def download_via_http(tiktok_url: str, output_path: Path) -> str:
    """
    Pure-HTTP fallback: scrape ssstik config, POST for download link, stream file.

    Returns the filename from the download response. Raises on failure.
    """
    config = _scrape_config()
    soup = _post_for_result(config, tiktok_url)
    download_url = _parse_result(soup)

    logger.debug("Downloading file from %s", download_url)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    suggested: str = f"ssstik_{output_path.stem}.mp4"
    with httpx.Client(headers=_BASE_HEADERS, follow_redirects=True, timeout=120) as client:
        with client.stream("GET", download_url) as resp:
            resp.raise_for_status()
            suggested = _filename_from_response(resp, suggested)
            with open(output_path, "wb") as fh:
                for chunk in resp.iter_bytes(chunk_size=8192):
                    fh.write(chunk)

    size = output_path.stat().st_size if output_path.exists() else 0
    if size == 0:
        output_path.unlink(missing_ok=True)
        raise RuntimeError("Downloaded file is empty")

    logger.debug("Saved %d bytes to %s (filename: %s)", size, output_path, suggested)
    return suggested
