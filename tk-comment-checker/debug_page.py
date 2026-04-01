"""Debug script: dump page info and screenshot to understand what TikTok loads."""

import json
import subprocess
import sys

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

URL = "https://www.tiktok.com/@uber.gooner/video/7622068566086421781"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/138.0.0.0 Safari/537.36"
)


def get_cookies():
    result = subprocess.run(
        ["yt-dlp", "--dump-json", "--skip-download", URL],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        print("yt-dlp failed:", result.stderr, file=sys.stderr)
        return []
    data = json.loads(result.stdout)
    cookie_str = next(
        (fmt["cookies"] for fmt in data.get("formats", []) if fmt.get("cookies")), ""
    )
    cookies, current = [], {}
    for part in cookie_str.split(";"):
        part = part.strip()
        if not part or part.startswith(("Domain=", "Path=", "Secure", "Expires=")):
            continue
        if "=" in part:
            if current.get("name"):
                cookies.append(current)
            key, val = part.split("=", 1)
            current = {"name": key.strip(), "value": val.strip(), "domain": ".tiktok.com", "path": "/", "secure": True}
    if current.get("name"):
        cookies.append(current)
    return cookies


intercepted = []

def on_response(response):
    if "comment/list" in response.url or "aweme_id" in response.url:
        print(f"[NETWORK] {response.url[:120]}")
        intercepted.append(response.url)

cookies = get_cookies()
print(f"Cookies: {len(cookies)}")

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
    ctx = browser.new_context(user_agent=USER_AGENT, viewport={"width": 1280, "height": 900}, locale="en-US")
    # Try without cookies first to check if base page renders
    page = ctx.new_page()
    Stealth().apply_stealth_sync(page)
    page.on("response", on_response)

    print("Navigating (networkidle, no cookies)...")
    try:
        page.goto(URL, wait_until="networkidle", timeout=45000)
    except Exception as e:
        print(f"goto error: {e}")
    page.wait_for_timeout(3000)

    page.screenshot(path="debug_screenshot.png", full_page=False)
    print("Screenshot saved: debug_screenshot.png")

    # Dump all data-e2e attributes found on page
    e2e_attrs = page.evaluate("""() => {
        return [...document.querySelectorAll('[data-e2e]')]
            .map(el => el.getAttribute('data-e2e'))
    }""")
    print(f"\ndata-e2e attributes on page ({len(e2e_attrs)}):")
    for attr in sorted(set(e2e_attrs)):
        print(f"  {attr}")

    print(f"\nIntercepted URLs: {len(intercepted)}")

    title = page.title()
    current_url = page.url
    html_source = page.content()
    print(f"\nPage title: {title!r}")
    print(f"Final URL: {current_url}")
    print(f"HTML length: {len(html_source)}")
    print(f"HTML preview:\n{html_source[:1000]}")

    browser.close()
