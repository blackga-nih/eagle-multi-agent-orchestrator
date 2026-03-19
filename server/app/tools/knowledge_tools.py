"""Knowledge base tools for searching and fetching documents.

These tools enable agents to:
1. Search the metadata table (DynamoDB) to discover relevant documents
2. Fetch full document content from S3

The knowledge base contains FAR guidance, templates, policies, and regulatory documents
that agents can use to assist with acquisition tasks.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import boto3
from botocore.exceptions import ClientError
from functools import lru_cache

from ..db_client import get_dynamodb, get_s3, AWS_REGION

logger = logging.getLogger("eagle.knowledge_tools")

# Configuration (separate from main EAGLE table)
METADATA_TABLE = os.environ.get("METADATA_TABLE", "eagle-document-metadata-dev")
DOCUMENT_BUCKET = os.environ.get("DOCUMENT_BUCKET", "eagle-documents-695681773636-dev")
SEARCH_MODEL_ID = os.environ.get(
    "KNOWLEDGE_SEARCH_MODEL", "anthropic.claude-3-haiku-20240307-v1:0"
)


@lru_cache(maxsize=1)
def _get_bedrock_runtime():
    """Get Bedrock runtime client for knowledge search."""
    return boto3.client("bedrock-runtime", region_name=AWS_REGION)


# ══════════════════════════════════════════════════════════════════════════════
# Tool Definitions (Anthropic tool_use format)
# ══════════════════════════════════════════════════════════════════════════════

KNOWLEDGE_SEARCH_TOOL = {
    "name": "knowledge_search",
    "description": (
        "Search the acquisition knowledge base for relevant documents, templates, and guidance. "
        "Returns summaries and metadata to help decide which documents to retrieve in full. "
        "Uses AI-powered semantic matching — describe what you need in natural language via 'query'. "
        "Use topic/document_type/agent filters to narrow the search scope."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": (
                    "Primary topic to filter by: funding, acquisition_packages, contract_types, "
                    "compliance, legal, market_research, socioeconomic, labor, intellectual_property, "
                    "termination, modifications, closeout, performance, subcontracting, general"
                ),
            },
            "document_type": {
                "type": "string",
                "enum": ["regulation", "guidance", "policy", "template", "memo", "checklist", "reference"],
                "description": "Type of document to search for",
            },
            "agent": {
                "type": "string",
                "description": (
                    "Filter by primary agent: supervisor-core, financial-advisor, legal-counselor, "
                    "compliance-strategist, market-intelligence, technical-translator, public-interest-guardian"
                ),
            },
            "authority_level": {
                "type": "string",
                "enum": ["statute", "regulation", "policy", "guidance", "internal"],
                "description": "Filter by authority level",
            },
            "keywords": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Keywords to include in semantic search context",
            },
            "query": {
                "type": "string",
                "description": (
                    "Natural language query describing what you're looking for. "
                    "Can be a question, topic description, case number, citation, or concept. "
                    "Examples: 'IDIQ minimum funding requirements', 'B-302358', "
                    "'what are the rules for sole source justification under SAT'"
                ),
            },
            "limit": {
                "type": "integer",
                "description": "Max results to return (default 10, max 50)",
            },
        },
    },
}

KNOWLEDGE_FETCH_TOOL = {
    "name": "knowledge_fetch",
    "description": (
        "Fetch full document content from the knowledge base by s3_key. "
        "You MUST call knowledge_search first to obtain an s3_key, then pass it here. "
        "If you only have a topic or query, use knowledge_search instead."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "s3_key": {
                "type": "string",
                "description": "The s3_key returned by knowledge_search (required)",
            },
            "query": {
                "type": "string",
                "description": (
                    "If you don't have an s3_key, pass a search query here and "
                    "the tool will automatically search and fetch the best match."
                ),
            },
        },
    },
}


# ══════════════════════════════════════════════════════════════════════════════
# AI-Powered Semantic Search
# ══════════════════════════════════════════════════════════════════════════════

def _ai_rank_documents(
    query: str,
    keywords: list[str],
    items: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    """Use Bedrock Haiku to semantically rank documents against a query.

    Sends the full metadata catalog to the LLM and asks it to pick
    the most relevant documents. With ~350 docs this is ~7K input tokens
    on Haiku — fast (<1s) and cheap (~$0.002/call).

    Returns:
        Ordered list of items ranked by relevance, or empty list on failure.
    """
    if not items:
        return []

    # Build compact catalog: index | doc_id | title | keywords | summary snippet
    catalog_lines = []
    for i, item in enumerate(items):
        doc_id = item.get("document_id", "")
        title = item.get("title", "")
        kws = ", ".join(item.get("keywords", [])[:5])
        summary = (item.get("summary", "") or "")[:150]
        catalog_lines.append(f"{i}|{doc_id}|{title}|{kws}|{summary}")

    catalog = "\n".join(catalog_lines)

    keywords_ctx = f"\nAdditional keywords: {', '.join(keywords)}" if keywords else ""

    prompt = (
        "You are a document relevance matcher for a federal acquisition knowledge base.\n"
        "Given the search query and document catalog, return the indices of the most "
        f"relevant documents, ranked by relevance. Return up to {limit} results.\n\n"
        f"Search query: {query}{keywords_ctx}\n\n"
        "Document catalog (index|document_id|title|keywords|summary):\n"
        f"{catalog}\n\n"
        f"Return ONLY a JSON array of index numbers for the top {limit} most relevant "
        "documents, most relevant first. If no documents are relevant, return [].\n"
        "Example: [5, 12, 3]"
    )

    try:
        bedrock = _get_bedrock_runtime()
        response = bedrock.converse(
            modelId=SEARCH_MODEL_ID,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 256, "temperature": 0},
        )

        result_text = response["output"]["message"]["content"][0]["text"].strip()
        # Extract JSON array — handle cases where LLM wraps in markdown
        if "```" in result_text:
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]
            result_text = result_text.strip()

        indices = json.loads(result_text)
        if not isinstance(indices, list):
            logger.warning("knowledge_search AI: unexpected response type: %s", type(indices))
            return []

        ranked = [items[i] for i in indices if isinstance(i, int) and 0 <= i < len(items)]
        logger.info(
            "knowledge_search AI: query='%s' matched %d/%d docs",
            query, len(ranked), len(items),
        )
        return ranked

    except (ClientError, json.JSONDecodeError, KeyError, IndexError) as e:
        logger.warning("knowledge_search AI ranking failed, falling back: %s", e)
        return []


def _deterministic_match(
    query: str,
    keywords: list[str],
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Fallback deterministic matching when AI ranking is unavailable."""
    result = items

    # Keyword filtering
    if keywords:
        keywords_lower = [k.lower() for k in keywords]
        filtered = []
        for item in result:
            item_keywords = [k.lower() for k in item.get("keywords", [])]
            if any(
                kw in item_keywords or any(kw in ik for ik in item_keywords)
                for kw in keywords_lower
            ):
                filtered.append(item)
        result = filtered

    # Free-text query filtering
    if query:
        query_lower = query.lower()
        query_terms = query_lower.split()
        filtered = []
        for item in result:
            doc_id = item.get("document_id", "").lower()
            title = item.get("title", "").lower()
            summary = item.get("summary", "").lower()
            filename = item.get("filename", "").lower()
            keywords_text = " ".join(item.get("keywords", [])).lower()
            searchable = f"{doc_id} {filename} {title} {summary} {keywords_text}"
            if query_lower in searchable or all(t in searchable for t in query_terms):
                filtered.append(item)
        result = filtered

    return result


# ══════════════════════════════════════════════════════════════════════════════
# Tool Implementations
# ══════════════════════════════════════════════════════════════════════════════

def exec_knowledge_search(
    params: dict[str, Any],
    tenant_id: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Search knowledge base metadata in DynamoDB with AI-powered ranking.

    Steps:
    1. Scan DynamoDB with exact-match filters (topic, document_type, etc.)
    2. If query or keywords provided, use LLM to semantically rank results
    3. Fall back to deterministic matching if LLM call fails
    """
    table = get_dynamodb().Table(METADATA_TABLE)

    # Extract query parameters
    topic = params.get("topic")
    document_type = params.get("document_type")
    agent = params.get("agent")
    authority_level = params.get("authority_level")
    keywords = params.get("keywords", [])
    query = params.get("query")
    limit = min(params.get("limit", 10), 50)

    logger.info(
        "knowledge_search: tenant=%s query=%s topic=%s doc_type=%s agent=%s limit=%d",
        tenant_id, query, topic, document_type, agent, limit,
    )

    # Build DynamoDB filter for exact-match attributes
    filter_parts = []
    expr_attr_names: dict[str, str] = {}
    expr_attr_values: dict[str, Any] = {}

    if topic:
        filter_parts.append("primary_topic = :topic")
        expr_attr_values[":topic"] = topic

    if document_type:
        filter_parts.append("document_type = :doc_type")
        expr_attr_values[":doc_type"] = document_type

    if agent:
        filter_parts.append("primary_agent = :agent")
        expr_attr_values[":agent"] = agent

    if authority_level:
        filter_parts.append("authority_level = :auth_level")
        expr_attr_values[":auth_level"] = authority_level

    # Full-table scan with pagination (no Limit — table is small)
    scan_kwargs: dict[str, Any] = {}
    if filter_parts:
        scan_kwargs["FilterExpression"] = " AND ".join(filter_parts)
        scan_kwargs["ExpressionAttributeValues"] = expr_attr_values
    if expr_attr_names:
        scan_kwargs["ExpressionAttributeNames"] = expr_attr_names

    try:
        items: list[dict[str, Any]] = []
        response = table.scan(**scan_kwargs)
        items.extend(response.get("Items", []))
        while "LastEvaluatedKey" in response:
            scan_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
            response = table.scan(**scan_kwargs)
            items.extend(response.get("Items", []))
        logger.info("knowledge_search: scanned %d total items", len(items))
    except ClientError as e:
        logger.error("knowledge_search DynamoDB error: %s", e)
        return {"error": str(e), "results": [], "count": 0}

    # Semantic ranking via AI when query or keywords are provided
    if query or keywords:
        search_query = query or ""
        if keywords and not query:
            search_query = " ".join(keywords)

        ranked_items = _ai_rank_documents(search_query, keywords, items, limit)
        if ranked_items:
            items = ranked_items
        else:
            # AI failed — fall back to deterministic matching
            logger.info("knowledge_search: using deterministic fallback")
            items = _deterministic_match(query or "", keywords, items)

    # Format results
    results = []
    for item in items[:limit]:
        results.append({
            "document_id": item.get("document_id", ""),
            "title": item.get("title", ""),
            "summary": item.get("summary", ""),
            "document_type": item.get("document_type", ""),
            "primary_topic": item.get("primary_topic", ""),
            "primary_agent": item.get("primary_agent", ""),
            "authority_level": item.get("authority_level", ""),
            "complexity_level": item.get("complexity_level", ""),
            "key_requirements": item.get("key_requirements", []),
            "keywords": item.get("keywords", [])[:10],
            "s3_key": item.get("s3_key", ""),
            "confidence_score": float(item.get("confidence_score", 0)),
        })

    logger.info("knowledge_search: returning %d results", len(results))
    return {"results": results, "count": len(results)}


def exec_knowledge_fetch(
    params: dict[str, Any],
    tenant_id: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Fetch full document content from S3.

    If s3_key is not provided but a query is, automatically runs
    knowledge_search first and fetches the top result.
    """
    s3 = get_s3()
    key = params.get("s3_key") or params.get("document_id")

    # Auto-search when called without a key but with a query
    if not key:
        query = params.get("query")
        if query:
            logger.info("knowledge_fetch: no s3_key, auto-searching for '%s'", query)
            search_result = exec_knowledge_search(
                {"query": query, "limit": 1}, tenant_id, session_id,
            )
            results = search_result.get("results", [])
            if results:
                key = results[0].get("s3_key") or results[0].get("document_id")
                logger.info("knowledge_fetch: auto-search found key=%s", key)

    if not key:
        return {
            "error": "No document found. Provide s3_key from knowledge_search, "
            "or pass a 'query' to auto-search.",
        }

    logger.info("knowledge_fetch: tenant=%s key=%s", tenant_id, key)

    try:
        response = s3.get_object(Bucket=DOCUMENT_BUCKET, Key=key)
        raw_content = response["Body"].read()

        # Try to decode as text
        try:
            content = raw_content.decode("utf-8")
        except UnicodeDecodeError:
            content = raw_content.decode("latin-1", errors="replace")

        content_length = len(content)
        max_length = 50000  # 50KB limit to avoid overwhelming context

        return {
            "document_id": key,
            "content": content[:max_length],
            "truncated": content_length > max_length,
            "content_length": content_length,
        }

    except s3.exceptions.NoSuchKey:
        logger.warning("knowledge_fetch: document not found: %s", key)
        return {"error": f"Document not found: {key}"}
    except ClientError as e:
        logger.error("knowledge_fetch S3 error: %s", e)
        return {"error": str(e)}
