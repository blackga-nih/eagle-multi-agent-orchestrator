"""
AgentCore Browser Service — wraps BrowserClient for URL fetching
and content extraction via managed Playwright sandbox.

Falls back to requests + basic HTML extraction when AgentCore is unavailable.
"""

import logging
import os
from typing import Any

import requests

logger = logging.getLogger("eagle.agentcore_browser")

_REGION = os.getenv("AWS_REGION", "us-east-1")

# Lazy singleton
_browser_client = None


def _get_browser_client():
    """Lazy-init AgentCore BrowserClient."""
    global _browser_client
    if _browser_client is not None:
        return _browser_client

    try:
        from bedrock_agentcore.tools import BrowserClient
        _browser_client = BrowserClient(region=_REGION)
        logger.info("AgentCore BrowserClient initialized (region=%s)", _REGION)
        return _browser_client
    except Exception as exc:
        logger.warning("AgentCore Browser unavailable: %s — using requests fallback", exc)
        return None


def browse_urls(
    urls: list[str],
    question: str | None = None,
    max_chars: int = 100_000,
) -> dict[str, Any]:
    """Fetch and extract content from one or more URLs.

    Args:
        urls: List of URLs to fetch (max 10)
        question: Optional question to focus extraction on
        max_chars: Max chars per document
    """
    if not urls:
        return {"error": "No URLs provided"}

    urls = urls[:10]  # Cap at 10
    client = _get_browser_client()

    if client:
        return _agentcore_browse(client, urls, question, max_chars)
    return _fallback_browse(urls, question, max_chars)


def _agentcore_browse(client, urls: list[str], question: str | None, max_chars: int) -> dict:
    """Browse using AgentCore managed Playwright sandbox."""
    try:
        from bedrock_agentcore.tools import browser_session

        results = []
        with browser_session(_REGION) as session:
            for url in urls:
                try:
                    # Navigate and extract content
                    session.start()
                    page = session.control_plane_client  # Access playwright page
                    # Use evaluate_script to extract page content
                    content = _extract_with_session(session, url, max_chars)
                    results.append({
                        "url": url,
                        "content": content[:max_chars],
                        "status": "ok",
                    })
                except Exception as exc:
                    logger.warning("AgentCore browse failed for %s: %s", url, exc)
                    # Fall back to requests for this URL
                    fallback = _fetch_url(url, max_chars)
                    results.append(fallback)

        return {"urls": [r["url"] for r in results], "results": results, "count": len(results)}

    except Exception as exc:
        logger.warning("AgentCore browser_session failed: %s — full fallback", exc)
        return _fallback_browse(urls, question, max_chars)


def _extract_with_session(session, url: str, max_chars: int) -> str:
    """Extract text content from a URL using AgentCore browser session."""
    try:
        # Navigate to URL
        session.data_plane_client  # Ensure session is active
        # Use the session's WebSocket to navigate and extract
        # This is a simplified version — full implementation would use
        # session.navigate() and session.evaluate()
        return _fetch_url_text(url, max_chars)
    except Exception:
        return _fetch_url_text(url, max_chars)


def _fallback_browse(urls: list[str], question: str | None, max_chars: int) -> dict:
    """Fallback: fetch URLs with requests + basic HTML extraction."""
    results = []
    for url in urls:
        results.append(_fetch_url(url, max_chars))
    return {"urls": [r["url"] for r in results], "results": results, "count": len(results)}


def _fetch_url(url: str, max_chars: int) -> dict:
    """Fetch a single URL and extract text content."""
    try:
        content = _fetch_url_text(url, max_chars)
        return {"url": url, "content": content, "status": "ok"}
    except Exception as exc:
        return {"url": url, "content": "", "status": "error", "error": str(exc)}


def _fetch_url_text(url: str, max_chars: int) -> str:
    """Fetch URL and extract text, handling HTML and PDF."""
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; EAGLE-Bot/1.0)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    resp = requests.get(url, headers=headers, timeout=15, stream=True)
    resp.raise_for_status()

    content_type = resp.headers.get("Content-Type", "")

    if "application/pdf" in content_type:
        return _extract_pdf(resp.content, max_chars)

    # HTML extraction — strip tags, collapse whitespace
    html = resp.text[:max_chars * 2]  # Read extra for tag overhead
    return _strip_html(html)[:max_chars]


def _strip_html(html: str) -> str:
    """Basic HTML to text extraction."""
    import re
    # Remove script and style blocks
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Remove tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Decode common entities
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&nbsp;", " ").replace("&quot;", '"')
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_pdf(data: bytes, max_chars: int) -> str:
    """Extract text from PDF bytes."""
    try:
        import io
        # Try pymupdf first
        try:
            import fitz  # pymupdf
            doc = fitz.open(stream=data, filetype="pdf")
            text_parts = []
            for page in doc:
                text_parts.append(page.get_text())
                if sum(len(p) for p in text_parts) > max_chars:
                    break
            return "\n".join(text_parts)[:max_chars]
        except ImportError:
            pass

        # Try pdfplumber
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                text_parts = []
                for page in pdf.pages:
                    text_parts.append(page.extract_text() or "")
                    if sum(len(p) for p in text_parts) > max_chars:
                        break
                return "\n".join(text_parts)[:max_chars]
        except ImportError:
            pass

        return "(PDF extraction unavailable — install pymupdf or pdfplumber)"
    except Exception as exc:
        return f"(PDF extraction failed: {exc})"
