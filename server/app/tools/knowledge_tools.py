"""Knowledge base tools for searching and fetching documents.

These tools enable agents to:
1. Search the metadata table (DynamoDB) to discover relevant documents
2. Fetch full document content from S3

The knowledge base contains FAR guidance, templates, policies, and regulatory documents
that agents can use to assist with acquisition tasks.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger("eagle.knowledge_tools")

# Configuration
METADATA_TABLE = os.environ.get("METADATA_TABLE", "eagle-document-metadata-dev")
DOCUMENT_BUCKET = os.environ.get("DOCUMENT_BUCKET", "eagle-documents-695681773636-dev")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

# Lazy-loaded clients
_dynamodb = None
_s3 = None


def _get_dynamodb():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
    return _dynamodb


def _get_s3():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3", region_name=AWS_REGION)
    return _s3


# ══════════════════════════════════════════════════════════════════════════════
# Tool Definitions (Anthropic tool_use format)
# ══════════════════════════════════════════════════════════════════════════════

KNOWLEDGE_SEARCH_TOOL = {
    "name": "knowledge_search",
    "description": (
        "Search the acquisition knowledge base for relevant documents, templates, and guidance. "
        "Returns summaries and metadata to help decide which documents to retrieve in full. "
        "Use this to find SOW templates, FAR guidance, policy documents, checklists, etc. "
        "Query by topic, document_type, agent, or keywords."
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
                "description": "Search keywords to match against document keywords",
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
        "Fetch full document content from the knowledge base. "
        "Use after knowledge_search to retrieve a specific document, template, or guidance. "
        "Pass the s3_key from search results."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "s3_key": {
                "type": "string",
                "description": "S3 key from knowledge_search results",
            },
            "document_id": {
                "type": "string",
                "description": "Alternative: document_id from search results (same as s3_key)",
            },
        },
    },
}


# ══════════════════════════════════════════════════════════════════════════════
# Tool Implementations
# ══════════════════════════════════════════════════════════════════════════════

def exec_knowledge_search(
    params: dict[str, Any],
    tenant_id: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Search knowledge base metadata in DynamoDB.

    Args:
        params: Search parameters (topic, document_type, agent, keywords, limit)
        tenant_id: Calling tenant (for logging)
        session_id: Optional session ID (for logging)

    Returns:
        Dict with 'results' array and 'count'
    """
    table = _get_dynamodb().Table(METADATA_TABLE)

    # Extract query parameters
    topic = params.get("topic")
    document_type = params.get("document_type")
    agent = params.get("agent")
    authority_level = params.get("authority_level")
    keywords = params.get("keywords", [])
    limit = min(params.get("limit", 10), 50)  # Cap at 50

    logger.info(
        "knowledge_search: tenant=%s topic=%s doc_type=%s agent=%s limit=%d",
        tenant_id, topic, document_type, agent, limit,
    )

    # Build filter expression for DynamoDB Scan
    # (For ~200 docs, Scan with filters is efficient enough)
    filter_parts = []
    expr_attr_names = {}
    expr_attr_values = {}

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

    # Build scan kwargs
    scan_kwargs = {"Limit": limit * 2}  # Fetch extra to allow for filtering

    if filter_parts:
        scan_kwargs["FilterExpression"] = " AND ".join(filter_parts)
        scan_kwargs["ExpressionAttributeValues"] = expr_attr_values
    if expr_attr_names:
        scan_kwargs["ExpressionAttributeNames"] = expr_attr_names

    try:
        response = table.scan(**scan_kwargs)
        items = response.get("Items", [])
    except ClientError as e:
        logger.error("knowledge_search DynamoDB error: %s", e)
        return {"error": str(e), "results": [], "count": 0}

    # Optional keyword filtering (if keywords provided)
    if keywords:
        keywords_lower = [k.lower() for k in keywords]
        filtered = []
        for item in items:
            item_keywords = [k.lower() for k in item.get("keywords", [])]
            if any(kw in item_keywords or any(kw in ik for ik in item_keywords) for kw in keywords_lower):
                filtered.append(item)
        items = filtered

    # Format results (return summary info, not full content)
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
            "keywords": item.get("keywords", [])[:10],  # Limit keywords in response
            "s3_key": item.get("s3_key", ""),
            "confidence_score": float(item.get("confidence_score", 0)),
        })

    logger.info("knowledge_search: found %d results", len(results))
    return {"results": results, "count": len(results)}


def exec_knowledge_fetch(
    params: dict[str, Any],
    tenant_id: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Fetch full document content from S3.

    Args:
        params: Must contain 's3_key' or 'document_id'
        tenant_id: Calling tenant (for logging)
        session_id: Optional session ID (for logging)

    Returns:
        Dict with 'document_id', 'content', 'truncated', 'content_length'
    """
    s3 = _get_s3()
    key = params.get("s3_key") or params.get("document_id")

    if not key:
        return {"error": "s3_key or document_id required"}

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
