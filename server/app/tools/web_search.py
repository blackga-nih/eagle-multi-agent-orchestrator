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

from botocore.config import Config
from botocore.exceptions import ClientError, ReadTimeoutError

from app.aws_session import get_shared_session, resolved_credential_path

logger = logging.getLogger("eagle.web_search")

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
WEB_SEARCH_MODEL_ID = os.environ.get("WEB_SEARCH_MODEL", "us.amazon.nova-2-lite-v1:0")

# Lazy-loaded client
_bedrock_runtime = None


def _get_client():
    """Build the bedrock-runtime client via the shared AWS session.

    Using ``get_shared_session()`` instead of a bare ``boto3.client(...)``
    ensures Nova grounding calls inherit the same credential path as the
    rest of the backend — ``AWS_PROFILE=eagle`` locally (SSO), ECS task
    role in production, OIDC-assumed role in CI.  This is the fix for
    the ``400 empty body`` symptom that happens when the ``[default]``
    profile has stale SSO creds: we now resolve through the eagle
    profile explicitly, not the implicit default chain.
    """
    global _bedrock_runtime
    if _bedrock_runtime is None:
        # AWS Nova web grounding typically takes 10-30s.  Cap at 60s to
        # prevent 5-minute stalls (observed 305-309s with previous 300s limit).
        # No retry — the agent can reformulate and retry if needed.
        session = get_shared_session()
        _bedrock_runtime = session.client(
            "bedrock-runtime",
            region_name=AWS_REGION,
            config=Config(read_timeout=60, retries={"max_attempts": 1}),
        )
        logger.info(
            "web_search: bedrock-runtime client built via %s",
            resolved_credential_path(),
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
            results.append(
                {
                    "url": url,
                    "domain": web.get("domain", ""),
                    "snippet": last_text[:200] if last_text else "",
                }
            )
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


# Multi-word phrases — substring match is safe because the phrase itself is
# specific enough that accidental substring matches are impossible.
_MARKET_RESEARCH_PHRASES = (
    "market research", "market survey", "vendor comparison",
    "competitive analysis", "product comparison", "market analysis",
    "service provider", "who offers", "what companies", "what vendors",
    "which vendors", "which providers", "available on", "gsa schedule",
    "gsa advantage", "google cloud", "machine learning",
)

# Single-word keywords — matched on WORD BOUNDARIES only so that short words
# like "ai", "aws", "saas" don't match inside unrelated words (e.g. "fair"
# contains "ai", "exhaustive" contains "aws"). These must never match inside
# a larger word.
_MARKET_RESEARCH_WORDS = frozenset({
    # Generic commercial signals
    "vendor", "vendors", "pricing", "price", "prices", "industry",
    "commercial", "manufacturer", "suppliers", "supplier", "products",
    "product", "subscription", "license", "licensing", "quote", "quotation",
    "catalog", "providers",
    # Cloud / infrastructure / software
    "cloud", "hosting", "saas", "iaas", "paas", "infrastructure",
    "platform", "software", "hardware", "equipment", "fedramp",
    # Specific vendor brand names — matched as whole words
    "aws", "azure", "oracle", "microsoft", "ibm", "zeiss", "illumina",
    # Product / technology words users search for
    "microscope", "laptop", "computer", "server", "storage", "database",
    "monitoring", "analytics",
})

# Pre-compiled word-boundary regex for the single-word set. Using a single
# alternation keeps the match O(n) per query rather than running one regex
# per keyword.
import re as _re  # noqa: E402 — placed here to scope to this block
_MARKET_RESEARCH_WORD_RE = _re.compile(
    r"\b(?:" + "|".join(_re.escape(w) for w in _MARKET_RESEARCH_WORDS) + r")\b",
    _re.IGNORECASE,
)


def _is_market_research(query: str) -> bool:
    """Return True if the query is for market research purposes.

    When True, the query is sent to Nova grounding WITHOUT a ``site:.gov``
    restriction so the agent can find vendor/pricing/product data from
    commercial sources. Policy/regulation queries still get .gov-scoped to
    keep the results authoritative.

    Uses substring matching for multi-word phrases (they're specific enough
    that false positives are impossible) and word-boundary regex matching
    for single-word keywords (so "ai" doesn't match "fair", "aws" doesn't
    match "always", etc.).
    """
    q = query.lower()
    if any(phrase in q for phrase in _MARKET_RESEARCH_PHRASES):
        return True
    return bool(_MARKET_RESEARCH_WORD_RE.search(query))


def _run_nova_grounding(
    search_query: str, max_sources: int
) -> tuple[str, list[dict[str, str]]]:
    """Call Nova and return ``(answer, sources)``.

    Split out from ``exec_web_search`` so the outer function can retry the
    query with a different scoping strategy when the first pass comes back
    empty. Raises ``ClientError`` / ``ReadTimeoutError`` / parse errors like
    the caller expects — those are handled once at the outer level.
    """
    response = _get_client().converse(
        modelId=WEB_SEARCH_MODEL_ID,
        messages=[{"role": "user", "content": [{"text": search_query}]}],
        toolConfig={
            "tools": [{"systemTool": {"name": "nova_grounding"}}],
        },
    )
    content_blocks = (
        response.get("output", {}).get("message", {}).get("content", [])
    )

    answer_parts: list[str] = []
    sources: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    last_text = ""

    for block in content_blocks:
        if "text" in block:
            last_text = block["text"]
            answer_parts.append(last_text)
        if "citationsContent" in block:
            for src in _extract_citations(block, last_text):
                if src["url"] not in seen_urls and len(sources) < max_sources:
                    seen_urls.add(src["url"])
                    sources.append(src)

    return "\n".join(answer_parts).strip(), sources


def exec_web_search(query: str, max_sources: int = 10) -> dict[str, Any]:
    """Call Nova 2 Lite with nova_grounding to perform a web search.

    Scoping strategy:
      1. Policy/regulation queries → ``site:.gov`` restriction (keeps
         answers authoritative for FAR/DFARS/OMB questions).
      2. Market-research queries → full web (vendor/pricing/product data).
      3. If a .gov-scoped pass returns zero sources, **retry** the query
         without the restriction. This prevents the classic demo failure
         where a legitimate research query (e.g. "FedRAMP High cloud
         hosting") returns nothing and the LLM paraphrases the empty
         response as "Sorry, I can't access the web."

    Args:
        query: The search query string.
        max_sources: Maximum number of source citations to return.

    Returns:
        dict with keys: query, answer, sources, source_count
        On error: dict with keys: error, query, detail
    """
    gov_scoped = not _is_market_research(query)
    search_query = f"{query} site:.gov" if gov_scoped else query
    if gov_scoped:
        logger.info("web_search: .gov scoped query — '%s'", search_query[:120])

    try:
        answer, sources = _run_nova_grounding(search_query, max_sources)

        # If .gov scoping found nothing, retry with full web. Federal
        # acquisition research often needs commercial sources (vendors,
        # product catalogs, pricing) that aren't on .gov domains.
        if gov_scoped and not sources:
            logger.info(
                "web_search: .gov scoped query returned 0 sources; retrying full web"
            )
            answer, sources = _run_nova_grounding(query, max_sources)
            gov_scoped = False  # report the actual scope used

        # Still empty after both attempts — return a STRUCTURED error so the
        # LLM surfaces the actual failure mode instead of paraphrasing as
        # "Sorry, I can't access the web." The detail field gives the agent
        # something concrete to say to the user.
        if not sources and not answer:
            logger.warning("web_search: both attempts returned empty for '%s'", query[:120])
            return {
                "error": "no_results",
                "query": query,
                "detail": (
                    "Nova web grounding returned no results for this query. "
                    "Try rephrasing with more specific terms, adding vendor "
                    "names, or breaking the question into smaller parts."
                ),
            }

        # Auto-fetch top source pages so the agent gets full content
        # without needing separate web_fetch calls.
        auto_fetch_count = int(os.environ.get("WEB_SEARCH_AUTO_FETCH", "3"))
        fetch_urls = [s["url"] for s in sources[:auto_fetch_count]]
        fetched_pages = _auto_fetch_pages(fetch_urls)

        # Annotate sources with fetched content
        for src in sources:
            page = fetched_pages.get(src["url"])
            if page:
                src["page_content"] = page

        # Build list of remaining URLs not yet fetched
        unfetched = [s["url"] for s in sources[auto_fetch_count:]]

        result: dict[str, Any] = {
            "query": query,
            "answer": answer,
            "sources": sources,
            "source_count": len(sources),
            "pages_fetched": len(fetched_pages),
            "gov_scoped": gov_scoped,
        }
        if unfetched:
            result["unfetched_urls"] = unfetched
        return result

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_msg = e.response.get("Error", {}).get("Message", str(e))
        logger.error("web_search ClientError [%s]: %s", error_code, e)
        return {
            "error": "bedrock_api_error",
            "query": query,
            "detail": (
                f"Bedrock {error_code}: {error_msg}. This is an AWS "
                "infrastructure issue, NOT a lack of web access — the tool "
                "is wired up correctly but the underlying Nova grounding "
                "call failed. Surface the error code to the user and ask "
                "them to retry shortly."
            ),
            "error_code": error_code,
        }
    except ReadTimeoutError:
        logger.error("web_search timeout for query: %s", query)
        return {
            "error": "timeout",
            "query": query,
            "detail": (
                "Web search exceeded the 60s read timeout. The Nova grounding "
                "call was still running when the client gave up. Try breaking "
                "the question into smaller, more specific queries."
            ),
        }
    except (KeyError, TypeError, IndexError) as e:
        logger.error("web_search parse error: %s", e)
        return {
            "error": "parse_error",
            "query": query,
            "detail": (
                f"Failed to parse Nova grounding response: {e}. This is a "
                "data-shape issue in the tool, not a web-access failure."
            ),
        }
