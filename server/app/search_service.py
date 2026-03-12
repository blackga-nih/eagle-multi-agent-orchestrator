"""
Web Search Service — Brave Search API + GovInfo API.

Provides web, news, and government document search
with per-tenant rate limiting.
"""

import logging
import os
import time
from typing import Any

import requests

logger = logging.getLogger("eagle.search")

_BRAVE_API_KEY = os.getenv("BRAVE_SEARCH_API_KEY", "")
_GOVINFO_API_KEY = os.getenv("DATA_GOV_API_KEY", "")

_BRAVE_WEB_URL = "https://api.search.brave.com/res/v1/web/search"
_BRAVE_NEWS_URL = "https://api.search.brave.com/res/v1/news/search"
_GOVINFO_URL = "https://api.govinfo.gov/search"

# Simple per-tenant rate limiting (requests per minute)
_rate_limits: dict[str, list[float]] = {}
_RATE_LIMIT_RPM = 30


def _check_rate_limit(tenant_id: str) -> bool:
    """Return True if under rate limit, False if exceeded."""
    now = time.time()
    window = _rate_limits.setdefault(tenant_id, [])
    # Purge entries older than 60s
    _rate_limits[tenant_id] = [t for t in window if now - t < 60]
    if len(_rate_limits[tenant_id]) >= _RATE_LIMIT_RPM:
        return False
    _rate_limits[tenant_id].append(now)
    return True


def web_search(
    query: str,
    search_type: str = "web",
    tenant_id: str = "demo-tenant",
    count: int = 10,
) -> dict[str, Any]:
    """Execute a web search.

    Args:
        query: Search query text
        search_type: "web" | "news" | "gov"
        tenant_id: For rate limiting
        count: Max results to return
    """
    if not _check_rate_limit(tenant_id):
        return {"error": "Rate limit exceeded. Try again in a minute.", "query": query}

    if search_type == "gov":
        return _search_govinfo(query, count)
    elif search_type == "news":
        return _search_brave(query, count, news=True)
    else:
        return _search_brave(query, count, news=False)


def _search_brave(query: str, count: int, news: bool = False) -> dict:
    """Search via Brave Search API."""
    if not _BRAVE_API_KEY:
        return {"error": "BRAVE_SEARCH_API_KEY not configured", "query": query}

    url = _BRAVE_NEWS_URL if news else _BRAVE_WEB_URL
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": _BRAVE_API_KEY,
    }
    params = {"q": query, "count": min(count, 20)}

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if news:
            results = []
            for item in data.get("results", [])[:count]:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "description": item.get("description", ""),
                    "age": item.get("age", ""),
                    "source": item.get("meta_url", {}).get("hostname", ""),
                })
            return {"search_type": "news", "query": query, "results": results, "count": len(results)}
        else:
            results = []
            for item in data.get("web", {}).get("results", [])[:count]:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "description": item.get("description", ""),
                    "age": item.get("age", ""),
                })
            return {"search_type": "web", "query": query, "results": results, "count": len(results)}

    except requests.RequestException as exc:
        logger.error("Brave search failed: %s", exc)
        return {"error": f"Search failed: {str(exc)}", "query": query}


def _search_govinfo(query: str, count: int) -> dict:
    """Search via GovInfo API for federal documents."""
    if not _GOVINFO_API_KEY:
        return {"error": "DATA_GOV_API_KEY not configured", "query": query}

    try:
        resp = requests.post(
            _GOVINFO_URL,
            headers={"Content-Type": "application/json"},
            params={"api_key": _GOVINFO_API_KEY},
            json={
                "query": query,
                "pageSize": min(count, 20),
                "offsetMark": "*",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        for pkg in data.get("results", [])[:count]:
            results.append({
                "title": pkg.get("title", ""),
                "packageId": pkg.get("packageId", ""),
                "dateIssued": pkg.get("dateIssued", ""),
                "category": pkg.get("category", ""),
                "url": pkg.get("packageLink", ""),
            })
        return {"search_type": "gov", "query": query, "results": results, "count": len(results)}

    except requests.RequestException as exc:
        logger.error("GovInfo search failed: %s", exc)
        return {"error": f"GovInfo search failed: {str(exc)}", "query": query}
