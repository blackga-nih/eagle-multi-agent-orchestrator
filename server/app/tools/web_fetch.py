"""Web fetch tool — fetches a URL and returns its content as clean markdown.

Complements web_search (Nova Web Grounding) by actually reading the full page.
Flow: web_search → get source URLs → web_fetch top results → agent synthesizes.

Uses httpx for HTTP, BeautifulSoup to strip boilerplate, markdownify for HTML→markdown.

Usage:
    from .tools.web_fetch import exec_web_fetch
    result = exec_web_fetch("https://www.gsa.gov/technology/...")
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from markdownify import markdownify as md

logger = logging.getLogger("eagle.web_fetch")

# Limits
MAX_CONTENT_CHARS = 50_000
REQUEST_TIMEOUT = 30  # seconds
MAX_RESPONSE_BYTES = 5_000_000  # 5MB — skip huge pages

# Tags that are boilerplate / not main content
STRIP_TAGS = [
    "script", "style", "nav", "footer", "header", "aside",
    "form", "iframe", "noscript", "svg", "button",
]

# Browser-realistic headers to avoid bot detection.
# Many sites check Sec-Fetch-* and Referer in addition to User-Agent.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Sec-Ch-Ua": '"Chromium";v="131", "Not_A Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Upgrade-Insecure-Requests": "1",
    "Cache-Control": "max-age=0",
}


def _try_cached_fallback(
    client: httpx.Client, url: str
) -> httpx.Response | None:
    """Try Wayback Machine, then Google cache for a 403-blocked URL.

    Returns a successful Response or None if all caches miss.
    """
    # 1. Check Wayback Machine availability (fast JSON check, avoids 404s)
    try:
        avail = client.get(
            f"https://archive.org/wayback/available?url={url}",
            timeout=5,
        )
        snapshots = avail.json().get("archived_snapshots", {})
        closest = snapshots.get("closest", {})
        if closest.get("available") and closest.get("url"):
            wb_resp = client.get(closest["url"])
            if wb_resp.status_code == 200:
                ct = wb_resp.headers.get("content-type", "")
                if "html" in ct:
                    logger.info("web_fetch: Wayback hit for %s", url)
                    return wb_resp
    except Exception:
        pass

    # 2. Google webcache
    try:
        from urllib.parse import quote_plus
        cache_url = (
            "https://webcache.googleusercontent.com"
            f"/search?q=cache:{quote_plus(url)}"
        )
        cache_resp = client.get(cache_url)
        if cache_resp.status_code == 200:
            ct = cache_resp.headers.get("content-type", "")
            snippet = cache_resp.text[:1000]
            is_real = (
                "html" in ct
                and "trouble accessing" not in snippet
                and "<title>Google Search</title>" not in snippet
            )
            if is_real:
                logger.info("web_fetch: Google cache hit for %s", url)
                return cache_resp
    except Exception:
        pass

    return None


def _clean_markdown(text: str) -> str:
    """Collapse excessive whitespace in converted markdown."""
    # Collapse 3+ newlines to 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Collapse runs of whitespace-only lines
    text = re.sub(r"[ \t]+\n", "\n", text)
    # Strip leading/trailing
    return text.strip()


def exec_web_fetch(url: str) -> dict[str, Any]:
    """Fetch a URL and return its content as clean markdown.

    Args:
        url: The URL to fetch.

    Returns:
        dict with keys: url, domain, title, content (markdown), content_length, truncated
        On error: dict with keys: error, url
    """
    # Validate URL
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return {"error": f"Invalid URL scheme: {parsed.scheme}. Use http or https.", "url": url}
    if not parsed.netloc:
        return {"error": "Invalid URL: no domain found.", "url": url}

    domain = parsed.netloc

    try:
        with httpx.Client(
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
            headers=_HEADERS,
            max_redirects=5,
        ) as client:
            response = client.get(url)

            # If 403, retry with Referer header (simulates click from search)
            if response.status_code == 403:
                logger.info("web_fetch 403, retrying with Referer: %s", url)
                retry_headers = {
                    **_HEADERS,
                    "Referer": "https://www.google.com/",
                    "Sec-Fetch-Site": "cross-site",
                }
                response = client.get(url, headers=retry_headers)

            # If still 403 (Cloudflare/bot wall), try cached versions
            if response.status_code == 403:
                logger.info("web_fetch 403 persists, trying caches: %s", url)
                cached = _try_cached_fallback(client, url)
                if cached is not None:
                    response = cached

            response.raise_for_status()

            # Check content type — only process HTML
            content_type = response.headers.get("content-type", "")
            if "text/html" not in content_type and "application/xhtml" not in content_type:
                return {
                    "error": f"Not an HTML page (content-type: {content_type})",
                    "url": url,
                }

            # Check size
            raw = response.text
            if len(raw) > MAX_RESPONSE_BYTES:
                return {"error": "Page too large (>5MB).", "url": url}

    except httpx.TimeoutException:
        logger.warning("web_fetch timeout: %s", url)
        return {"error": "Request timed out.", "url": url}
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        logger.warning("web_fetch HTTP %d: %s", code, url)
        if code == 403:
            return {
                "error": (
                    "HTTP 403 — this site blocks automated access "
                    "(Cloudflare/bot protection) and no cached version "
                    "is available. Use the search snippet from web_search "
                    "instead, or try a different source."
                ),
                "url": url,
            }
        return {"error": f"HTTP {code}", "url": url}
    except httpx.RequestError as e:
        logger.warning("web_fetch request error: %s — %s", url, e)
        return {"error": f"Request failed: {type(e).__name__}", "url": url}

    # Parse HTML
    soup = BeautifulSoup(raw, "html.parser")

    # Extract title
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    # Strip boilerplate tags
    for tag_name in STRIP_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    # Try to find main content area
    main = (
        soup.find("main")
        or soup.find("article")
        or soup.find("div", {"role": "main"})
        or soup.find("div", {"id": "content"})
        or soup.find("div", {"id": "main-content"})
        or soup.body
        or soup
    )

    # Convert to markdown (strip images — they're not useful as text)
    markdown = md(
        str(main),
        heading_style="ATX",
        strip=["img"],
    )

    markdown = _clean_markdown(markdown)
    truncated = len(markdown) > MAX_CONTENT_CHARS

    return {
        "url": url,
        "domain": domain,
        "title": title,
        "content": markdown[:MAX_CONTENT_CHARS],
        "content_length": len(markdown),
        "truncated": truncated,
    }
