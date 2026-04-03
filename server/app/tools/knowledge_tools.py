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
from decimal import Decimal
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError
import threading

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
        "keywords": [
            "SOW",
            "statement of work",
            "template",
            "requirements",
            "deliverables",
            "tasks",
            "performance",
        ],
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
        "keywords": [
            "IGCE",
            "IGE",
            "cost estimate",
            "template",
            "pricing",
            "labor rates",
            "budget",
            "spreadsheet",
        ],
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
        "keywords": [
            "market research",
            "MRR",
            "template",
            "vendors",
            "pricing",
            "small business",
            "set-aside",
            "competition",
        ],
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
        "keywords": [
            "J&A",
            "justification",
            "approval",
            "sole source",
            "template",
            "FAR 6.302",
            "competition",
            "JOFOC",
        ],
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
        "keywords": [
            "acquisition plan",
            "AP",
            "template",
            "FAR 7.105",
            "strategy",
            "contract type",
            "competition",
            "planning",
        ],
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
        "keywords": [
            "COR",
            "appointment",
            "certification",
            "memorandum",
            "template",
            "contracting officer representative",
        ],
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
        "keywords": [
            "SON",
            "statement of need",
            "products",
            "equipment",
            "supplies",
            "template",
            "intake",
            "requirements",
        ],
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
        "keywords": [
            "SON",
            "statement of need",
            "services",
            "catalog",
            "pricing",
            "template",
            "intake",
        ],
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
        "keywords": [
            "Buy American",
            "BAA",
            "determination",
            "template",
            "non-availability",
            "foreign",
            "compliance",
        ],
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
        "keywords": [
            "subcontracting",
            "subK",
            "plan",
            "template",
            "small business",
            "goals",
            "FAR 19.702",
        ],
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
        "keywords": [
            "J&A",
            "justification",
            "sole source",
            "template",
            "simplified",
            "under SAT",
            "under $350K",
        ],
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
        "keywords": [
            "checklist",
            "acquisition package",
            "required documents",
            "completeness",
            "review",
            "compliance",
        ],
        "s3_key": "eagle-knowledge-base/approved/supervisor-core/checklists/HHS_PMR_Common_Requirements.txt",
        "confidence_score": 0.90,
    },
    # --- PMR & FRC Checklists (method-specific) ---
    {
        "document_id": "checklist-frc",
        "title": "NIH File Reviewer's Checklist (FRC)",
        "summary": "OALM Acquisition Compliance Review checklist covering general requirements, acquisition planning, solicitation, evaluation, award, modifications, receiving, and closeout phases. Color-coded rating system (Green/Yellow/Red/NA). Use to verify file completeness.",
        "document_type": "checklist",
        "primary_topic": "compliance",
        "primary_agent": "supervisor-core",
        "authority_level": "policy",
        "keywords": [
            "FRC",
            "file reviewer",
            "OALM",
            "compliance review",
            "acquisition file",
            "checklist",
            "required documents",
        ],
        "s3_key": "eagle-knowledge-base/approved/supervisor-core/checklists/File_Reviewers_Checklist_FRC.txt",
        "confidence_score": 0.95,
    },
    {
        "document_id": "checklist-nih-acq-files",
        "title": "NIH Acquisition File Checklists (OAG-FY25-01)",
        "summary": "Sample acquisition file checklists for negotiated contracts, GSA FSS orders, task/delivery orders, and modifications. Covers presolicitation-to-award, administration/closeout, and unsuccessful proposals.",
        "document_type": "checklist",
        "primary_topic": "acquisition_packages",
        "primary_agent": "supervisor-core",
        "authority_level": "guidance",
        "keywords": [
            "acquisition file",
            "negotiated",
            "FSS",
            "task order",
            "modification",
            "closeout",
            "checklist",
            "OAG",
        ],
        "s3_key": "eagle-knowledge-base/approved/supervisor-core/checklists/OAG_FY25_01_NIH_Acquisition_File_Checklists_MERGED_CORRECTED.txt",
        "confidence_score": 0.95,
    },
    {
        "document_id": "checklist-pmr-common",
        "title": "HHS PMR Common Requirements Checklist",
        "summary": "Universal pre-award, solicitation/award, and administration/closeout requirements applicable to all HHS contract types. Covers funding, market research, small business review, Buy American, IT security, cost/price analysis, responsibility determinations, and closeout.",
        "document_type": "checklist",
        "primary_topic": "compliance",
        "primary_agent": "supervisor-core",
        "authority_level": "policy",
        "keywords": [
            "PMR",
            "common requirements",
            "pre-award",
            "compliance",
            "HHS",
            "closeout",
            "checklist",
        ],
        "s3_key": "eagle-knowledge-base/approved/supervisor-core/checklists/HHS_PMR_Common_Requirements.txt",
        "confidence_score": 0.95,
    },
    {
        "document_id": "checklist-pmr-sap",
        "title": "HHS PMR Simplified Acquisition Procedures (SAP) Checklist",
        "summary": "62-item checklist for simplified acquisitions up to $350K SAT. Covers market research, competition, socioeconomic considerations, compliance certifications, and closeout.",
        "document_type": "checklist",
        "primary_topic": "acquisition_packages",
        "primary_agent": "supervisor-core",
        "authority_level": "policy",
        "keywords": [
            "PMR",
            "SAP",
            "simplified",
            "checklist",
            "pre-award",
            "$350K",
            "HHS",
        ],
        "s3_key": "eagle-knowledge-base/approved/compliance-strategist/PMR-checklists/HHS_PMR_SAP_Checklist.txt",
        "confidence_score": 0.95,
    },
    {
        "document_id": "checklist-pmr-fss",
        "title": "HHS PMR Federal Supply Schedule (FSS) Order Checklist",
        "summary": "Checklist for direct FSS orders without BPAs. Covers competition thresholds, price reduction mandates, SOW documentation, and open market compliance.",
        "document_type": "checklist",
        "primary_topic": "contract_types",
        "primary_agent": "supervisor-core",
        "authority_level": "policy",
        "keywords": [
            "PMR",
            "FSS",
            "schedule",
            "checklist",
            "GSA",
            "order",
            "HHS",
        ],
        "s3_key": "eagle-knowledge-base/approved/compliance-strategist/PMR-checklists/HHS_PMR_FSS_Checklist.txt",
        "confidence_score": 0.95,
    },
    {
        "document_id": "checklist-pmr-bpa",
        "title": "HHS PMR BPA and Call Checklist",
        "summary": "Checklist for GSA Schedule BPA establishment and call orders. Covers approval thresholds, posting requirements, fair opportunity procedures, and option exercise determinations.",
        "document_type": "checklist",
        "primary_topic": "acquisition_packages",
        "primary_agent": "supervisor-core",
        "authority_level": "policy",
        "keywords": [
            "PMR",
            "BPA",
            "blanket purchase",
            "call order",
            "checklist",
            "HHS",
        ],
        "s3_key": "eagle-knowledge-base/approved/compliance-strategist/PMR-checklists/HHS_PMR_BPA_Checklist.txt",
        "confidence_score": 0.95,
    },
    {
        "document_id": "checklist-pmr-idiq",
        "title": "HHS PMR IDIQ Contract and Order Checklist",
        "summary": "Checklist for IDIQ parent contracts and task/delivery orders. Covers single vs. multiple award decisions, source selection, fair opportunity procedures, and closeout.",
        "document_type": "checklist",
        "primary_topic": "acquisition_packages",
        "primary_agent": "supervisor-core",
        "authority_level": "policy",
        "keywords": [
            "PMR",
            "IDIQ",
            "task order",
            "delivery order",
            "checklist",
            "HHS",
        ],
        "s3_key": "eagle-knowledge-base/approved/compliance-strategist/PMR-checklists/HHS_PMR_IDIQ_Checklist.txt",
        "confidence_score": 0.95,
    },
    {
        "document_id": "checklist-pmr-thresholds",
        "title": "HHS PMR Threshold-Based Requirements Matrix",
        "summary": "Matrix of federal acquisition thresholds and triggered requirements effective Oct 2025. Covers $15K to $100M thresholds for IDIQ, BPA, and FSS orders.",
        "document_type": "checklist",
        "primary_topic": "acquisition_packages",
        "primary_agent": "supervisor-core",
        "authority_level": "policy",
        "keywords": [
            "PMR",
            "threshold",
            "matrix",
            "requirements",
            "dollar value",
            "HHS",
        ],
        "s3_key": "eagle-knowledge-base/approved/compliance-strategist/PMR-checklists/HHS_PMR_Threshold_Matrix.txt",
        "confidence_score": 0.95,
    },
]

SEARCH_MODEL_ID = os.environ.get(
    "KNOWLEDGE_SEARCH_MODEL", "us.anthropic.claude-haiku-4-5-20251001-v1:0"
)


_bedrock_local = threading.local()


def _get_bedrock_runtime():
    """Get Bedrock runtime client for knowledge search (thread-local).

    Uses threading.local() instead of @lru_cache to avoid sharing a boto3
    client with internal _thread.lock objects across threads.  When Strands
    SDK runs @tool functions via asyncio.to_thread() and OTEL threading
    instrumentation propagates context, copy.deepcopy on shared locks causes
    TypeError/RecursionError.
    """
    if not hasattr(_bedrock_local, "client"):
        _bedrock_local.client = boto3.client("bedrock-runtime", region_name=AWS_REGION)
    return _bedrock_local.client


def _sanitize_item(item: dict[str, Any]) -> dict[str, Any]:
    """Convert a DynamoDB item to a plain Python dict.

    Creates fresh dict/list containers and converts Decimal to int/float.
    Breaks OTEL wrapper reference chains that cause RecursionError in json.dumps
    when strands-agents[otel] threading instrumentation wraps boto3 responses.
    """

    def _convert(obj: Any, depth: int = 0) -> Any:
        if depth > 20:
            return str(obj)
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        if isinstance(obj, dict):
            return {str(k): _convert(v, depth + 1) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [_convert(v, depth + 1) for v in obj]
        if isinstance(obj, (str, int, float, bool, type(None))):
            return obj
        return str(obj)

    return _convert(item)


# ══════════════════════════════════════════════════════════════════════════════
# Tool Definitions (Anthropic tool_use format)
# ══════════════════════════════════════════════════════════════════════════════

KNOWLEDGE_SEARCH_TOOL = {
    "name": "knowledge_search",
    "description": (
        "Search the acquisition knowledge base for relevant documents, templates, and guidance. "
        "Returns summaries and metadata to help decide which documents to retrieve in full. "
        "Uses AI-powered semantic matching — describe what you need in natural language via 'query'. "
        "Use topic/document_type/specialist filters to narrow the search scope."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "enum": [
                    "funding",
                    "acquisition_packages",
                    "contract_types",
                    "compliance",
                    "legal",
                    "market_research",
                    "socioeconomic",
                    "labor",
                    "intellectual_property",
                    "termination",
                    "modifications",
                    "closeout",
                    "performance",
                    "subcontracting",
                    "general",
                ],
                "description": "Primary topic to filter by",
            },
            "document_type": {
                "type": "string",
                "enum": [
                    "regulation",
                    "guidance",
                    "policy",
                    "template",
                    "memo",
                    "checklist",
                    "reference",
                ],
                "description": "Type of document to search for",
            },
            "specialist": {
                "type": "string",
                "enum": [
                    "supervisor-core",
                    "financial-advisor",
                    "legal-counselor",
                    "compliance-strategist",
                    "market-intelligence",
                    "technical-translator",
                    "public-interest-guardian",
                ],
                "description": "Filter by primary agent/specialist",
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


_AI_RANK_MAX_CANDIDATES = 200  # max items to send to LLM for ranking


def _ai_rank_documents(
    query: str,
    keywords: list[str],
    items: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    """Use Bedrock Haiku to semantically rank documents against a query.

    When the catalog exceeds _AI_RANK_MAX_CANDIDATES items, pre-filters
    using deterministic keyword matching to stay within Haiku's 200K
    context window.

    Returns:
        Ordered list of items ranked by relevance, or empty list on failure.
    """
    if not items:
        return []

    # Pre-filter large catalogs to avoid context overflow (208K+ tokens).
    # Deterministic match narrows to the top candidates by keyword relevance,
    # then AI ranking re-orders those for semantic precision.
    if len(items) > _AI_RANK_MAX_CANDIDATES:
        original_count = len(items)
        pre_filtered = _deterministic_match(query, keywords, items)
        if pre_filtered:
            items = pre_filtered[:_AI_RANK_MAX_CANDIDATES]
            logger.info(
                "knowledge_search AI: pre-filtered %d -> %d candidates",
                original_count,
                len(items),
            )

    # Build compact catalog: index | doc_id | title | keywords | related | summary
    catalog_lines = []
    for i, item in enumerate(items):
        doc_id = item.get("document_id", "")
        title = item.get("title", "")
        kws = ", ".join(item.get("keywords", []))
        related = ", ".join(item.get("related_topics", []))
        summary = (item.get("summary", "") or "")[:200]
        line = f"{i}|{doc_id}|{title}|{kws}|{summary}"
        if related:
            line += f"|RELATED:{related}"
        catalog_lines.append(line)

    catalog = "\n".join(catalog_lines)

    keywords_ctx = f"\nAdditional keywords: {', '.join(keywords)}" if keywords else ""

    # Boost checklists when query involves document generation or compliance
    _doc_gen_signals = {
        "acquisition plan",
        "igce",
        "sow",
        "market research",
        "generate",
        "create document",
        "compliance",
        "checklist",
        "pre-award",
        "package",
    }
    _query_lower = query.lower()
    checklist_boost = ""
    if any(sig in _query_lower for sig in _doc_gen_signals):
        checklist_boost = (
            "\nIMPORTANT: When the query involves document generation, compliance, "
            "or acquisition packages, always include relevant checklists (document_type "
            "= 'checklist') in the top results. Checklists ensure completeness and "
            "regulatory compliance."
        )

    prompt = (
        "You are a document relevance matcher for a federal acquisition knowledge base.\n"
        "Given the search query and document catalog, return the indices of the most "
        f"relevant documents, ranked by relevance. Return up to {limit} results.\n\n"
        "MATCHING RULES:\n"
        "1. CONCEPT ASSOCIATIONS — related concepts must match each other:\n"
        "   - 'fiscal year' + 'appropriation' <-> 'bona fide needs'\n"
        "   - 'severable' / 'non-severable' <-> 'bona fide needs' + 'fiscal year'\n"
        "   - 'IDIQ' + 'minimum' <-> 'funding' + 'obligation'\n"
        "   - 'protest' + 'debriefing' <-> 'stay' + 'timeliness'\n"
        "   - 'fair opportunity' <-> 'exceptions' + 'IDIQ' + '16.505'\n"
        "2. CASE NUMBERS — if the query contains a case number (e.g., B-302358, B-421835),\n"
        "   prioritize documents whose document_id, title, or keywords contain that number.\n"
        "3. SYNONYMS — treat these as equivalent:\n"
        "   - 'requirement' = 'obligation' = 'mandate'\n"
        "   - 'funding' = 'appropriation' = 'money'\n"
        "   - 'IDIQ' = 'indefinite-delivery indefinite-quantity'\n"
        "4. RELATED TOPICS — if a document's RELATED field contains a query concept,\n"
        "   boost its relevance score.\n"
        "5. PREFER knowledge-base documents (s3_key contains 'eagle-knowledge-base/approved')\n"
        "   over user-generated package documents for regulatory/policy queries.\n\n"
        f"Search query: {query}{keywords_ctx}{checklist_boost}\n\n"
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
            logger.warning(
                "knowledge_search AI: unexpected response type: %s", type(indices)
            )
            return []

        ranked = [
            items[i] for i in indices if isinstance(i, int) and 0 <= i < len(items)
        ]
        logger.info(
            "knowledge_search AI: query='%s' matched %d/%d docs",
            query,
            len(ranked),
            len(items),
        )
        return ranked

    except (
        ClientError,
        BotoCoreError,
        json.JSONDecodeError,
        KeyError,
        IndexError,
        Exception,
    ) as e:
        logger.warning("knowledge_search AI ranking failed, falling back: %s", e)
        return []


def _deterministic_match(
    query: str,
    keywords: list[str],
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Fallback deterministic matching when AI ranking is unavailable.

    Uses term-frequency scoring so partial matches still surface results.
    Each query term that appears in a document's searchable text adds 1 point;
    keyword matches add 2 points (higher signal). Documents are ranked by score
    and only those matching at least 30% of query terms are returned.
    """
    if not items:
        return []

    query_lower = (query or "").lower()
    query_terms = query_lower.split() if query_lower else []
    keywords_lower = [k.lower() for k in (keywords or [])]

    scored: list[tuple[float, dict[str, Any]]] = []
    min_term_ratio = 0.3  # require at least 30% of terms to match

    for item in items:
        doc_id = item.get("document_id", "").lower()
        title = item.get("title", "").lower()
        summary = item.get("summary", "").lower()
        filename = item.get("filename", "").lower()
        item_keywords = [k.lower() for k in item.get("keywords", [])]
        keywords_text = " ".join(item_keywords)
        searchable = f"{doc_id} {filename} {title} {summary} {keywords_text}"

        score = 0.0

        # Score query term matches (1 point each, bonus for title match)
        if query_terms:
            for term in query_terms:
                if term in title:
                    score += 2.0  # title match worth more
                elif term in searchable:
                    score += 1.0

        # Score keyword matches (2 points each)
        for kw in keywords_lower:
            if kw in item_keywords or any(kw in ik for ik in item_keywords):
                score += 2.0

        # Exact substring match bonus
        if query_lower and query_lower in searchable:
            score += 5.0

        # Only include if enough terms matched
        term_count = len(query_terms) + len(keywords_lower)
        if term_count > 0 and score / term_count >= min_term_ratio:
            scored.append((score, item))
        elif term_count == 0:
            scored.append((0.0, item))

    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored]


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
        tenant_id,
        query,
        topic,
        document_type,
        agent,
        limit,
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
        items.extend(_sanitize_item(it) for it in response.get("Items", []))
        while "LastEvaluatedKey" in response:
            scan_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
            response = table.scan(**scan_kwargs)
            items.extend(_sanitize_item(it) for it in response.get("Items", []))

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
            1
            for e in BUILTIN_KB_ENTRIES
            if any(it.get("document_id") == e["document_id"] for it in items)
        )
        logger.info(
            "knowledge_search: %d total items (%d DB + %d built-in templates)",
            len(items),
            db_count,
            len(items) - db_count,
        )
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

    # Ensure checklists are included in results for acquisition queries.
    # The agent sometimes calls knowledge_search directly instead of
    # the composite research tool, so we guarantee checklist visibility here.
    top_items = items[:limit]
    top_ids = {it.get("document_id") for it in top_items}
    checklist_extras = [
        it for it in items[limit:]
        if it.get("document_type") == "checklist" and it.get("document_id") not in top_ids
    ]
    if checklist_extras:
        top_items.extend(checklist_extras)
        logger.info(
            "knowledge_search: injected %d checklists beyond limit", len(checklist_extras)
        )

    # Format results
    results = []
    for item in top_items:
        results.append(
            {
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
            }
        )

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
                {"query": query, "limit": 1},
                tenant_id,
                session_id,
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
