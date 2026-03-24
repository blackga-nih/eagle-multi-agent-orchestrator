"""Web search tool using Amazon Nova Web Grounding (nova_grounding systemTool).

Calls Nova 2 Lite via Bedrock Converse API with the nova_grounding system tool
to perform real-time web searches. Returns structured results with source citations.

After retrieving search results, auto-fetches the top N source pages in parallel
so the calling agent receives full page content — not just snippets — without
needing to make separate web_fetch calls.

AWS docs: https://docs.aws.amazon.com/nova/latest/nova2-userguide/web-grounding.html

Key implementation notes (from AWS docs):
  - Use Config(read_timeout=300) — web grounding performs multiple searches
  - Response contains interleaved text + citationsContent blocks
  - text and citationsContent may appear in the SAME content block or as separate blocks
  - citationsContent.citations[].location.web.{url, domain}
  - Requires bedrock:InvokeTool on system-tool/amazon.nova_grounding (separate from InvokeModel)

Usage:
    from .tools.web_search import exec_web_search
    result = exec_web_search("current GSA IT schedule rates")
"""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, ReadTimeoutError

logger = logging.getLogger("eagle.web_search")

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
WEB_SEARCH_MODEL_ID = os.environ.get(
    "WEB_SEARCH_MODEL", "us.amazon.nova-2-lite-v1:0"
)

# Lazy-loaded client
_bedrock_runtime = None


def _get_client():
    global _bedrock_runtime
    if _bedrock_runtime is None:
        # Extended timeout per AWS docs — web grounding performs multiple
        # searches and can take 10-30s for complex queries.
        _bedrock_runtime = boto3.client(
            "bedrock-runtime",
            region_name=AWS_REGION,
            config=Config(read_timeout=300, retries={"max_attempts": 2}),
        )
    return _bedrock_runtime


def _extract_citations(block: dict, last_text: str) -> list[dict]:
    """Extract citations from a citationsContent block.

    Handles both formats seen in the wild:
      - {"citationsContent": {"citations": [...]}}   (standard)
      - {"citationsContent": [...]}                    (simplified)
    """
    raw = block.get("citationsContent", {})
    if isinstance(raw, list):
        citations = raw
    elif isinstance(raw, dict):
        citations = raw.get("citations", [])
    else:
        return []

    results = []
    for citation in citations:
        location = citation.get("location", {})
        web = location.get("web", {})
        url = web.get("url", "")
        if url:
            results.append({
                "url": url,
                "domain": web.get("domain", ""),
                "snippet": last_text[:200] if last_text else "",
            })
    return results


def _auto_fetch_pages(
    urls: list[str],
    max_chars: int = 3000,
) -> dict[str, str]:
    """Fetch multiple URLs in parallel, returning truncated page content.

    Returns a dict of {url: page_content_string}. Failed fetches are
    silently skipped.
    """
    if not urls:
        return {}

    from .web_fetch import exec_web_fetch

    results: dict[str, str] = {}

    def _fetch_one(url: str) -> tuple[str, str | None]:
        try:
            data = exec_web_fetch(url)
            content = data.get("content", "")
            if content and not data.get("error"):
                truncated = content[:max_chars]
                if len(content) > max_chars:
                    truncated += "\n\n[... truncated — call web_fetch for full page]"
                return url, truncated
        except Exception:
            pass
        return url, None

    with ThreadPoolExecutor(max_workers=min(len(urls), 5)) as pool:
        futures = {pool.submit(_fetch_one, u): u for u in urls}
        for future in as_completed(futures):
            try:
                url, content = future.result()
                if content:
                    results[url] = content
            except Exception:
                pass

    return results


def exec_web_search(query: str, max_sources: int = 10) -> dict[str, Any]:
    """Call Nova 2 Lite with nova_grounding to perform a web search.

    Args:
        query: The search query string.
        max_sources: Maximum number of source citations to return.

    Returns:
        dict with keys: query, answer, sources, source_count
        On error: dict with keys: error, query
    """
    try:
        response = _get_client().converse(
            modelId=WEB_SEARCH_MODEL_ID,
            messages=[{"role": "user", "content": [{"text": query}]}],
            toolConfig={
                "tools": [{"systemTool": {"name": "nova_grounding"}}],
            },
        )

        # Parse the response content blocks.
        # Nova returns interleaved text + citationsContent blocks.
        # text and citationsContent may be in the SAME block or SEPARATE blocks.
        content_blocks = response.get("output", {}).get("message", {}).get("content", [])

        answer_parts: list[str] = []
        sources: list[dict[str, str]] = []
        seen_urls: set[str] = set()
        last_text = ""

        for block in content_blocks:
            # Extract text from this block
            if "text" in block:
                last_text = block["text"]
                answer_parts.append(last_text)

            # Extract citations — check EVERY block (not elif)
            # because text and citationsContent can coexist in the same block
            if "citationsContent" in block:
                for src in _extract_citations(block, last_text):
                    if src["url"] not in seen_urls and len(sources) < max_sources:
                        seen_urls.add(src["url"])
                        sources.append(src)

        answer = "\n".join(answer_parts).strip()

        # Auto-fetch top source pages so the agent gets full content
        # without needing separate web_fetch calls.
        auto_fetch_count = int(
            os.environ.get("WEB_SEARCH_AUTO_FETCH", "3")
        )
        fetch_urls = [s["url"] for s in sources[:auto_fetch_count]]
        fetched_pages = _auto_fetch_pages(fetch_urls)

        # Annotate sources with fetched content
        for src in sources:
            page = fetched_pages.get(src["url"])
            if page:
                src["page_content"] = page

        # Build list of remaining URLs not yet fetched
        unfetched = [
            s["url"] for s in sources[auto_fetch_count:]
        ]

        result: dict[str, Any] = {
            "query": query,
            "answer": answer,
            "sources": sources,
            "source_count": len(sources),
            "pages_fetched": len(fetched_pages),
        }
        if unfetched:
            result["unfetched_urls"] = unfetched
            result["_instruction"] = (
                f"The top {auto_fetch_count} source pages were auto-fetched "
                f"(see page_content in sources). Call web_fetch on the "
                f"remaining URLs above if you need more detail."
            )
        return result

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        logger.error("web_search ClientError [%s]: %s", error_code, e)
        return {"error": f"Bedrock API error: {error_code}", "query": query}
    except ReadTimeoutError:
        logger.error("web_search timeout for query: %s", query)
        return {"error": "Web search timed out. Try a simpler query.", "query": query}
    except (KeyError, TypeError, IndexError) as e:
        logger.error("web_search parse error: %s", e)
        return {"error": f"Failed to parse web search response: {e}", "query": query}
