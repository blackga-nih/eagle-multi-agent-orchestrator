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
from botocore.exceptions import BotoCoreError, ClientError
from functools import lru_cache

from ..db_client import get_dynamodb, get_s3, AWS_REGION

logger = logging.getLogger("eagle.knowledge_tools")

# Configuration (separate from main EAGLE table)
METADATA_TABLE = os.environ.get("METADATA_TABLE", "eagle-document-metadata-dev")
DOCUMENT_BUCKET = os.environ.get("DOCUMENT_BUCKET", "eagle-documents-695681773636-dev")

# ══════════════════════════════════════════════════════════════════════════════
# Built-in KB entries for templates and checklists
# These are injected into search results so knowledge_search can discover them
# even when they're not registered in the DynamoDB metadata table.
# ══════════════════════════════════════════════════════════════════════════════

_TEMPLATE_PREFIX = "eagle-knowledge-base/approved/supervisor-core/essential-templates"

BUILTIN_KB_ENTRIES: list[dict[str, Any]] = [
    {
        "document_id": "tmpl-sow",
        "title": "Statement of Work (SOW) Template",
        "summary": "Official NCI/HHS SOW template with sections for background, scope, period of performance, place of performance, and applicable documents. Use for competitive acquisitions above micro-purchase threshold.",
        "document_type": "template",
        "primary_topic": "acquisition_packages",
        "primary_agent": "supervisor-core",
        "authority_level": "guidance",
        "keywords": ["SOW", "statement of work", "template", "requirements", "deliverables", "tasks", "performance"],
        "s3_key": f"{_TEMPLATE_PREFIX}/statement-of-work-template-eagle-v2.docx",
        "confidence_score": 0.95,
    },
    {
        "document_id": "tmpl-igce",
        "title": "Independent Government Cost Estimate (IGCE) Template",
        "summary": "Excel spreadsheet template for IGCE with line items, labor categories, rates, and total estimates. Variants available for commercial, educational, and nonprofit organizations.",
        "document_type": "template",
        "primary_topic": "funding",
        "primary_agent": "supervisor-core",
        "authority_level": "guidance",
        "keywords": ["IGCE", "IGE", "cost estimate", "template", "pricing", "labor rates", "budget", "spreadsheet"],
        "s3_key": f"{_TEMPLATE_PREFIX}/01.D_IGCE_for_Commercial_Organizations.xlsx",
        "confidence_score": 0.95,
    },
    {
        "document_id": "tmpl-market-research",
        "title": "HHS Streamlined Market Research Report Template",
        "summary": "Official HHS FY26 streamlined market research report template. Sections for market conditions, vendors identified, pricing analysis, small business sources, set-aside recommendation, and conclusion.",
        "document_type": "template",
        "primary_topic": "market_research",
        "primary_agent": "supervisor-core",
        "authority_level": "guidance",
        "keywords": ["market research", "MRR", "template", "vendors", "pricing", "small business", "set-aside", "competition"],
        "s3_key": f"{_TEMPLATE_PREFIX}/HHS_Streamlined_Market_Research_Template_FY26.docx",
        "confidence_score": 0.95,
    },
    {
        "document_id": "tmpl-justification",
        "title": "Justification & Approval (J&A) Template — Over $350K",
        "summary": "Template for sole source justification and approval for acquisitions over SAT ($350K). Includes FAR 6.302 authority citation, contractor rationale, efforts to compete, and market research summary.",
        "document_type": "template",
        "primary_topic": "compliance",
        "primary_agent": "supervisor-core",
        "authority_level": "guidance",
        "keywords": ["J&A", "justification", "approval", "sole source", "template", "FAR 6.302", "competition", "JOFOC"],
        "s3_key": f"{_TEMPLATE_PREFIX}/Justification_and_Approval_Over_350K_Template.docx",
        "confidence_score": 0.95,
    },
    {
        "document_id": "tmpl-acquisition-plan",
        "title": "HHS Streamlined Acquisition Plan Template",
        "summary": "Official HHS streamlined acquisition plan template per FAR 7.105. Covers requirement description, estimated value, contract type, competition strategy, period of performance, set-aside, and funding.",
        "document_type": "template",
        "primary_topic": "acquisition_packages",
        "primary_agent": "supervisor-core",
        "authority_level": "guidance",
        "keywords": ["acquisition plan", "AP", "template", "FAR 7.105", "strategy", "contract type", "competition", "planning"],
        "s3_key": f"{_TEMPLATE_PREFIX}/HHS Streamlined Acquisition Plan Template.docx",
        "confidence_score": 0.95,
    },
    {
        "document_id": "tmpl-cor-certification",
        "title": "COR Appointment Memorandum Template",
        "summary": "NIH COR appointment/certification memorandum template. Fields for nominee details, FAC-COR level, contract number, and appointment authority.",
        "document_type": "template",
        "primary_topic": "compliance",
        "primary_agent": "supervisor-core",
        "authority_level": "guidance",
        "keywords": ["COR", "appointment", "certification", "memorandum", "template", "contracting officer representative"],
        "s3_key": f"{_TEMPLATE_PREFIX}/NIH COR Appointment Memorandum.docx",
        "confidence_score": 0.90,
    },
    {
        "document_id": "tmpl-son-products",
        "title": "Statement of Need — Products (Equipment and Supplies)",
        "summary": "Template for Statement of Need for products including equipment and supplies. Used during intake phase for competitive acquisitions.",
        "document_type": "template",
        "primary_topic": "acquisition_packages",
        "primary_agent": "supervisor-core",
        "authority_level": "guidance",
        "keywords": ["SON", "statement of need", "products", "equipment", "supplies", "template", "intake", "requirements"],
        "s3_key": f"{_TEMPLATE_PREFIX}/3.a. SON - Products (including Equipment and Supplies).docx",
        "confidence_score": 0.90,
    },
    {
        "document_id": "tmpl-son-services",
        "title": "Statement of Need — Services (Catalog Pricing)",
        "summary": "Template for Statement of Need for services based on catalog pricing. Used during intake phase for competitive acquisitions.",
        "document_type": "template",
        "primary_topic": "acquisition_packages",
        "primary_agent": "supervisor-core",
        "authority_level": "guidance",
        "keywords": ["SON", "statement of need", "services", "catalog", "pricing", "template", "intake"],
        "s3_key": f"{_TEMPLATE_PREFIX}/3.b. SON - Services based on Catalog Pricing.docx",
        "confidence_score": 0.90,
    },
    {
        "document_id": "tmpl-buy-american",
        "title": "Buy American Act Determination Form",
        "summary": "Determination form for Buy American Act non-availability exception. Required when acquiring foreign products that may fall under BAA requirements.",
        "document_type": "template",
        "primary_topic": "compliance",
        "primary_agent": "supervisor-core",
        "authority_level": "guidance",
        "keywords": ["Buy American", "BAA", "determination", "template", "non-availability", "foreign", "compliance"],
        "s3_key": f"{_TEMPLATE_PREFIX}/DF_Buy_American_Non_Availability_Template.docx",
        "confidence_score": 0.85,
    },
    {
        "document_id": "tmpl-subk-plan",
        "title": "HHS Subcontracting Plan Template",
        "summary": "Template for subcontracting plans required for contracts over $900K (FAR 19.702). Includes small business subcontracting goals, reporting requirements, and good faith effort documentation.",
        "document_type": "template",
        "primary_topic": "socioeconomic",
        "primary_agent": "supervisor-core",
        "authority_level": "guidance",
        "keywords": ["subcontracting", "subK", "plan", "template", "small business", "goals", "FAR 19.702"],
        "s3_key": f"{_TEMPLATE_PREFIX}/HHS SubK Plan Template - updated March 2022.doc",
        "confidence_score": 0.85,
    },
    {
        "document_id": "tmpl-j-and-a-under-sat",
        "title": "Justification & Approval (J&A) Template — Under $350K",
        "summary": "Streamlined J&A template for sole source acquisitions under the simplified acquisition threshold ($350K). Less documentation required than full J&A.",
        "document_type": "template",
        "primary_topic": "compliance",
        "primary_agent": "supervisor-core",
        "authority_level": "guidance",
        "keywords": ["J&A", "justification", "sole source", "template", "simplified", "under SAT", "under $350K"],
        "s3_key": f"{_TEMPLATE_PREFIX}/Justification_and_Approval_Under_350K_Template.docx",
        "confidence_score": 0.90,
    },
    {
        "document_id": "checklist-acquisition-package",
        "title": "Acquisition Package Checklist",
        "summary": "Checklist of required documents for a complete acquisition package. Varies by dollar threshold and acquisition method. Includes SOW, IGCE, AP, market research, J&A, evaluation criteria, and compliance documents.",
        "document_type": "checklist",
        "primary_topic": "acquisition_packages",
        "primary_agent": "supervisor-core",
        "authority_level": "guidance",
        "keywords": ["checklist", "acquisition package", "required documents", "completeness", "review", "compliance"],
        "s3_key": "",
        "confidence_score": 0.80,
    },
]

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

    except (ClientError, BotoCoreError, json.JSONDecodeError, KeyError, IndexError, Exception) as e:
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

        # Inject built-in template/checklist entries so they participate in search.
        # Filter them the same way DynamoDB results are filtered.
        for entry in BUILTIN_KB_ENTRIES:
            if topic and entry.get("primary_topic") != topic:
                continue
            if document_type and entry.get("document_type") != document_type:
                continue
            if agent and entry.get("primary_agent") != agent:
                continue
            if authority_level and entry.get("authority_level") != authority_level:
                continue
            # Avoid duplicates if a DynamoDB entry already has the same document_id
            if not any(it.get("document_id") == entry["document_id"] for it in items):
                items.append(entry)

        db_count = len(items) - sum(
            1 for e in BUILTIN_KB_ENTRIES
            if any(it.get("document_id") == e["document_id"] for it in items)
        )
        logger.info("knowledge_search: %d total items (%d DB + %d built-in templates)",
                     len(items), db_count, len(items) - db_count)
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
