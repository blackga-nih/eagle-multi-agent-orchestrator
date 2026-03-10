"""
EAGLE – NCI Acquisition Assistant
Agentic Service using the Anthropic Python SDK directly.
Real AWS tools (S3, DynamoDB, CloudWatch) scoped per-tenant.
"""
import os
import json
import time
import logging
import re
import uuid
from datetime import datetime
from typing import Any, List

import boto3
from botocore.exceptions import ClientError, BotoCoreError

from app.tools.knowledge_tools import (
    KNOWLEDGE_SEARCH_TOOL,
    KNOWLEDGE_FETCH_TOOL,
    exec_knowledge_search,
    exec_knowledge_fetch,
)

logger = logging.getLogger("eagle.agent")

# ── Configuration ────────────────────────────────────────────────────
_USE_BEDROCK = os.getenv("USE_BEDROCK", "false").lower() == "true"
_BEDROCK_REGION = os.getenv("AWS_REGION", "us-east-1")
MODEL = os.getenv("ANTHROPIC_MODEL", "us.anthropic.claude-haiku-4-5-20251001-v1:0" if _USE_BEDROCK else "claude-haiku-4-5-20251001")

SYSTEM_PROMPT = (
    # ── 1. Identity & Mission ──────────────────────────────────────────
    "You are EAGLE, the NCI Office of Acquisitions intelligent intake assistant. "
    "You guide Contracting Officer Representatives (CORs), program staff, and "
    "contracting officers through the federal acquisition lifecycle — from initial "
    "need identification through document generation and package submission. "
    "You are knowledgeable about FAR, DFARS, HHSAR, and NCI-specific acquisition "
    "policies. Be professional, precise, and proactively helpful.\n\n"

    # ── 2. Intake Philosophy ───────────────────────────────────────────
    "INTAKE PHILOSOPHY: Act like 'Trish' — a senior contracting expert who "
    "intuitively knows what to do with any package. Don't require users to "
    "understand all the branching logic upfront. Instead: (1) Start minimal — "
    "collect just enough to begin (what, estimated cost, timeline). (2) Ask "
    "smart follow-ups — 2-3 questions at a time based on their answers. "
    "(3) Determine the pathway — acquisition type, contract type, competition "
    "strategy, and required documents. (4) Guide to completion — help generate "
    "every required document in the package.\n\n"

    # ── 3. Five-Phase Intake Workflow ──────────────────────────────────
    "FIVE-PHASE INTAKE WORKFLOW:\n"
    "  Phase 1 — Minimal Intake: Collect requirement description, estimated cost "
    "range, and timeline.\n"
    "  Phase 2 — Clarifying Questions: Product vs. service, vendor knowledge, "
    "funding status, existing vehicles, urgency drivers.\n"
    "  Phase 3 — Pathway Determination: Micro-purchase (<$15K), Simplified "
    "($15K-$250K, FAR Part 13), or Negotiated (>$250K, FAR Part 15); contract "
    "type (fixed-price, T&M, cost-reimbursement); set-aside evaluation.\n"
    "  Phase 4 — Document Requirements: Identify required documents by "
    "acquisition type and generate them.\n"
    "  Phase 5 — Summary & Handoff: Produce acquisition summary with "
    "determination table, document checklist, and next steps.\n\n"

    # ── 4. Key Thresholds ─────────────────────────────────────────────
    "KEY THRESHOLDS:\n"
    "  Micro-Purchase Threshold (MPT): $15,000 — minimal documentation\n"
    "  Simplified Acquisition Threshold (SAT): $250,000 — full competition above\n"
    "  Cost/Pricing Data: $750,000 — certified cost data required above\n"
    "  8(a) Sole Source: $4M (services/non-mfg), $7M (manufacturing)\n"
    "  Davis-Bacon: $25,000 — wage requirements apply for services\n\n"

    # ── 5. Specialist Lenses ──────────────────────────────────────────
    "SPECIALIST PERSPECTIVES — Apply these lenses when reviewing acquisitions:\n\n"
    "Legal Counsel Lens: Assess legal risks in acquisition strategies. Consider "
    "GAO protest decisions, FAR compliance, fiscal law constraints, and "
    "appropriations law. Identify protest vulnerabilities, cite specific "
    "authorities (FAR 6.302-x), and flag litigation risks.\n\n"
    "Technical Translator Lens: Bridge technical requirements with contract "
    "language. Translate scientific/technical needs into specific, measurable, "
    "achievable contract requirements. Develop clear evaluation criteria and "
    "performance standards that CORs and contracting officers both understand.\n\n"
    "Market Intelligence Lens: Analyze market conditions, vendor capabilities, "
    "and pricing. Leverage GSA rates, FPDS data, and small business program "
    "knowledge (8(a), HUBZone, WOSB, SDVOSB). Identify set-aside opportunities "
    "and validate cost reasonableness.\n\n"
    "Public Interest Lens: Ensure fair competition, transparency, and public "
    "accountability. Evaluate taxpayer value, assess congressional/media "
    "sensitivity, and protect acquisition integrity. Flag fairness issues and "
    "appearance problems before they become protests.\n\n"

    # ── 6. Document Types ─────────────────────────────────────────────
    "DOCUMENT TYPES AVAILABLE VIA create_document TOOL:\n"
    "  sow — Statement of Work\n"
    "  igce — Independent Government Cost Estimate\n"
    "  market_research — Market Research Report\n"
    "  justification — Justification & Approval (sole source)\n"
    "  acquisition_plan — Acquisition Plan (streamlined 5-section format)\n"
    "  eval_criteria — Evaluation Criteria (technical factors & rating scale)\n"
    "  security_checklist — IT Security Checklist (FISMA, FedRAMP, FAR/HHSAR)\n"
    "  section_508 — Section 508 Compliance Statement (accessibility)\n"
    "  cor_certification — COR Certification (nominee, FAC-COR level, duties)\n"
    "  contract_type_justification — Contract Type Justification (D&F elements)\n\n"

    # ── 7. Tool Usage ─────────────────────────────────────────────────
    "TOOL USAGE GUIDANCE:\n"
    "You have access to real AWS-backed tools for document storage (S3), "
    "intake tracking (DynamoDB), log inspection (CloudWatch), FAR search, "
    "document generation, intake status, and a guided intake workflow.\n\n"
    "WORKFLOW: When a user wants to start a new acquisition intake, use the "
    "intake_workflow tool with action='start'. This creates a guided 4-stage "
    "process:\n"
    "  1. Requirements Gathering — collect what, why, when, how much\n"
    "  2. Compliance Check — search FAR, determine thresholds, competition\n"
    "  3. Document Generation — create all required documents\n"
    "  4. Review & Submit — final review and package submission\n\n"
    "Use intake_workflow action='advance' to move between stages after completing "
    "each step. Show the progress bar and next actions to keep users informed.\n\n"
    "For simple queries (FAR search, single document), respond directly. "
    "For full intake packages, use the workflow to ensure nothing is missed. "
    "Use get_intake_status to show which documents are complete vs. pending."
)

# ── AWS Clients (lazy singletons) ────────────────────────────────────
_s3_client = None
_dynamodb_resource = None
_logs_client = None


def _get_s3():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3", region_name="us-east-1")
    return _s3_client


def _get_dynamodb():
    global _dynamodb_resource
    if _dynamodb_resource is None:
        _dynamodb_resource = boto3.resource("dynamodb", region_name="us-east-1")
    return _dynamodb_resource


def _get_logs():
    global _logs_client
    if _logs_client is None:
        _logs_client = boto3.client("logs", region_name="us-east-1")
    return _logs_client


def _extract_tenant_id(session_id: str | None = None) -> str:
    """Extract tenant_id from session context.

    Composite session format: ``{tenant_id}#{tier}#{user_id}#{session}``
    (set by strands_agentic_service when building service tools).
    Falls back to 'demo-tenant' for legacy/unrecognised formats.
    """
    if not session_id:
        return "demo-tenant"
    if "#" in session_id:
        return session_id.split("#", 3)[0]
    return "demo-tenant"


def _extract_user_id(session_id: str | None = None) -> str:
    """Extract user_id from session context.

    Composite session format: ``{tenant_id}#{tier}#{user_id}#{session}``
    Falls back to 'demo-user' for legacy/unrecognised formats.
    """
    if not session_id:
        return "demo-user"
    if "#" in session_id:
        parts = session_id.split("#", 3)
        if len(parts) >= 3:
            return parts[2]
    if session_id.startswith("ws-"):
        return session_id
    return "demo-user"


def _extract_leaf_session_id(session_id: str | None = None) -> str | None:
    """Extract raw session id from composite format {tenant}#{tier}#{user}#{session}."""
    if not session_id:
        return None
    if "#" in session_id:
        parts = session_id.split("#", 3)
        if len(parts) >= 4 and parts[3]:
            return parts[3]
        return None
    return session_id


def _normalize_context_text(text: str) -> str:
    """Prefer the explicit user request section from wrapped prompts."""
    cleaned = (text or "").strip()
    if not cleaned:
        return ""

    marker = "[USER REQUEST]"
    if marker in cleaned:
        tail = cleaned.split(marker, 1)[1].strip()
        if "Instruction:" in tail:
            tail = tail.split("Instruction:", 1)[0].strip()
        if tail:
            cleaned = tail
    return cleaned


def _load_recent_user_context(session_id: str | None = None) -> list[str]:
    """Load recent user messages for contextualizing document generation."""
    leaf_session_id = _extract_leaf_session_id(session_id)
    if not leaf_session_id:
        return []

    tenant_id = _extract_tenant_id(session_id)
    user_id = _extract_user_id(session_id)

    try:
        from .session_store import get_messages

        messages = get_messages(leaf_session_id, tenant_id, user_id, limit=30)
        user_texts: list[str] = []
        for msg in messages:
            if msg.get("role") != "user":
                continue

            content = msg.get("content", "")
            if isinstance(content, str):
                normalized = _normalize_context_text(content)
                if normalized:
                    user_texts.append(normalized)
                continue

            if isinstance(content, list):
                text_parts: list[str] = []
                for block in content:
                    if isinstance(block, dict):
                        block_text = block.get("text")
                        if isinstance(block_text, str) and block_text.strip():
                            text_parts.append(block_text.strip())
                if text_parts:
                    normalized = _normalize_context_text("\n".join(text_parts))
                    if normalized:
                        user_texts.append(normalized)

        return user_texts[-8:]
    except Exception as exc:
        logger.debug("Could not load session context for create_document: %s", exc)
        return []


def _extract_first_money_value(text: str) -> str | None:
    """Extract a likely budget/estimate token from free text."""
    if not text:
        return None

    m = re.search(r"\$[0-9][0-9,]*(?:\.[0-9]+)?", text)
    if m:
        return m.group(0)

    m = re.search(r"\b[0-9][0-9,]*(?:\.[0-9]+)?\s*(?:million|billion|k|m)\b", text, flags=re.IGNORECASE)
    if m:
        return m.group(0)

    return None


def _extract_period(text: str) -> str | None:
    """Extract a likely period-of-performance phrase from free text."""
    if not text:
        return None

    m = re.search(r"\b\d+\s*(?:month|months|year|years)\b(?:[^.,;\n]{0,40})", text, flags=re.IGNORECASE)
    if m:
        return m.group(0).strip()
    return None


def _extract_section_bullets(text: str) -> dict[str, list[str]]:
    """Extract bullet lists grouped by heading from free-form user prompts."""
    sections: dict[str, list[str]] = {}
    current: str | None = None

    aliases = {
        "project description": "project_description",
        "technical requirements": "technical_requirements",
        "scope of work": "scope_of_work",
        "deliverables": "deliverables",
        "environment tiers": "environment_tiers",
        "security": "security",
    }

    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        heading_key = line.rstrip(":").strip().lower()
        if heading_key in aliases:
            current = aliases[heading_key]
            sections.setdefault(current, [])
            continue

        if line.startswith("- ") or line.startswith("* "):
            item = line[2:].strip().strip('"')
            if not item:
                continue
            bucket = current or "general"
            sections.setdefault(bucket, []).append(item)
            continue

    return sections


def _augment_document_data_from_context(
    doc_type: str,
    title: str,
    data: dict | None,
    session_id: str | None,
) -> dict:
    """Fill missing create_document fields from recent user conversation context."""
    merged = dict(data or {})

    # If caller already passed meaningful inputs, preserve them and only fill gaps.
    context_messages = _load_recent_user_context(session_id)
    if not context_messages:
        return merged

    last_user_text = context_messages[-1]
    context_blob = " ".join(context_messages[-4:])

    # Prefer explicit recent user request; keep bounded.
    requirement = (last_user_text or context_blob).strip()
    if requirement:
        requirement = requirement[:500]

    money = _extract_first_money_value(context_blob)
    period = _extract_period(context_blob)

    # Common keys used across multiple document generators/templates.
    if requirement:
        merged.setdefault("description", requirement)
        merged.setdefault("requirement", requirement)
        merged.setdefault("objective", requirement)
    if money:
        merged.setdefault("estimated_cost", money)
        merged.setdefault("estimated_value", money)
        merged.setdefault("budget", money)
        merged.setdefault("total_estimate", money)
    if period:
        merged.setdefault("period_of_performance", period)
        merged.setdefault("timeline", period)

    parsed_sections = _extract_section_bullets("\n".join(context_messages[-3:]))

    project_description = " ".join(parsed_sections.get("project_description", [])).strip()
    if project_description:
        existing_desc = str(merged.get("description", "")).strip()
        if (
            not existing_desc
            or "project description" in existing_desc.lower()
            or len(existing_desc) > 320
        ):
            merged["description"] = project_description[:500]
        merged.setdefault("requirement", project_description[:500])
        merged.setdefault("objective", project_description[:500])
    if parsed_sections.get("deliverables"):
        merged.setdefault("deliverables", parsed_sections["deliverables"][:15])
    if parsed_sections.get("security"):
        merged.setdefault("security_requirements", "; ".join(parsed_sections["security"])[:600])
    if parsed_sections.get("environment_tiers"):
        merged.setdefault("place_of_performance", "; ".join(parsed_sections["environment_tiers"])[:300])

    # Minimal doc-type hints for better first-pass drafts.
    if doc_type == "igce":
        merged.setdefault("item_name", title or "Primary acquisition item")
    if doc_type == "market_research":
        merged.setdefault("requirement_summary", requirement or title)
    if doc_type == "sow":
        scope_items = parsed_sections.get("scope_of_work", [])
        tech_items = parsed_sections.get("technical_requirements", [])
        combined_tasks = (scope_items + tech_items)[:20]
        if combined_tasks:
            merged.setdefault("tasks", combined_tasks)
        merged.setdefault("scope", requirement or title)

    return merged


def _looks_like_unfilled_template_preview(doc_type: str, preview: str) -> bool:
    """Detect boilerplate template previews that did not absorb user context."""
    if not preview:
        return False

    normalized = " ".join(preview.lower().split())
    if doc_type == "sow":
        markers = [
            "this section should provide brief description of the project",
            "the background information should identify the requirement in very general terms",
            "sample language",
            "table of contents",
        ]
        return all(marker in normalized for marker in markers[:2]) and "table of contents" in normalized

    return False


_SOW_SECTION_HINTS: dict[str, str] = {
    "1": "background and purpose",
    "2": "scope",
    "3": "period of performance",
    "4": "applicable documents and standards",
    "5": "tasks and requirements",
    "6": "deliverables",
    "7": "government-furnished property",
    "8": "quality assurance surveillance plan",
    "9": "place of performance",
    "10": "security requirements",
}


def _extract_sow_clear_targets(edit_request: str) -> list[str]:
    """Return SOW section heading hints that the request asks to clear."""
    req = (edit_request or "").strip().lower()
    if not req:
        return []

    # Guardrail: only auto-clear when user explicitly asks to clear/blank.
    clear_intent = (
        "clear" in req
        or "blank" in req
        or "to be completed" in req
        or "remove" in req
    )
    if not clear_intent:
        return []

    targets: list[str] = []

    for section_num in re.findall(r"\bsection\s*(\d{1,2})\b", req):
        hint = _SOW_SECTION_HINTS.get(section_num)
        if hint and hint not in targets:
            targets.append(hint)

    heading_aliases = (
        "background and purpose",
        "scope",
        "period of performance",
        "applicable documents and standards",
        "tasks and requirements",
        "deliverables",
        "government-furnished property",
        "quality assurance surveillance plan",
        "place of performance",
        "security requirements",
    )
    for alias in heading_aliases:
        if alias in req and alias not in targets:
            targets.append(alias)

    # "leave it blank" after "scope" is common shorthand.
    if "scope" in req and "scope" not in targets:
        targets.append("scope")

    return targets


def _apply_sow_clear_edits(current_content: str, edit_request: str) -> str | None:
    """Apply explicit SOW section clear requests against existing markdown."""
    if not isinstance(current_content, str) or not current_content.strip():
        return None

    targets = _extract_sow_clear_targets(edit_request)
    if not targets:
        return None

    heading_matches = list(re.finditer(r"(?m)^##\s+(.+?)\s*$", current_content))
    if not heading_matches:
        return None

    rebuilt: list[str] = []
    cursor = 0
    changed = False

    for idx, heading_match in enumerate(heading_matches):
        heading_end = heading_match.end()
        next_start = heading_matches[idx + 1].start() if idx + 1 < len(heading_matches) else len(current_content)

        heading_text = heading_match.group(1).strip().lower()
        body_text = current_content[heading_end:next_start]

        rebuilt.append(current_content[cursor:heading_end])

        if any(target in heading_text for target in targets):
            replacement = "\n\n[To be completed]\n\n"
            if body_text.strip() != "[To be completed]":
                changed = True
            rebuilt.append(replacement)
        else:
            rebuilt.append(body_text)

        cursor = next_start

    updated = "".join(rebuilt)
    return updated if changed else None


def _get_user_prefix(session_id: str | None = None) -> str:
    """Get the S3 prefix for the current user: eagle/{tenant}/{user}/"""
    tenant_id = _extract_tenant_id(session_id)
    user_id = _extract_user_id(session_id)
    return f"eagle/{tenant_id}/{user_id}/"


# ── Tool Definitions (Anthropic tool_use format) ─────────────────────
EAGLE_TOOLS = [
    {
        "name": "s3_document_ops",
        "description": (
            "Read, write, or list documents stored in S3. All documents are "
            "scoped per-tenant. Use this to manage acquisition documents, "
            "templates, and generated files."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["list", "read", "write"],
                    "description": "Operation to perform: list files, read a file, or write a file",
                },
                "bucket": {
                    "type": "string",
                    "description": "S3 bucket name (uses S3_BUCKET env var if not specified)",
                },
                "key": {
                    "type": "string",
                    "description": "S3 key/path for read or write operations",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write (for write operation)",
                },
            },
            "required": ["operation"],
        },
    },
    {
        "name": "dynamodb_intake",
        "description": (
            "Create, read, update, list, or query intake records in DynamoDB. "
            "All records are scoped per-tenant using PK/SK patterns. Use this "
            "to track acquisition intake packages."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["create", "read", "update", "list", "query"],
                    "description": "CRUD operation to perform",
                },
                "table": {
                    "type": "string",
                    "description": "DynamoDB table name (default: eagle)",
                },
                "item_id": {
                    "type": "string",
                    "description": "Unique item identifier for read/update",
                },
                "data": {
                    "type": "object",
                    "description": "Data fields for create/update operations",
                },
                "filter_expression": {
                    "type": "string",
                    "description": "Optional filter expression for queries",
                },
            },
            "required": ["operation"],
        },
    },
    {
        "name": "cloudwatch_logs",
        "description": (
            "Read CloudWatch logs filtered by user/session. Use this to inspect "
            "application logs, debug issues, or audit user activity."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["search", "recent", "get_stream"],
                    "description": "Log operation: search with filter, get recent events, or get a specific stream",
                },
                "log_group": {
                    "type": "string",
                    "description": "CloudWatch log group name (default: /eagle/app)",
                },
                "filter_pattern": {
                    "type": "string",
                    "description": "CloudWatch filter pattern for searching logs",
                },
                "start_time": {
                    "type": "string",
                    "description": "Start time for log search (ISO format or relative like '-1h')",
                },
                "end_time": {
                    "type": "string",
                    "description": "End time for log search (ISO format)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of log events to return (default: 50)",
                },
            },
            "required": ["operation"],
        },
    },
    {
        "name": "search_far",
        "description": (
            "Search the Federal Acquisition Regulation (FAR) and Defense Federal "
            "Acquisition Regulation Supplement (DFARS) for relevant clauses, "
            "requirements, and guidance. Returns part numbers, sections, titles, "
            "full text summaries, and applicability notes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query — topic, clause number, or keyword",
                },
                "parts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific FAR part numbers to search (e.g. ['13', '15'])",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "create_document",
        "description": (
            "Generate acquisition documents including SOW, IGCE, Market Research, "
            "J&A, Acquisition Plan, Evaluation Criteria, Security Checklist, "
            "Section 508 Statement, COR Certification, and Contract Type "
            "Justification. Documents are saved to S3."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "doc_type": {
                    "type": "string",
                    "enum": [
                        "sow", "igce", "market_research", "justification",
                        "acquisition_plan", "eval_criteria", "security_checklist",
                        "section_508", "cor_certification",
                        "contract_type_justification"
                    ],
                    "description": "Type of acquisition document to generate",
                },
                "title": {
                    "type": "string",
                    "description": "Title of the acquisition/document",
                },
                "data": {
                    "type": "object",
                    "description": "Document-specific fields (description, line_items, vendors, etc.)",
                },
            },
            "required": ["doc_type", "title"],
        },
    },
    {
        "name": "get_intake_status",
        "description": (
            "Get the current intake package status and completeness. Shows which "
            "documents exist, which are missing, and next actions needed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "intake_id": {
                    "type": "string",
                    "description": "Intake package ID (defaults to active intake if not provided)",
                },
            },
        },
    },
    {
        "name": "intake_workflow",
        "description": (
            "Manage the acquisition intake workflow. Use 'start' to begin a new intake, "
            "'advance' to move to the next stage, 'status' to see current stage and progress, "
            "or 'complete' to finish the intake. The workflow guides through: "
            "1) Requirements Gathering, 2) Compliance Check, 3) Document Generation, 4) Review & Submit."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["start", "advance", "status", "complete", "reset"],
                    "description": "Workflow action to perform",
                },
                "intake_id": {
                    "type": "string",
                    "description": "Intake ID (auto-generated on start, required for other actions)",
                },
                "data": {
                    "type": "object",
                    "description": "Stage-specific data to save (requirements, compliance results, etc.)",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "query_compliance_matrix",
        "description": (
            "Query NCI/NIH contract requirements decision tree. "
            "Pass a JSON params string with operation (query/list_methods/list_types/"
            "list_thresholds/search_far/suggest_vehicle) and operation-specific fields."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "params": {
                    "type": "string",
                    "description": (
                        'JSON string. For query: {"operation":"query","contract_value":85000,'
                        '"acquisition_method":"sap","contract_type":"ffp","is_services":true}. '
                        'For search: {"operation":"search_far","keyword":"sole source"}.'
                    ),
                },
            },
            "required": ["params"],
        },
    },
    # Knowledge base tools
    KNOWLEDGE_SEARCH_TOOL,
    KNOWLEDGE_FETCH_TOOL,
]


# ── Tool Execution Handlers ──────────────────────────────────────────

def _exec_s3_document_ops(params: dict, tenant_id: str, session_id: str = None) -> dict:
    """Real S3 operations scoped per-user."""
    operation = params.get("operation", "list")
    bucket = params.get("bucket") or os.getenv("S3_BUCKET", "eagle-documents-695681773636-dev")
    key = params.get("key", "")
    content = params.get("content", "")
    # Per-user prefix: eagle/{tenant}/{user}/
    user_id = _extract_user_id(session_id)
    prefix = f"eagle/{tenant_id}/{user_id}/"

    s3 = _get_s3()

    try:
        if operation == "list":
            resp = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=100)
            objects = resp.get("Contents", [])
            files = []
            for obj in objects:
                files.append({
                    "key": obj["Key"],
                    "size_bytes": obj["Size"],
                    "last_modified": obj["LastModified"].isoformat(),
                })
            return {
                "operation": "list",
                "bucket": bucket,
                "prefix": prefix,
                "file_count": len(files),
                "files": files,
            }

        elif operation == "read":
            if not key:
                return {"error": "Missing 'key' parameter for read operation"}
            # Ensure key is within tenant scope
            if not key.startswith(prefix):
                key = prefix + key
            resp = s3.get_object(Bucket=bucket, Key=key)
            body = resp["Body"].read().decode("utf-8", errors="replace")
            return {
                "operation": "read",
                "key": key,
                "content_type": resp.get("ContentType", "unknown"),
                "size_bytes": resp.get("ContentLength", 0),
                "content": body[:50000],  # Cap at 50K chars
            }

        elif operation == "write":
            if not key:
                return {"error": "Missing 'key' parameter for write operation"}
            if not content:
                return {"error": "Missing 'content' parameter for write operation"}
            # Ensure key is within tenant scope
            if not key.startswith(prefix):
                key = prefix + key
            s3.put_object(Bucket=bucket, Key=key, Body=content.encode("utf-8"))
            return {
                "operation": "write",
                "key": key,
                "bucket": bucket,
                "size_bytes": len(content.encode("utf-8")),
                "status": "success",
                "message": f"Document written to s3://{bucket}/{key}",
            }

        else:
            return {"error": f"Unknown operation: {operation}. Use list, read, or write."}

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        error_msg = e.response["Error"]["Message"]
        if error_code in ("AccessDenied", "AccessDeniedException"):
            return {
                "error": f"AWS permission denied for S3 {operation}",
                "detail": error_msg,
                "suggestion": "The IAM user may not have the required S3 permissions. Contact your administrator.",
            }
        elif error_code == "NoSuchKey":
            return {"error": f"File not found: {key}", "bucket": bucket}
        elif error_code == "NoSuchBucket":
            return {"error": f"Bucket not found: {bucket}"}
        else:
            return {"error": f"S3 error ({error_code}): {error_msg}"}
    except BotoCoreError as e:
        return {"error": f"AWS connection error: {str(e)}"}


def _exec_dynamodb_intake(params: dict, tenant_id: str) -> dict:
    """Real DynamoDB operations scoped per-tenant."""
    operation = params.get("operation", "list")
    table_name = params.get("table", "eagle")
    item_id = params.get("item_id", "")
    data = params.get("data", {})

    try:
        ddb = _get_dynamodb()
        table = ddb.Table(table_name)

        if operation == "create":
            if not item_id:
                item_id = str(uuid.uuid4())[:8]
            item = {
                "PK": f"INTAKE#{tenant_id}",
                "SK": f"INTAKE#{item_id}",
                "item_id": item_id,
                "tenant_id": tenant_id,
                "created_at": datetime.utcnow().isoformat(),
                "status": "draft",
                **{k: v for k, v in data.items() if k not in ("PK", "SK")},
            }
            table.put_item(Item=item)
            return {
                "operation": "create",
                "item_id": item_id,
                "status": "created",
                "item": item,
            }

        elif operation == "read":
            if not item_id:
                return {"error": "Missing 'item_id' for read operation"}
            resp = table.get_item(
                Key={"PK": f"INTAKE#{tenant_id}", "SK": f"INTAKE#{item_id}"}
            )
            item = resp.get("Item")
            if not item:
                return {"error": f"Intake record not found: {item_id}"}
            return {"operation": "read", "item": _serialize_ddb_item(item)}

        elif operation == "update":
            if not item_id:
                return {"error": "Missing 'item_id' for update operation"}
            if not data:
                return {"error": "Missing 'data' for update operation"}
            # Build update expression
            update_parts = []
            expr_names = {}
            expr_values = {}
            for i, (k, v) in enumerate(data.items()):
                if k in ("PK", "SK"):
                    continue
                alias = f"#attr{i}"
                val_alias = f":val{i}"
                update_parts.append(f"{alias} = {val_alias}")
                expr_names[alias] = k
                expr_values[val_alias] = v
            if not update_parts:
                return {"error": "No valid fields to update"}
            update_parts.append("#upd = :updval")
            expr_names["#upd"] = "updated_at"
            expr_values[":updval"] = datetime.utcnow().isoformat()

            table.update_item(
                Key={"PK": f"INTAKE#{tenant_id}", "SK": f"INTAKE#{item_id}"},
                UpdateExpression="SET " + ", ".join(update_parts),
                ExpressionAttributeNames=expr_names,
                ExpressionAttributeValues=expr_values,
            )
            return {"operation": "update", "item_id": item_id, "status": "updated", "fields_updated": list(data.keys())}

        elif operation in ("list", "query"):
            from boto3.dynamodb.conditions import Key as DDBKey
            resp = table.query(
                KeyConditionExpression=DDBKey("PK").eq(f"INTAKE#{tenant_id}")
            )
            items = [_serialize_ddb_item(i) for i in resp.get("Items", [])]
            return {
                "operation": "list",
                "tenant_id": tenant_id,
                "count": len(items),
                "items": items,
            }

        else:
            return {"error": f"Unknown operation: {operation}. Use create, read, update, list, or query."}

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        error_msg = e.response["Error"]["Message"]
        if error_code in ("AccessDenied", "AccessDeniedException"):
            return {
                "error": f"AWS permission denied for DynamoDB {operation}",
                "detail": error_msg,
                "suggestion": "The IAM user may not have the required DynamoDB permissions. Contact your administrator.",
            }
        elif error_code == "ResourceNotFoundException":
            return {"error": f"DynamoDB table '{table_name}' not found. It may need to be created."}
        else:
            return {"error": f"DynamoDB error ({error_code}): {error_msg}"}
    except BotoCoreError as e:
        return {"error": f"AWS connection error: {str(e)}"}


def _serialize_ddb_item(item: dict) -> dict:
    """Convert DynamoDB item to JSON-serializable dict."""
    from decimal import Decimal
    result = {}
    for k, v in item.items():
        if isinstance(v, Decimal):
            result[k] = float(v) if v % 1 else int(v)
        else:
            result[k] = v
    return result


def _exec_cloudwatch_logs(params: dict, tenant_id: str) -> dict:
    """Real CloudWatch Logs operations with optional user_id scoping."""
    operation = params.get("operation", "recent")
    log_group = params.get("log_group", "/eagle/app")
    filter_pattern = params.get("filter_pattern", "")
    limit = params.get("limit", 50)
    start_time_str = params.get("start_time", "")
    end_time_str = params.get("end_time", "")
    user_id = params.get("user_id", "")

    try:
        logs = _get_logs()

        # Parse time ranges
        now = int(time.time() * 1000)
        start_time = now - (3600 * 1000)  # Default: last 1 hour
        end_time = now

        if start_time_str:
            if start_time_str.startswith("-"):
                # Relative time like "-1h", "-30m", "-24h"
                val = start_time_str[1:-1]
                unit = start_time_str[-1]
                multipliers = {"m": 60, "h": 3600, "d": 86400}
                offset_sec = int(val) * multipliers.get(unit, 3600)
                start_time = now - (offset_sec * 1000)
            else:
                try:
                    dt = datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
                    start_time = int(dt.timestamp() * 1000)
                except ValueError:
                    pass

        if end_time_str:
            try:
                dt = datetime.fromisoformat(end_time_str.replace("Z", "+00:00"))
                end_time = int(dt.timestamp() * 1000)
            except ValueError:
                pass

        if operation == "search":
            # Include tenant_id and user_id in filter pattern for scoping
            scoped_pattern = filter_pattern
            if tenant_id and tenant_id not in (filter_pattern or ""):
                scoped_pattern = f'"{tenant_id}" {scoped_pattern}'.strip()
            if user_id and user_id not in (scoped_pattern or ""):
                scoped_pattern = f'"{user_id}" {scoped_pattern}'.strip()

            resp = logs.filter_log_events(
                logGroupName=log_group,
                filterPattern=scoped_pattern,
                startTime=start_time,
                endTime=end_time,
                limit=min(limit, 100),
            )
            events = [
                {"timestamp": e["timestamp"], "message": e["message"][:500], "logStreamName": e.get("logStreamName", "")}
                for e in resp.get("events", [])
            ]
            return {
                "operation": "search",
                "log_group": log_group,
                "filter_pattern": scoped_pattern,
                "event_count": len(events),
                "events": events,
            }

        elif operation == "recent":
            # Build optional filter pattern from user_id for scoped recent queries
            recent_pattern = ""
            if user_id:
                recent_pattern = f'"{user_id}"'

            kwargs = {
                "logGroupName": log_group,
                "startTime": start_time,
                "endTime": end_time,
                "limit": min(limit, 100),
            }
            if recent_pattern:
                kwargs["filterPattern"] = recent_pattern

            resp = logs.filter_log_events(**kwargs)
            events = [
                {"timestamp": e["timestamp"], "message": e["message"][:500], "logStreamName": e.get("logStreamName", "")}
                for e in resp.get("events", [])
            ]
            result = {
                "operation": "recent",
                "log_group": log_group,
                "event_count": len(events),
                "events": events,
            }
            if user_id:
                result["user_id_filter"] = user_id
            return result

        elif operation == "get_stream":
            resp = logs.describe_log_streams(
                logGroupName=log_group,
                orderBy="LastEventTime",
                descending=True,
                limit=5,
            )
            streams = [
                {"logStreamName": s["logStreamName"], "lastEventTimestamp": s.get("lastEventTimestamp", 0)}
                for s in resp.get("logStreams", [])
            ]
            return {
                "operation": "get_stream",
                "log_group": log_group,
                "streams": streams,
            }

        else:
            return {"error": f"Unknown operation: {operation}. Use search, recent, or get_stream."}

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        error_msg = e.response["Error"]["Message"]
        if error_code in ("AccessDenied", "AccessDeniedException"):
            return {
                "error": f"AWS permission denied for CloudWatch Logs {operation}",
                "detail": error_msg,
                "suggestion": "The IAM user may not have the required CloudWatch Logs permissions. Contact your administrator.",
            }
        elif error_code == "ResourceNotFoundException":
            return {"error": f"Log group '{log_group}' not found."}
        else:
            return {"error": f"CloudWatch error ({error_code}): {error_msg}"}
    except BotoCoreError as e:
        return {"error": f"AWS connection error: {str(e)}"}


def _exec_search_far(params: dict, tenant_id: str) -> dict:
    """Search Federal Acquisition Regulation using shared far-database.json."""
    from .compliance_matrix import search_far as _cm_search_far

    query = params.get("query", "")
    parts_filter = params.get("parts", None)

    results = _cm_search_far(query, parts_filter)

    if not results:
        results = [
            {"part": "1", "section": "1.102", "title": "Statement of Guiding Principles",
             "summary": "Deliver best value to the Government, satisfy the customer, minimize administrative costs, conduct business with integrity.",
             "applicability": "All federal acquisitions"},
        ]

    return {
        "query": query,
        "parts_searched": parts_filter or ["all"],
        "results_count": len(results),
        "clauses": results[:15],
        "source": "FAR/DFARS/HHSAR reference database (eagle-plugin/data/far-database.json)",
        "note": "Reference data — always verify against current FAR/DFARS at acquisition.gov",
    }


def _exec_search_far_LEGACY(params: dict, tenant_id: str) -> dict:
    """LEGACY — old inline mock data kept for reference. Not called."""
    query = params.get("query", "").lower()
    parts_filter = params.get("parts", [])

    # Comprehensive FAR database
    far_database = [
        # Part 1 - Federal Acquisition Regulations System
        {"part": "1", "section": "1.102", "title": "Statement of Guiding Principles for the Federal Acquisition System",
         "summary": "The vision for the Federal acquisition system is to deliver on a timely basis the best value product or service to the customer, while maintaining the public's trust and fulfilling public policy objectives.",
         "applicability": "All federal acquisitions",
         "keywords": ["principles", "vision", "best value", "public trust", "policy"]},
        {"part": "1", "section": "1.602-1", "title": "Authority of Contracting Officers",
         "summary": "Contracting officers have authority to enter into, administer, or terminate contracts and make related determinations and findings. They may bind the Government only to the extent of the authority delegated to them.",
         "applicability": "All contracting officers",
         "keywords": ["authority", "contracting officer", "delegation", "binding"]},

        # Part 2 - Definitions of Words and Terms
        {"part": "2", "section": "2.101", "title": "Definitions",
         "summary": "Micro-purchase threshold: $10,000 ($25,000 for DoD contingency operations, $20,000 for acquisitions inside the US, $35,000 for acquisitions outside the US). Simplified Acquisition Threshold (SAT): $250,000. Commercial product/service definitions provided.",
         "applicability": "All acquisitions — defines key thresholds",
         "keywords": ["micro-purchase", "threshold", "simplified", "sat", "definitions", "commercial", "$10,000", "$250,000"]},

        # Part 3 - Improper Business Practices
        {"part": "3", "section": "3.104", "title": "Procurement Integrity",
         "summary": "Prohibits disclosure of contractor bid/proposal information and source selection information. Restricts employment contacts between Government officials and offerors. Violations may result in criminal penalties.",
         "applicability": "All competitive acquisitions",
         "keywords": ["integrity", "disclosure", "bid", "source selection", "ethics"]},

        # Part 4 - Administrative Matters
        {"part": "4", "section": "4.606", "title": "Reporting Data (FPDS)",
         "summary": "Contract actions reported to Federal Procurement Data System (FPDS) within 3 business days of execution. Required for actions over micro-purchase threshold.",
         "applicability": "Actions above micro-purchase threshold",
         "keywords": ["fpds", "reporting", "data", "contract action"]},
        {"part": "4", "section": "4.1102", "title": "System for Award Management (SAM)",
         "summary": "Prospective contractors must be registered in SAM prior to award of any contract. Contracting officers must verify registration before award.",
         "applicability": "All awards",
         "keywords": ["sam", "registration", "award", "verification"]},

        # Part 5 - Publicizing Contract Actions
        {"part": "5", "section": "5.101", "title": "Methods of Disseminating Information",
         "summary": "Synopsis required on SAM.gov (formerly FedBizOpps) for acquisitions exceeding $25,000. 15-day response time for most actions, 30 days for sealed bidding, 45 days for competitive proposals when certified cost or pricing data required.",
         "applicability": "Acquisitions above $25,000",
         "keywords": ["synopsis", "publicize", "sam.gov", "fedbizopps", "notice"]},

        # Part 6 - Competition Requirements
        {"part": "6", "section": "6.101", "title": "Policy — Full and Open Competition",
         "summary": "Contracting officers shall promote and provide for full and open competition. Must solicit from as many sources as practicable to ensure competition.",
         "applicability": "All acquisitions above SAT",
         "keywords": ["competition", "full and open", "sources", "policy"]},
        {"part": "6", "section": "6.302", "title": "Circumstances Permitting Other Than Full and Open Competition",
         "summary": "Seven exceptions: (1) Only one responsible source/unique supply, (2) Unusual and compelling urgency, (3) Industrial mobilization/expert services, (4) International agreement, (5) Authorized/required by statute, (6) National security, (7) Public interest determination by agency head.",
         "applicability": "Sole source or limited competition situations",
         "keywords": ["sole source", "competition", "exception", "j&a", "justification", "urgency", "unique"]},
        {"part": "6", "section": "6.303", "title": "Justifications (J&A)",
         "summary": "Written Justification and Approval (J&A) required for other than full and open competition. Must include: description of supplies, nature of action, authority cited, demonstration that proposed contractor's capabilities are unique, market research, any other facts, listing of sources solicited, actions to remove barriers to competition.",
         "applicability": "All sole source or limited competition actions",
         "keywords": ["justification", "j&a", "sole source", "approval", "written"]},
        {"part": "6", "section": "6.304", "title": "Approval of Justifications",
         "summary": "Approval thresholds: ≤$750K by Contracting Officer, ≤$15M by Competition Advocate, ≤$75M by Head of Procuring Activity, ≤$100M by Senior Procurement Executive, >$100M by agency head (non-delegable).",
         "applicability": "All J&A approvals",
         "keywords": ["approval", "threshold", "j&a", "competition advocate", "authority"]},

        # Part 7 - Acquisition Planning
        {"part": "7", "section": "7.102", "title": "Policy — Acquisition Planning",
         "summary": "Agencies shall perform acquisition planning and conduct market research for all acquisitions to promote and provide for full and open competition, or when full and open competition is not required, to promote competition to the maximum extent practicable.",
         "applicability": "All acquisitions",
         "keywords": ["planning", "market research", "strategy"]},
        {"part": "7", "section": "7.105", "title": "Contents of Written Acquisition Plans",
         "summary": "Written acquisition plan required for acquisitions of supplies/services with estimated value exceeding $7M for new contracts or $50M for task/delivery orders. Plan includes: statement of need, cost, period of performance, trade-offs, risks, acquisition streamlining.",
         "applicability": "Major acquisitions",
         "keywords": ["acquisition plan", "written", "contents", "requirement"]},

        # Part 8 - Required Sources of Supplies and Services
        {"part": "8", "section": "8.405", "title": "Ordering Procedures for Federal Supply Schedules",
         "summary": "GSA Schedule ordering: micro-purchase (one source), $10K-$250K (consider 3+ schedule contractors), >$250K (request quotes from enough sources). Must consider small business. Fair opportunity required for BPAs.",
         "applicability": "GSA Schedule orders",
         "keywords": ["gsa", "schedule", "ordering", "federal supply", "bpa"]},

        # Part 9 - Contractor Qualifications
        {"part": "9", "section": "9.104-1", "title": "General Standards of Responsibility",
         "summary": "Prospective contractor must have: adequate financial resources, ability to comply with delivery schedule, satisfactory performance record, satisfactory record of integrity, necessary organization/experience/accounting/operational controls, necessary equipment/facilities, be otherwise qualified and eligible.",
         "applicability": "All awards",
         "keywords": ["responsibility", "financial", "performance", "integrity", "qualified"]},

        # Part 10 - Market Research
        {"part": "10", "section": "10.001", "title": "Policy — Market Research",
         "summary": "Agencies must conduct market research appropriate to the circumstances before developing new requirements, before soliciting offers, and before awarding task/delivery orders. Used to determine if commercial products/services can meet needs.",
         "applicability": "All acquisitions",
         "keywords": ["market research", "commercial", "requirement", "sources"]},
        {"part": "10", "section": "10.002", "title": "Procedures for Market Research",
         "summary": "Techniques include: contacting knowledgeable individuals, reviewing published market research, publishing RFIs, querying GSA/government databases, participating in industry conferences, reviewing catalogs, and conducting interchange meetings with industry.",
         "applicability": "All acquisitions",
         "keywords": ["market research", "procedure", "rfi", "sources sought", "industry"]},

        # Part 11 - Describing Agency Needs
        {"part": "11", "section": "11.002", "title": "Policy for Describing Agency Needs",
         "summary": "Agencies should define requirements using market research. Use performance specifications rather than design specifications to the maximum extent practicable. State requirements in terms of functions, performance, or essential physical characteristics.",
         "applicability": "All requirements",
         "keywords": ["requirements", "performance", "specifications", "needs", "medical", "equipment"]},

        # Part 12 - Acquisition of Commercial Products/Services
        {"part": "12", "section": "12.000", "title": "Scope of Part — Commercial Acquisition",
         "summary": "Establishes acquisition policies and procedures for commercial products, commercial services, and COTS items. Agencies shall acquire commercial items when available to meet needs.",
         "applicability": "Commercial acquisitions",
         "keywords": ["commercial", "cots", "products", "services", "streamlined"]},
        {"part": "12", "section": "12.207", "title": "Contract Type for Commercial Items",
         "summary": "Firm-Fixed-Price (FFP) contracts or Fixed-Price with Economic Price Adjustment (FP-EPA) are preferred for commercial products and services. T&M/LH contracts may be used only if no other type is suitable and if approved at one level above the CO.",
         "applicability": "Commercial item acquisitions",
         "keywords": ["contract type", "ffp", "fixed price", "commercial", "time and materials"]},
        {"part": "12", "section": "12.602", "title": "Streamlined Evaluation for Commercial Items",
         "summary": "Evaluation of commercial items shall be based on past performance, price, and technical approach. Simplified evaluation procedures are encouraged. Oral presentations may replace written proposals.",
         "applicability": "Commercial acquisitions",
         "keywords": ["evaluation", "commercial", "streamlined", "past performance"]},

        # Part 13 - Simplified Acquisition Procedures
        {"part": "13", "section": "13.000", "title": "Scope of Part — Simplified Acquisition Procedures",
         "summary": "Simplified acquisition procedures (SAP) apply to acquisitions at or below the Simplified Acquisition Threshold ($250,000). Promotes competition, efficiency, and economy while reducing administrative burden. Government-wide purchase card is the preferred method for micro-purchases.",
         "applicability": "Acquisitions ≤ $250,000",
         "keywords": ["simplified", "sap", "threshold", "purchase card", "micro-purchase", "small purchase"]},
        {"part": "13", "section": "13.003", "title": "Policy for Simplified Acquisition",
         "summary": "Agencies shall use simplified acquisition procedures to the maximum extent practicable for acquisitions at or below the SAT. Promotes competition, efficiency, economy. Supports small business participation.",
         "applicability": "Acquisitions ≤ SAT",
         "keywords": ["simplified", "policy", "small business", "efficiency"]},
        {"part": "13", "section": "13.106-1", "title": "Soliciting Competition Under SAP",
         "summary": "For purchases above micro-purchase threshold: promote competition to maximum extent practicable. Consider at least 3 sources. Oral solicitations acceptable. No synopsis required under $25,000. Small business set-aside rules apply.",
         "applicability": "SAP above micro-purchase threshold",
         "keywords": ["competition", "soliciting", "sources", "oral", "simplified"]},
        {"part": "13", "section": "13.500", "title": "Test Program for Certain Commercial Products (Subpart 13.5)",
         "summary": "Allows use of simplified procedures for acquisitions of commercial products and services exceeding the SAT but not exceeding $7.5M ($15M for acquisitions as described in 13.500(c)).",
         "applicability": "Commercial items $250K - $7.5M",
         "keywords": ["test program", "commercial", "simplified", "subpart 13.5"]},

        # Part 14 - Sealed Bidding
        {"part": "14", "section": "14.101", "title": "Elements of Sealed Bidding",
         "summary": "Four elements: (1) Preparation of IFB describing Government requirements, (2) Publicizing the IFB, (3) Public opening of bids at time and place stated, (4) Award to responsible bidder whose bid conforms to IFB and is most advantageous (price and price-related factors).",
         "applicability": "Sealed bid acquisitions",
         "keywords": ["sealed bidding", "ifb", "invitation", "bid", "public opening"]},

        # Part 15 - Contracting by Negotiation
        {"part": "15", "section": "15.101", "title": "Best Value Continuum",
         "summary": "Range from Lowest Price Technically Acceptable (LPTA) to tradeoff. In tradeoff: non-price factors can justify paying a higher price. Use LPTA when best value to the Government results from selection of technically acceptable proposal at lowest price. Source selection authority decides.",
         "applicability": "Negotiated acquisitions",
         "keywords": ["best value", "lpta", "tradeoff", "evaluation", "negotiation", "price"]},
        {"part": "15", "section": "15.304", "title": "Evaluation Factors and Significant Subfactors",
         "summary": "Evaluation factors must: (a) represent key areas of importance/emphasis, (b) support meaningful comparison, (c) include price/cost as a factor. Past performance shall be evaluated unless waived. Small disadvantaged business participation may be evaluated.",
         "applicability": "All competitive negotiated acquisitions",
         "keywords": ["evaluation factors", "criteria", "price", "past performance", "technical"]},
        {"part": "15", "section": "15.404-1", "title": "Proposal Analysis Techniques",
         "summary": "Price analysis (comparing proposed prices to each other, historical, published, or independent estimates). Cost analysis (evaluating separate cost elements and profit). Certified cost or pricing data required when exceeding $2M threshold (Truth in Negotiations Act — TINA).",
         "applicability": "Price/cost proposals",
         "keywords": ["price analysis", "cost analysis", "tina", "certified", "proposal", "cost estimate"]},

        # Part 16 - Types of Contracts
        {"part": "16", "section": "16.102", "title": "Policies for Contract Types",
         "summary": "Selecting contract type requires negotiation and is a matter requiring judgment. Fixed-price types provide maximum incentive for cost control. Cost-reimbursement types place risk of cost overrun on Government. A firm-fixed-price contract is preferred when risk involved is minimal.",
         "applicability": "All contracts",
         "keywords": ["contract type", "fixed price", "cost reimbursement", "risk", "selection"]},
        {"part": "16", "section": "16.601", "title": "Time-and-Materials Contracts",
         "summary": "T&M contracts provide for acquiring supplies/services on the basis of direct labor hours at specified rates and actual cost of materials. Use only when it is not possible to estimate the extent or duration of work or costs with sufficient accuracy. Requires D&F approved one level above CO.",
         "applicability": "When FFP not feasible",
         "keywords": ["time and materials", "t&m", "labor hours", "rates"]},

        # Part 19 - Small Business Programs
        {"part": "19", "section": "19.201", "title": "General Policy for Small Business",
         "summary": "It is the policy of the Government to provide maximum practicable opportunities to small business concerns, veteran-owned, service-disabled veteran-owned, HUBZone, small disadvantaged, and women-owned small business concerns.",
         "applicability": "All acquisitions",
         "keywords": ["small business", "set-aside", "policy", "opportunity"]},
        {"part": "19", "section": "19.502-2", "title": "Total Small Business Set-Asides",
         "summary": "Set aside for small business if: (a) there is a reasonable expectation of receiving offers from two or more responsible small business concerns, and (b) award will be made at fair market prices. Applies to acquisitions between micro-purchase threshold and SAT automatically.",
         "applicability": "Acquisitions above micro-purchase threshold",
         "keywords": ["set-aside", "small business", "total", "automatic", "competition"]},
        {"part": "19", "section": "19.805", "title": "8(a) Competitive Requirements",
         "summary": "Competitive 8(a) acquisitions required above $4.5M (services) or $7M (manufacturing). Below those thresholds, sole source 8(a) awards permitted. Must have an approved offering letter from SBA.",
         "applicability": "8(a) program acquisitions",
         "keywords": ["8a", "competitive", "sba", "sole source", "small disadvantaged"]},
        {"part": "19", "section": "19.1305", "title": "HUBZone Set-Aside Procedures",
         "summary": "Set aside for HUBZone small business if reasonable expectation of two or more responsible HUBZone offers at fair market price. Contracting officer must verify HUBZone status in SAM.",
         "applicability": "HUBZone acquisitions",
         "keywords": ["hubzone", "set-aside", "historically underutilized"]},
        {"part": "19", "section": "19.1405", "title": "Service-Disabled Veteran-Owned SB Set-Asides",
         "summary": "Contracting officer may set aside acquisitions for SDVOSB if there is a reasonable expectation of receiving offers from two or more SDVOSB concerns at fair market prices.",
         "applicability": "SDVOSB acquisitions",
         "keywords": ["sdvosb", "veteran", "service-disabled", "set-aside"]},
        {"part": "19", "section": "19.1505", "title": "Women-Owned Small Business Set-Asides (WOSB)",
         "summary": "Contracting officer may set aside for WOSB/EDWOSB in designated NAICS codes where WOSB are underrepresented or substantially underrepresented.",
         "applicability": "WOSB program acquisitions",
         "keywords": ["wosb", "women-owned", "edwosb", "set-aside"]},

        # Part 22 - Application of Labor Laws
        {"part": "22", "section": "22.406", "title": "Davis-Bacon Act Administration",
         "summary": "Requires payment of prevailing wages to laborers and mechanics on federally funded construction contracts exceeding $2,000. Contracting officer must include applicable wage determinations from DOL.",
         "applicability": "Construction contracts > $2,000",
         "keywords": ["davis-bacon", "prevailing wage", "construction", "labor"]},
        {"part": "22", "section": "22.1003", "title": "Service Contract Labor Standards",
         "summary": "Service Contract Act requires payment of prevailing wages and fringe benefits to service employees on contracts exceeding $2,500. Applicable to service contracts performed in the US.",
         "applicability": "Service contracts > $2,500",
         "keywords": ["service contract act", "prevailing wage", "labor standards", "fringe benefits"]},

        # Part 25 - Foreign Acquisition
        {"part": "25", "section": "25.101", "title": "Buy American Act — Supplies",
         "summary": "Buy American Act restricts acquisition of foreign supplies. Domestic end products required unless an exception applies (public interest, unreasonable cost, non-availability, trade agreements). Evaluation preference of 20-30% for domestic products.",
         "applicability": "Supply contracts",
         "keywords": ["buy american", "domestic", "foreign", "supplies", "trade agreements"]},

        # Part 31 - Contract Cost Principles
        {"part": "31", "section": "31.205", "title": "Selected Costs (Cost Principles)",
         "summary": "Determines allowability of specific cost categories: compensation, travel, insurance, depreciation, independent R&D. Key disallowable costs: entertainment, alcohol, lobbying, fines/penalties, bad debts.",
         "applicability": "Cost-reimbursement and T&M contracts",
         "keywords": ["allowable", "cost principles", "compensation", "travel", "overhead"]},

        # Part 32 - Contract Financing
        {"part": "32", "section": "32.006", "title": "Reduction or Suspension of Contract Payments",
         "summary": "Agency head may reduce or suspend payments upon substantial evidence of fraud. Contracting officer may withhold further payments pending resolution. Contractor entitled to 90% of approved payment requests on cost-reimbursement contracts.",
         "applicability": "All contracts with financing",
         "keywords": ["payment", "financing", "suspension", "fraud"]},

        # Part 36 - Construction and Architect-Engineer Contracts
        {"part": "36", "section": "36.602", "title": "Selection of Firms for A-E Contracts",
         "summary": "Brooks Act requires selection based on demonstrated competence and qualifications. Price is NOT a selection factor. Negotiate fair and reasonable price with most qualified firm.",
         "applicability": "Architect-Engineer contracts",
         "keywords": ["architect", "engineer", "a-e", "brooks act", "qualifications"]},

        # Part 37 - Service Contracting
        {"part": "37", "section": "37.102", "title": "Policy for Service Contracts",
         "summary": "Performance-Based Acquisition (PBA) methods preferred. Define requirements in terms of results, not process. Use measurable performance standards and quality assurance surveillance plans (QASP). Incentivize excellent performance.",
         "applicability": "Service acquisitions",
         "keywords": ["service", "performance-based", "pba", "qasp", "standards"]},

        # Part 42 - Contract Administration
        {"part": "42", "section": "42.302", "title": "Contract Administration Functions",
         "summary": "COR duties include: monitoring contractor performance, reviewing and approving invoices, maintaining documentation, reporting performance issues. COR must be designated in writing with specific duties.",
         "applicability": "Post-award contract administration",
         "keywords": ["administration", "cor", "monitoring", "performance", "invoice"]},

        # Part 46 - Quality Assurance
        {"part": "46", "section": "46.202-4", "title": "Higher-Level Quality Standards",
         "summary": "May require ISO 9001, ISO 13485 (medical devices), or equivalent quality management certifications. Contracting officer determines appropriate quality level based on criticality of supply/service.",
         "applicability": "Complex or critical acquisitions",
         "keywords": ["quality", "iso", "13485", "medical", "device", "standards", "certification"]},

        # Part 52 - Solicitation Provisions and Contract Clauses
        {"part": "52", "section": "52.212-1", "title": "Instructions to Offerors — Commercial Products/Services",
         "summary": "Standard instructions for offerors on commercial acquisitions. Simplified provisions. Technical proposal, past performance information, and price proposal typically required. Electronic submissions generally accepted.",
         "applicability": "Commercial acquisitions (FAR Part 12)",
         "keywords": ["instructions", "offeror", "commercial", "provision", "proposal"]},
        {"part": "52", "section": "52.212-4", "title": "Contract Terms and Conditions — Commercial Products/Services",
         "summary": "Standard commercial contract terms including: inspection/acceptance, assignment, disputes, payment, excusable delays, termination for cause/convenience. Tailorable through addenda.",
         "applicability": "Commercial contracts",
         "keywords": ["terms", "conditions", "commercial", "clause", "termination"]},

        # HHS/NIH Specific
        {"part": "HHSAR", "section": "352.270-5", "title": "HHS-Specific Acquisition Requirements",
         "summary": "Health and Human Services Acquisition Regulation supplements. Includes special clauses for research contracts, patient care, use of human subjects, animal welfare, and conflict of interest requirements specific to HHS/NIH.",
         "applicability": "HHS/NIH acquisitions",
         "keywords": ["hhs", "nih", "hhsar", "health", "research", "medical", "human subjects"]},
        {"part": "HHSAR", "section": "352.239-74", "title": "Electronic and Information Technology Accessibility (Section 508)",
         "summary": "Requires that all electronic and information technology (EIT) products and services meet Section 508 accessibility standards. Applies to all HHS IT acquisitions.",
         "applicability": "HHS IT acquisitions",
         "keywords": ["508", "accessibility", "eit", "electronic", "it", "hhs"]},
    ]

    # Search logic
    results = []
    query_terms = query.split()

    for entry in far_database:
        # Filter by parts if specified
        if parts_filter and entry["part"] not in parts_filter:
            continue

        # Score based on keyword matches
        score = 0
        text_fields = (entry["summary"] + " " + entry["title"] + " " + " ".join(entry["keywords"])).lower()
        for term in query_terms:
            if term in text_fields:
                score += 1
            # Bonus for keyword exact match
            if term in entry["keywords"]:
                score += 2

        if score > 0:
            results.append({**entry, "_score": score})

    # Sort by relevance
    results.sort(key=lambda x: x["_score"], reverse=True)

    # Remove score and limit results
    clauses = []
    for r in results[:15]:
        clauses.append({
            "part": r["part"],
            "section": r["section"],
            "title": r["title"],
            "summary": r["summary"],
            "applicability": r["applicability"],
        })

    # Fallback if no results
    if not clauses:
        clauses = [
            {"part": "1", "section": "1.102", "title": "Statement of Guiding Principles",
             "summary": "Deliver best value to the Government, satisfy the customer, minimize administrative costs, conduct business with integrity.",
             "applicability": "All federal acquisitions"},
            {"part": "10", "section": "10.001", "title": "Market Research Policy",
             "summary": "Agencies must conduct market research before developing requirements and before soliciting offers.",
             "applicability": "All acquisitions"},
        ]

    return {
        "query": params.get("query", ""),
        "parts_searched": parts_filter or ["all"],
        "results_count": len(clauses),
        "clauses": clauses,
        "source": "static_reference_dataset",
        "note": "Not live acquisition.gov lookup. Verify against current FAR/DFARS at acquisition.gov.",
    }


def _update_document_content(
    tenant_id: str,
    doc_key: str,
    content: str,
    change_source: str = "ai_edit",
    session_id: str = None,
) -> dict:
    """Update an existing document in S3.

    For package documents, creates a new version.
    For workspace documents, performs direct overwrite.
    """
    if not doc_key:
        return {"error": "update_existing_key is required but empty"}
    if not content:
        return {"error": "content is required for update"}

    user_id = _extract_user_id(session_id)
    bucket = os.getenv("S3_BUCKET", "eagle-documents-695681773636-dev")

    # Security check
    if not doc_key.startswith(f"eagle/{tenant_id}/{user_id}/"):
        return {"error": f"Access denied: document key must be within user's prefix"}

    # Detect if this is a package document
    is_package_doc = "/packages/" in doc_key

    if is_package_doc:
        from app.document_service import create_package_document_version

        # Extract package_id and doc_type from the key
        parts = doc_key.split("/")
        try:
            pkg_idx = parts.index("packages")
            package_id = parts[pkg_idx + 1]
            filename = parts[-1]
            doc_type = filename.split("_v")[0] if "_v" in filename else filename.rsplit(".", 1)[0]
            title = doc_type.replace("_", " ").title()
        except (ValueError, IndexError):
            return {"error": "Invalid package document key format"}

        result = create_package_document_version(
            tenant_id=tenant_id,
            package_id=package_id,
            doc_type=doc_type,
            content=content,
            title=title,
            file_type="md",
            created_by_user_id=user_id,
            session_id=session_id,
            change_source=change_source,
        )

        if not result.success:
            return {"error": result.error or "Failed to create document version"}

        return {
            "success": True,
            "mode": "update_package",
            "key": result.s3_key,
            "version": result.version,
            "document_id": result.document_id,
            "message": f"Document updated (version {result.version})",
        }
    else:
        # Workspace document: direct S3 overwrite
        try:
            s3 = _get_s3()
            s3.put_object(
                Bucket=bucket,
                Key=doc_key,
                Body=content.encode("utf-8"),
                ContentType="text/markdown; charset=utf-8",
            )
            return {
                "success": True,
                "mode": "update_workspace",
                "key": doc_key,
                "message": "Document saved",
            }
        except (ClientError, BotoCoreError) as e:
            logger.error("S3 put document error during update: %s", e, exc_info=True)
            return {"error": f"Failed to save document: {str(e)}"}


def _exec_create_document(params: dict, tenant_id: str, session_id: str = None) -> dict:
    """Generate acquisition documents and save to S3.

    Uses official S3 templates when available (DOCX/XLSX), falling back to
    markdown generators when templates are unavailable or fail to load.

    If `update_existing_key` is provided, updates the existing document instead
    of creating a new one.
    """
    from app.template_service import TemplateService

    # Handle update mode - update existing document
    update_key = params.get("update_existing_key")
    if update_key:
        return _update_document_content(
            tenant_id=tenant_id,
            doc_key=update_key,
            content=params.get("data", {}).get("content", ""),
            change_source="ai_edit",
            session_id=session_id,
        )

    doc_type = params.get("doc_type", "sow")
    title = params.get("title", "Untitled Acquisition")
    data = params.get("data", {})
    package_id = params.get("package_id")
    output_format = params.get("output_format", "docx")  # docx, xlsx, or md
    timestamp = time.strftime("%Y%m%d_%H%M%S")

    # Enrich missing/partial document fields from recent session context so
    # first-pass drafts are less generic when tools are invoked with sparse params.
    data = _augment_document_data_from_context(doc_type, title, data, session_id)

    # Document-viewer edit flow: when current content + explicit clear request is
    # present, patch the existing markdown directly instead of regenerating a
    # fresh template that can ignore section-level edit intent.
    inline_edited_content: str | None = None
    if doc_type == "sow":
        current_content = data.get("current_content")
        edit_request = str(data.get("edit_request", "") or "")
        if isinstance(current_content, str) and edit_request:
            inline_edited_content = _apply_sow_clear_edits(current_content, edit_request)

    # Validate doc_type
    valid_doc_types = {
        "sow", "igce", "market_research", "justification", "acquisition_plan",
        "eval_criteria", "security_checklist", "section_508", "cor_certification",
        "contract_type_justification",
    }
    if doc_type not in valid_doc_types:
        return {"error": f"Unknown document type: {doc_type}. Supported: {', '.join(sorted(valid_doc_types))}."}

    # Map doc_type to markdown generator functions (for fallback)
    markdown_generators = {
        "sow": _generate_sow,
        "igce": _generate_igce,
        "market_research": _generate_market_research,
        "justification": _generate_justification,
        "acquisition_plan": _generate_acquisition_plan,
        "eval_criteria": _generate_eval_criteria,
        "security_checklist": _generate_security_checklist,
        "section_508": _generate_section_508,
        "cor_certification": _generate_cor_certification,
        "contract_type_justification": _generate_contract_type_justification,
    }

    # Get user_id for S3 path
    user_id = _extract_user_id(session_id)

    if inline_edited_content is not None:
        content = inline_edited_content
        file_type = "md"
        source = "inline_edit_clear_sections"
        template_path = None
        result = None
    else:
        # Try template-based generation first
        try:
            service = TemplateService(tenant_id, user_id, markdown_generators)
            result = service.generate_document(doc_type, title, data, output_format)

            if not result.success:
                # Template service failed, use direct markdown fallback
                generator = markdown_generators.get(doc_type)
                if generator:
                    content = generator(title, data)
                    file_type = "md"
                    source = "markdown_fallback"
                    template_path = None
                else:
                    return {"error": f"No generator available for {doc_type}: {result.error}"}
            else:
                content = result.preview  # For response display
                file_type = result.file_type
                source = result.source
                template_path = result.template_path

                # Some official templates are boilerplate-only and may not expose
                # machine-replaceable placeholders. If the extracted preview is still
                # generic, return markdown generator content for the editable response
                # while still saving the populated binary artifact to S3.
                if _looks_like_unfilled_template_preview(doc_type, content):
                    generator = markdown_generators.get(doc_type)
                    if generator:
                        content = generator(title, data)
                        source = f"{source}+markdown_context_response"
                        logger.warning(
                            "Template preview looked unfilled for doc_type=%s; using markdown generator for response content",
                            doc_type,
                        )

        except ImportError as e:
            # python-docx or openpyxl not available, use markdown
            logger.warning("Template libraries unavailable: %s, using markdown fallback", e)
            generator = markdown_generators.get(doc_type)
            if generator:
                content = generator(title, data)
                file_type = "md"
                source = "markdown_fallback"
                template_path = None
                result = None
            else:
                return {"error": f"No generator available for {doc_type}"}

    # Determine file extension and content to save
    ext = file_type if file_type in ("docx", "xlsx") else "md"
    bucket = os.getenv("S3_BUCKET", "eagle-documents-695681773636-dev")
    content_to_store = (
        result.content if result and result.success and file_type in ("docx", "xlsx")
        else content
    )

    # Package mode: route through canonical package document service.
    if package_id:
        from app.document_service import create_package_document_version

        canonical = create_package_document_version(
            tenant_id=tenant_id,
            package_id=package_id,
            doc_type=doc_type,
            content=content_to_store,
            title=title,
            file_type=ext,
            created_by_user_id=user_id,
            session_id=session_id,
            change_source="agent_tool",
            template_id=params.get("template_id") or template_path,
        )
        if not canonical.success:
            return {"error": canonical.error or "Failed to create package document"}

        response = {
            "mode": "package",
            "package_id": package_id,
            "document_id": canonical.document_id,
            "doc_type": doc_type,
            "document_type": doc_type,
            "version": canonical.version,
            "status": canonical.status or "draft",
            "s3_key": canonical.s3_key,
            "s3_location": f"s3://{bucket}/{canonical.s3_key}",
            "file_type": ext,
            "source": source,
            "title": title,
            "content": content,
            "word_count": len(content.split()),
            "generated_at": datetime.utcnow().isoformat(),
            "note": "This is a draft document. Review and customize before official use.",
        }
        if template_path:
            response["template_path"] = template_path
        return response

    s3_key = f"eagle/{tenant_id}/{user_id}/documents/{doc_type}_{timestamp}.{ext}"

    # Save to S3
    try:
        s3 = _get_s3()
        if isinstance(content_to_store, bytes):
            # Save binary content (DOCX/XLSX)
            s3.put_object(
                Bucket=bucket,
                Key=s3_key,
                Body=content_to_store,
                ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                if file_type == "docx"
                else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        else:
            # Save markdown content
            s3.put_object(Bucket=bucket, Key=s3_key, Body=content_to_store.encode("utf-8"))
        save_status = "saved"
        save_location = f"s3://{bucket}/{s3_key}"
    except (ClientError, BotoCoreError) as e:
        save_status = "generated_but_not_saved"
        save_location = f"S3 save failed: {str(e)}"
        logger.warning("Failed to save document to S3: %s", e)

    response = {
        "document_type": doc_type,
        "title": title,
        "status": save_status,
        "s3_location": save_location,
        "s3_key": s3_key,
        "file_type": file_type,
        "source": source,
        "content": content,
        "word_count": len(content.split()),
        "generated_at": datetime.utcnow().isoformat(),
        "note": "This is a draft document. Review and customize before official use.",
    }

    if template_path:
        response["template_path"] = template_path

    return response


def _generate_sow(title: str, data: dict) -> str:
    desc = data.get("description", "the required supplies/services")
    pop = data.get("period_of_performance", "12 months from date of award")
    deliverables = data.get("deliverables", [
        "Project Management Plan — within 30 days of award",
        "Monthly Status Reports — NLT 5th business day of each month",
        "Final Delivery/Acceptance Report — within 30 days of contract completion",
    ])
    tasks = data.get("tasks", [
        "Planning and Requirements Analysis",
        "Implementation and Delivery",
        "Testing and Quality Assurance",
        "Training and Knowledge Transfer",
        "Ongoing Support and Maintenance",
    ])
    scope_override = str(data.get("scope", "") or "").strip()
    if scope_override:
        scope_text = scope_override
    else:
        scope_text = (
            "The contractor shall provide all personnel, equipment, supplies, facilities,\n"
            "transportation, tools, materials, supervision, and other items and non-personal\n"
            f"services necessary to {desc}, as defined in this SOW."
        )

    deliverables_text = "\n".join(f"   {i+1}. {d}" for i, d in enumerate(deliverables))
    tasks_text = "\n".join(f"   5.{i+1} Task {i+1}: {t}" for i, t in enumerate(tasks))

    return f"""# STATEMENT OF WORK (SOW)
## {title}
### National Cancer Institute (NCI)

**Document Status:** DRAFT — Generated {time.strftime('%Y-%m-%d %H:%M UTC')}

---

## 1. BACKGROUND AND PURPOSE

The National Cancer Institute (NCI), part of the National Institutes of Health (NIH),
requires {desc}. This Statement of Work (SOW) describes the tasks, deliverables,
and performance requirements for this acquisition.

## 2. SCOPE

{scope_text}

## 3. PERIOD OF PERFORMANCE

{pop}

## 4. APPLICABLE DOCUMENTS AND STANDARDS

- Federal Acquisition Regulation (FAR)
- Health and Human Services Acquisition Regulation (HHSAR)
- FAR 52.212-4 Contract Terms and Conditions — Commercial Products/Services
- Section 508 Accessibility Standards (if applicable)
- ISO 13485 Quality Management for Medical Devices (if applicable)
- NIH Information Security Standards

## 5. TASKS AND REQUIREMENTS

{tasks_text}

## 6. DELIVERABLES

{deliverables_text}

## 7. GOVERNMENT-FURNISHED PROPERTY (GFP)

[To be determined based on final requirements]

## 8. QUALITY ASSURANCE SURVEILLANCE PLAN (QASP)

The Government will evaluate contractor performance using a Quality Assurance
Surveillance Plan (QASP). Performance standards and acceptable quality levels
will be defined for each major task area.

## 9. PLACE OF PERFORMANCE

National Cancer Institute
National Institutes of Health
Bethesda, MD 20892

[Or as otherwise specified in the contract]

## 10. SECURITY REQUIREMENTS

[To be determined based on data sensitivity and access requirements]

---
*This document was generated by EAGLE — NCI Acquisition Assistant*
"""


def _generate_igce(title: str, data: dict) -> str:
    line_items = data.get("line_items", [])
    overhead_rate = data.get("overhead_rate", 12)
    contingency_rate = data.get("contingency_rate", 10)

    rows = []
    subtotal = 0
    for item in line_items:
        desc = item.get("description", "Item")
        qty = item.get("quantity", 1)
        unit = item.get("unit_price", 0)
        total = qty * unit
        subtotal += total
        rows.append(f"| {desc} | {qty} | ${unit:,.2f} | ${total:,.2f} |")

    overhead = subtotal * (overhead_rate / 100)
    contingency = subtotal * (contingency_rate / 100)
    grand_total = subtotal + overhead + contingency

    items_table = "\n".join(rows) if rows else "| [No line items provided] | - | - | - |"

    return f"""# INDEPENDENT GOVERNMENT COST ESTIMATE (IGCE)
## {title}
### National Cancer Institute (NCI)

**Prepared:** {time.strftime('%Y-%m-%d')}
**Document Status:** DRAFT — For Budget Planning Purposes

---

## 1. PURPOSE

This Independent Government Cost Estimate (IGCE) provides a detailed estimate
of the anticipated costs for: {title}.

## 2. METHODOLOGY

This estimate is based on:
- GSA Schedule pricing and published rates
- Historical contract award data from FPDS
- Market research and vendor quotations
- Bureau of Labor Statistics data

## 3. COST BREAKDOWN

| Description | Qty | Unit Price | Total |
|---|---|---|---|
{items_table}

**Subtotal:** ${subtotal:,.2f}

**Overhead ({overhead_rate}%):** ${overhead:,.2f}

**Contingency ({contingency_rate}%):** ${contingency:,.2f}

---

### **TOTAL ESTIMATED COST: ${grand_total:,.2f}**

---

## 4. ASSUMPTIONS AND LIMITATIONS

- Estimates based on current market conditions
- Prices subject to change based on competition
- Contingency included for unforeseen requirements
- Does not include Government-furnished equipment costs

## 5. CONFIDENCE LEVEL

**Medium** — Recommend validating with current market data and vendor quotes.

---
*This document was generated by EAGLE — NCI Acquisition Assistant*
"""


def _generate_market_research(title: str, data: dict) -> str:
    description = data.get("description", title)
    naics = data.get("naics_code", "TBD")
    vendors = data.get("vendors", [])

    vendor_text = ""
    if vendors:
        for v in vendors:
            vendor_text += f"- **{v.get('name', 'TBD')}** — {v.get('size', 'TBD')}, Contract vehicles: {', '.join(v.get('vehicles', ['TBD']))}\n"
    else:
        vendor_text = "- [Market research in progress — vendors to be identified]\n"

    return f"""# MARKET RESEARCH REPORT
## {title}
### National Cancer Institute (NCI)

**Date:** {time.strftime('%Y-%m-%d')}
**NAICS Code:** {naics}
**Document Status:** DRAFT

---

## 1. DESCRIPTION OF NEED

{description}

## 2. SOURCES CONSULTED

- SAM.gov (System for Award Management)
- GSA Advantage / GSA eLibrary
- FPDS.gov (Federal Procurement Data System)
- Industry publications and conferences
- Previous NIH/NCI contract history
- Sources Sought notice responses

## 3. POTENTIAL SOURCES

{vendor_text}

## 4. SMALL BUSINESS ANALYSIS

[Analysis of small business availability and potential for set-aside]

## 5. COMMERCIAL AVAILABILITY

[Analysis of whether commercial products/services meet requirements]

## 6. RECOMMENDED ACQUISITION STRATEGY

[Based on market research findings]

## 7. RECOMMENDED CONTRACT VEHICLE

- [ ] GSA Multiple Award Schedule (MAS)
- [ ] NIH NITAAC CIO-SP3
- [ ] Full and Open Competition (FAR Part 15)
- [ ] Small Business Set-Aside (FAR Part 19)

---
*This document was generated by EAGLE — NCI Acquisition Assistant*
"""


def _generate_justification(title: str, data: dict) -> str:
    authority = data.get("authority", "FAR 6.302-1 — Only One Responsible Source")
    contractor = data.get("contractor", "[Contractor Name]")
    value = data.get("estimated_value", "[Estimated Value]")
    rationale = data.get("rationale", "[Provide detailed rationale for sole source]")

    return f"""# JUSTIFICATION AND APPROVAL (J&A)
## Other Than Full and Open Competition
### {title}
### National Cancer Institute (NCI)

**Date:** {time.strftime('%Y-%m-%d')}
**Estimated Value:** {value}
**Document Status:** DRAFT

---

## 1. CONTRACTING ACTIVITY

National Cancer Institute (NCI)
National Institutes of Health (NIH)
Bethesda, MD 20892

## 2. DESCRIPTION OF ACTION

Sole source award to {contractor} for {title}.

## 3. DESCRIPTION OF SUPPLIES/SERVICES

[Detailed description of requirements]

## 4. AUTHORITY CITED

{authority}

## 5. REASON FOR AUTHORITY

{rationale}

## 6. EFFORTS TO OBTAIN COMPETITION

[Description of market research and efforts to identify competitive sources]

## 7. DETERMINATION BY THE CONTRACTING OFFICER

The Contracting Officer has determined that the anticipated cost to the
Government will be fair and reasonable based on:
- Market research
- Price analysis
- Historical pricing data

## 8. ACTIONS TO REMOVE BARRIERS TO COMPETITION

[Actions planned for future competitive acquisitions]

## 9. APPROVAL

| Role | Name | Signature | Date |
|---|---|---|---|
| Contracting Officer | | | |
| Competition Advocate | | | |
| [Additional approvals as required by FAR 6.304] | | | |

---
*This document was generated by EAGLE — NCI Acquisition Assistant*
"""


def _generate_acquisition_plan(title: str, data: dict) -> str:
    """Generate a streamlined Acquisition Plan (AP)."""
    desc = data.get("description", "the required supplies/services")
    value = data.get("estimated_value", "[TBD]")
    pop = data.get("period_of_performance", "12 months from date of award")
    competition = data.get("competition", "Full and Open Competition")
    contract_type = data.get("contract_type", "Firm-Fixed-Price")
    set_aside = data.get("set_aside", "To be determined based on market research")
    funding_by_fy = data.get("funding_by_fy", [])

    funding_table = ""
    if funding_by_fy:
        for entry in funding_by_fy:
            fy = entry.get("fiscal_year", "FY20XX")
            amt = entry.get("amount", "$0")
            funding_table += f"| {fy} | {amt} |\n"
    else:
        funding_table = "| FY2026 | [TBD] |\n| FY2027 | [TBD] |\n"

    return f"""# ACQUISITION PLAN (AP) — Streamlined Format
## {title}
### National Cancer Institute (NCI)

**Date:** {time.strftime('%Y-%m-%d')}
**Estimated Value:** {value}
**Document Status:** DRAFT

---

## SECTION 1: ACQUISITION BACKGROUND AND OBJECTIVES

### 1.1 Statement of Need

{desc}

### 1.2 Applicable Conditions

- **Period of Performance:** {pop}
- **Estimated Total Value:** {value}
- **Funding by Fiscal Year:**

| Fiscal Year | Amount |
|-------------|--------|
{funding_table}

### 1.3 Cost

The estimated cost is based on independent government cost estimates,
market research, and historical pricing data for similar acquisitions.

### 1.4 Capability and Performance

The contractor must demonstrate capability to deliver the required
services/supplies in accordance with the Statement of Work.

### 1.5 Delivery and Schedule

Delivery schedule will be defined in the SOW. Key milestones are
tied to the period of performance: {pop}.

## SECTION 2: PLAN OF ACTION

### 2.1 Competitive Requirements

**Competition Strategy:** {competition}

### 2.2 Source Selection

Evaluation factors will be established in accordance with FAR Part 15.
Best value tradeoff or lowest price technically acceptable as appropriate.

### 2.3 Acquisition Considerations

- **Contract Type:** {contract_type}
- **Set-Aside:** {set_aside}
- **Applicable FAR/HHSAR Clauses:** To be determined

## SECTION 3: MILESTONES

| Milestone | Target Date |
|-----------|-------------|
| Acquisition Plan Approval | [TBD] |
| Solicitation Issue | [TBD] |
| Proposals Due | [TBD] |
| Evaluation Complete | [TBD] |
| Award | [TBD] |

## SECTION 4: APPROVALS

| Role | Name | Signature | Date |
|------|------|-----------|------|
| Program/Project Officer | | __________ | |
| Contracting Officer | | __________ | |
| Competition Advocate | | __________ | |

---
*This document was generated by EAGLE — NCI Acquisition Assistant*
"""


def _generate_eval_criteria(title: str, data: dict) -> str:
    """Generate Evaluation Criteria document."""
    factors = data.get("factors", [
        {"name": "Technical Approach", "weight": "Most Important"},
        {"name": "Past Performance", "weight": "Important"},
        {"name": "Price", "weight": "Least Important"},
    ])
    method = data.get("evaluation_method", "Best Value Tradeoff")
    rating_scale = data.get("rating_scale", [
        ("Outstanding", "Exceeds requirements; very high probability of success"),
        ("Good", "Meets requirements; high probability of success"),
        ("Acceptable", "Meets minimum requirements; reasonable probability of success"),
        ("Marginal", "Does not clearly meet some requirements; low probability of success"),
        ("Unacceptable", "Fails to meet minimum requirements; no probability of success"),
    ])

    factors_text = ""
    for i, f in enumerate(factors, 1):
        name = f if isinstance(f, str) else f.get("name", f"Factor {i}")
        weight = "" if isinstance(f, str) else f" ({f.get('weight', '')})"
        factors_text += f"### Factor {i}: {name}{weight}\n\n[Detailed description of evaluation criteria]\n\n"

    scale_text = ""
    for rating, desc in rating_scale:
        scale_text += f"| {rating} | {desc} |\n"

    return f"""# EVALUATION CRITERIA
## {title}
### National Cancer Institute (NCI)

**Date:** {time.strftime('%Y-%m-%d')}
**Evaluation Method:** {method}
**Document Status:** DRAFT

---

## 1. EVALUATION FACTORS

Evaluation factors are listed in descending order of importance.

{factors_text}

## 2. RATING SCALE

| Rating | Description |
|--------|-------------|
{scale_text}

## 3. EVALUATION PROCESS

- Technical proposals will be evaluated by a Technical Evaluation Panel (TEP)
- Past performance will be assessed using CPARS and references
- Price will be evaluated for reasonableness and realism
- Evaluation will follow FAR 15.305 procedures

## 4. BASIS FOR AWARD

Award will be made to the offeror whose proposal represents the
best value to the Government, considering technical merit and price.

---
*This document was generated by EAGLE — NCI Acquisition Assistant*
"""


def _generate_security_checklist(title: str, data: dict) -> str:
    """Generate IT Security Checklist."""
    it_systems = data.get("it_systems_involved", "[TBD]")
    impact_level = data.get("impact_level", "Moderate")
    cloud_services = data.get("cloud_services", False)

    return f"""# IT SECURITY CHECKLIST
## {title}
### National Cancer Institute (NCI)

**Date:** {time.strftime('%Y-%m-%d')}
**Document Status:** DRAFT

---

## 1. SECURITY ASSESSMENT QUESTIONS

| # | Question | Yes | No | N/A |
|---|----------|-----|----|-----|
| 1 | Will contractor access IT systems or networks? | | | |
| 2 | Will contractor access the NIH network? | | | |
| 3 | Will contractor handle Personally Identifiable Information (PII)? | | | |
| 4 | Is FISMA compliance required? | | | |
| 5 | Are security clearances required? | | | |
| 6 | Will data leave NIH facilities or networks? | | | |
| 7 | Are cloud services involved? | {'[x]' if cloud_services else '[ ]'} | {'[ ]' if cloud_services else '[x]'} | |
| 8 | Is FedRAMP authorization required? | | | |
| 9 | Will contractor develop or modify software? | | | |
| 10 | Are there data encryption requirements? | | | |

## 2. IMPACT LEVEL DETERMINATION

**Selected Impact Level:** {impact_level}

| Level | Description |
|-------|-------------|
| Low | Limited adverse effect on operations |
| Moderate | Serious adverse effect on operations |
| High | Severe or catastrophic adverse effect |

## 3. REQUIRED FAR/HHSAR CLAUSES

- [ ] FAR 52.239-1 — Privacy or Security Safeguards
- [ ] HHSAR 352.239-73 — Electronic Information and Technology Accessibility
- [ ] FAR 52.204-21 — Basic Safeguarding of Covered Contractor Information Systems
- [ ] NIST SP 800-171 — Protecting Controlled Unclassified Information (if applicable)

## 4. IT SYSTEMS INVOLVED

{it_systems}

## 5. ISSM/ISSO REVIEW

| Role | Name | Signature | Date |
|------|------|-----------|------|
| ISSM | | __________ | |
| ISSO | | __________ | |
| COR | | __________ | |

---
*This document was generated by EAGLE — NCI Acquisition Assistant*
"""


def _generate_section_508(title: str, data: dict) -> str:
    """Generate Section 508 Compliance Statement."""
    product_types = data.get("product_types", [])
    exception_claimed = data.get("exception_claimed", False)
    vpat_status = data.get("vpat_status", "Not yet reviewed")

    product_checklist = ""
    all_types = [
        "Software Applications", "Web-based Information",
        "Telecommunications Products", "Video and Multimedia",
        "Self-Contained Products", "Desktop and Portable Computers",
        "Electronic Documents",
    ]
    for pt in all_types:
        checked = "[x]" if pt in product_types else "[ ]"
        product_checklist += f"- {checked} {pt}\n"

    return f"""# SECTION 508 COMPLIANCE STATEMENT
## {title}
### National Cancer Institute (NCI)

**Date:** {time.strftime('%Y-%m-%d')}
**Document Status:** DRAFT

---

## 1. APPLICABILITY DETERMINATION

Does this acquisition include Electronic and Information Technology (EIT)?

- [ ] Yes — Section 508 applies
- [ ] No — Section 508 does not apply (provide justification below)

## 2. PRODUCT TYPE CHECKLIST

{product_checklist}

## 3. EXCEPTION DETERMINATION

**Exception Claimed:** {'Yes' if exception_claimed else 'No'}

| Exception Type | Applicable |
|---------------|------------|
| National Security | [ ] |
| Acquired by contractor incidental to contract | [ ] |
| Located in spaces frequented only by service personnel | [ ] |
| Micro-purchase | [ ] |
| Fundamental alteration | [ ] |
| Undue burden | [ ] |

## 4. VPAT/ACR STATUS

**Status:** {vpat_status}

- [ ] Vendor has provided VPAT/Accessibility Conformance Report
- [ ] VPAT reviewed and acceptable
- [ ] Remediation plan required
- [ ] Not applicable

## 5. CONTRACT LANGUAGE

Include FAR 39.2 and Section 508 requirements in:
- [ ] Statement of Work
- [ ] Evaluation Criteria
- [ ] Contract Clauses

---
*This document was generated by EAGLE — NCI Acquisition Assistant*
"""


def _generate_cor_certification(title: str, data: dict) -> str:
    """Generate COR Certification document."""
    nominee_name = data.get("nominee_name", "[Nominee Name]")
    nominee_title = data.get("nominee_title", "[Title]")
    nominee_org = data.get("nominee_org", "National Cancer Institute")
    nominee_phone = data.get("nominee_phone", "[Phone]")
    nominee_email = data.get("nominee_email", "[Email]")
    fac_cor_level = data.get("fac_cor_level", "II")
    contract_number = data.get("contract_number", "[TBD]")

    return f"""# CONTRACTING OFFICER'S REPRESENTATIVE (COR) CERTIFICATION
## {title}
### National Cancer Institute (NCI)

**Date:** {time.strftime('%Y-%m-%d')}
**Contract Number:** {contract_number}
**Document Status:** DRAFT

---

## 1. COR NOMINEE INFORMATION

| Field | Value |
|-------|-------|
| Name | {nominee_name} |
| Title | {nominee_title} |
| Organization | {nominee_org} |
| Phone | {nominee_phone} |
| Email | {nominee_email} |
| FAC-COR Level | Level {fac_cor_level} |

## 2. FAC-COR CERTIFICATION

| Level | Requirements | Applicable |
|-------|-------------|------------|
| I | 8 hours CLC training, low-risk contracts | {'[x]' if fac_cor_level == 'I' else '[ ]'} |
| II | 40 hours CLC training, moderate-risk contracts | {'[x]' if fac_cor_level == 'II' else '[ ]'} |
| III | 60 hours CLC training, high-risk contracts | {'[x]' if fac_cor_level == 'III' else '[ ]'} |

## 3. DELEGATED DUTIES

The COR is authorized to perform the following duties:

- [x] Provide technical direction (within scope of contract)
- [x] Review and approve invoices for payment
- [x] Accept or reject deliverables
- [x] Monitor contractor performance
- [x] Maintain COR files and documentation
- [x] Report issues to the Contracting Officer

## 4. LIMITATIONS

The COR may NOT:

- Direct changes to the scope of work
- Authorize additional costs or funding
- Extend the period of performance
- Make any contractual commitments or modifications
- Direct the contractor to perform work outside the contract

## 5. SIGNATURES

| Role | Name | Signature | Date |
|------|------|-----------|------|
| COR Nominee | {nominee_name} | __________ | |
| Contracting Officer | | __________ | |
| Supervisor | | __________ | |

---
*This document was generated by EAGLE — NCI Acquisition Assistant*
"""


def _generate_contract_type_justification(title: str, data: dict) -> str:
    """Generate Contract Type Justification (Determination & Findings)."""
    contract_type = data.get("contract_type", "Firm-Fixed-Price")
    rationale = data.get("rationale", "[Provide rationale for selected contract type]")
    risk_to_govt = data.get("risk_to_government", "Low")
    risk_to_contractor = data.get("risk_to_contractor", "Moderate")
    value = data.get("estimated_value", "[TBD]")

    return f"""# CONTRACT TYPE JUSTIFICATION
## Determination and Findings (D&F)
### {title}
### National Cancer Institute (NCI)

**Date:** {time.strftime('%Y-%m-%d')}
**Estimated Value:** {value}
**Recommended Contract Type:** {contract_type}
**Document Status:** DRAFT

---

## 1. FINDINGS

### 1.1 Description of Acquisition

{title}

### 1.2 Contract Type Analysis

| Contract Type | Risk to Govt | Risk to Contractor | Recommended |
|--------------|-------------|-------------------|-------------|
| Firm-Fixed-Price (FFP) | Low | High | {'[x]' if 'fixed' in contract_type.lower() else '[ ]'} |
| Time & Materials (T&M) | High | Low | {'[x]' if 't&m' in contract_type.lower() or 'time' in contract_type.lower() else '[ ]'} |
| Cost-Reimbursement (CR) | High | Low | {'[x]' if 'cost' in contract_type.lower() else '[ ]'} |
| Labor-Hour (LH) | Moderate | Moderate | {'[x]' if 'labor' in contract_type.lower() else '[ ]'} |

### 1.3 Rationale for Contract Type Selection

{rationale}

### 1.4 Risk Assessment

- **Risk to Government:** {risk_to_govt}
- **Risk to Contractor:** {risk_to_contractor}

### 1.5 Requirements Definition

| Criteria | Assessment |
|----------|-----------|
| Requirements well-defined? | [Yes/No] |
| Level of effort estimable? | [Yes/No] |
| Adequate price competition expected? | [Yes/No] |
| Historical pricing available? | [Yes/No] |

## 2. DETERMINATION

Based on the above findings, I determine that a {contract_type} contract
is in the best interest of the Government for this acquisition because:

1. {rationale}
2. The risk allocation is appropriate for this type of requirement
3. The contract type is consistent with FAR 16.1 guidance

## 3. APPROVAL

| Role | Name | Signature | Date |
|------|------|-----------|------|
| Contracting Officer | | __________ | |
| [Head of Contracting Activity — if required] | | __________ | |

---
*This document was generated by EAGLE — NCI Acquisition Assistant*
"""


def _exec_get_intake_status(params: dict, tenant_id: str, session_id: str = None) -> dict:
    """Check intake status — queries DynamoDB and S3 for completeness."""
    intake_id = params.get("intake_id", "")
    user_id = _extract_user_id(session_id)

    # Check what documents exist in S3 (per-user path)
    existing_docs = []
    doc_types_found = set()
    try:
        s3 = _get_s3()
        resp = s3.list_objects_v2(
            Bucket=os.getenv("S3_BUCKET", "eagle-documents-695681773636-dev"),
            Prefix=f"eagle/{tenant_id}/{user_id}/documents/",
            MaxKeys=50,
        )
        for obj in resp.get("Contents", []):
            key = obj["Key"]
            name = key.split("/")[-1]
            existing_docs.append({
                "key": key,
                "name": name,
                "size": obj["Size"],
                "last_modified": obj["LastModified"].isoformat(),
            })
            # Detect document types
            for dt in ("sow", "igce", "market_research", "justification",
                        "acquisition_plan", "eval_criteria", "security_checklist",
                        "section_508", "cor_certification", "contract_type_justification"):
                if dt in name.lower():
                    doc_types_found.add(dt)
    except (ClientError, BotoCoreError) as e:
        logger.warning("Could not check S3 for intake status: %s", e)

    # Check DynamoDB for intake records
    intake_records = []
    try:
        from boto3.dynamodb.conditions import Key as DDBKey
        ddb = _get_dynamodb()
        table = ddb.Table("eagle")
        resp = table.query(
            KeyConditionExpression=DDBKey("PK").eq(f"INTAKE#{tenant_id}")
        )
        intake_records = [_serialize_ddb_item(i) for i in resp.get("Items", [])]
    except (ClientError, BotoCoreError) as e:
        logger.warning("Could not check DynamoDB for intake status: %s", e)

    # Compute completeness
    required_docs = {
        "sow": "Statement of Work",
        "igce": "Independent Government Cost Estimate",
        "market_research": "Market Research Report",
        "justification": "Justification & Approval (if sole source)",
        "acquisition_plan": "Acquisition Plan",
        "eval_criteria": "Evaluation Criteria",
        "security_checklist": "IT Security Checklist",
        "section_508": "Section 508 Compliance Statement",
        "cor_certification": "COR Certification",
        "contract_type_justification": "Contract Type Justification",
    }

    # These doc types are conditional — only required in certain situations
    conditional_docs = {
        "justification", "eval_criteria", "security_checklist",
        "section_508", "contract_type_justification",
    }

    completed = []
    pending = []
    for doc_key, doc_name in required_docs.items():
        if doc_key in doc_types_found:
            completed.append({"document": doc_name, "type": doc_key, "status": "✅ Complete"})
        elif doc_key in conditional_docs:
            pending.append({"document": doc_name, "type": doc_key, "status": "🔲 Conditional", "priority": "Conditional"})
        else:
            pending.append({"document": doc_name, "type": doc_key, "status": "🔲 Not Started", "priority": "High"})

    total = len(required_docs) - len(conditional_docs)  # Exclude conditional docs
    done = len([c for c in completed if c["type"] not in conditional_docs])
    pct = int((done / total) * 100) if total > 0 else 0

    return {
        "intake_id": intake_id or f"EAGLE-{tenant_id}-{int(time.time()) % 100000:05d}",
        "tenant_id": tenant_id,
        "completion_pct": f"{pct}%",
        "documents_completed": completed,
        "documents_pending": pending,
        "existing_files": existing_docs,
        "intake_records": intake_records[:10],
        "next_action": pending[0]["document"] if pending else "All required documents complete!",
        "estimated_completion": "Depends on remaining document generation",
    }


# ── Intake Workflow Engine ───────────────────────────────────────────

WORKFLOW_STAGES = [
    {
        "id": "requirements",
        "name": "Requirements Gathering",
        "description": "Collect acquisition details: what, why, when, how much",
        "fields": ["title", "description", "estimated_value", "period_of_performance", "urgency"],
        "next_actions": ["Describe the acquisition need", "Provide estimated value", "Specify timeline"],
    },
    {
        "id": "compliance",
        "name": "Compliance Check",
        "description": "Verify FAR/DFAR requirements and acquisition thresholds",
        "fields": ["acquisition_type", "threshold", "competition_required", "far_citations", "small_business"],
        "next_actions": ["Search FAR for applicable regulations", "Determine acquisition type", "Check competition requirements"],
    },
    {
        "id": "documents",
        "name": "Document Generation",
        "description": "Generate required acquisition documents",
        "fields": ["sow_generated", "igce_generated", "market_research_generated", "justification_generated"],
        "next_actions": ["Generate Statement of Work", "Generate IGCE", "Generate Market Research"],
    },
    {
        "id": "review",
        "name": "Review & Submit",
        "description": "Final review and package submission",
        "fields": ["reviewed_by", "review_notes", "submitted_at", "approval_status"],
        "next_actions": ["Review all documents", "Add any notes", "Submit for approval"],
    },
]


def _exec_intake_workflow(params: dict, tenant_id: str) -> dict:
    """Manage the acquisition intake workflow with stage-based progression."""
    action = params.get("action", "status")
    intake_id = params.get("intake_id")
    data = params.get("data", {})
    
    # In-memory workflow state (would be DynamoDB in production)
    # For demo, we use a simple file-based approach
    workflow_file = f"/tmp/eagle_workflow_{tenant_id}.json"
    
    def load_workflow() -> dict:
        try:
            with open(workflow_file, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
    
    def save_workflow(state: dict):
        with open(workflow_file, "w") as f:
            json.dump(state, f, indent=2, default=str)
    
    workflows = load_workflow()
    
    if action == "start":
        # Create a new intake workflow
        new_id = f"EAGLE-{tenant_id[:8]}-{int(time.time()) % 100000:05d}"
        workflows[new_id] = {
            "intake_id": new_id,
            "tenant_id": tenant_id,
            "created_at": datetime.utcnow().isoformat(),
            "current_stage": 0,
            "stage_name": WORKFLOW_STAGES[0]["name"],
            "status": "in_progress",
            "stages_completed": [],
            "data": data,
        }
        save_workflow(workflows)
        
        stage = WORKFLOW_STAGES[0]
        return {
            "action": "started",
            "intake_id": new_id,
            "message": f"🚀 New intake workflow started: {new_id}",
            "current_stage": {
                "number": 1,
                "name": stage["name"],
                "description": stage["description"],
            },
            "next_actions": stage["next_actions"],
            "fields_to_collect": stage["fields"],
            "tip": "Provide the acquisition details, and I'll guide you through each step.",
        }
    
    elif action == "status":
        # Get current workflow status
        if not intake_id:
            # Return most recent workflow
            if not workflows:
                return {
                    "message": "No active intake workflows. Use action='start' to begin a new intake.",
                    "hint": "Try: 'Start a new intake for cloud services'",
                }
            intake_id = list(workflows.keys())[-1]
        
        wf = workflows.get(intake_id)
        if not wf:
            return {"error": f"Intake {intake_id} not found"}
        
        current_idx = wf.get("current_stage", 0)
        stage = WORKFLOW_STAGES[current_idx] if current_idx < len(WORKFLOW_STAGES) else None
        
        progress_bar = "".join(["✅" if i < current_idx else "🔲" for i in range(len(WORKFLOW_STAGES))])
        
        return {
            "intake_id": intake_id,
            "status": wf.get("status", "in_progress"),
            "progress": f"{current_idx}/{len(WORKFLOW_STAGES)} stages",
            "progress_bar": progress_bar,
            "current_stage": {
                "number": current_idx + 1,
                "name": stage["name"] if stage else "Complete",
                "description": stage["description"] if stage else "All stages complete",
            } if stage else {"name": "Complete", "description": "Workflow finished"},
            "stages_completed": wf.get("stages_completed", []),
            "next_actions": stage["next_actions"] if stage else ["Submit for final approval"],
            "data_collected": wf.get("data", {}),
            "created_at": wf.get("created_at"),
        }
    
    elif action == "advance":
        # Move to next stage
        if not intake_id:
            if not workflows:
                return {"error": "No active workflow. Start one first with action='start'"}
            intake_id = list(workflows.keys())[-1]
        
        wf = workflows.get(intake_id)
        if not wf:
            return {"error": f"Intake {intake_id} not found"}
        
        current_idx = wf.get("current_stage", 0)
        
        # Save stage data
        if data:
            wf.setdefault("data", {}).update(data)
        
        # Mark current stage complete
        completed_stage = WORKFLOW_STAGES[current_idx]["name"]
        wf.setdefault("stages_completed", []).append({
            "stage": completed_stage,
            "completed_at": datetime.utcnow().isoformat(),
        })
        
        # Advance to next stage
        next_idx = current_idx + 1
        if next_idx >= len(WORKFLOW_STAGES):
            wf["current_stage"] = next_idx
            wf["status"] = "ready_for_review"
            wf["stage_name"] = "Complete"
            save_workflow(workflows)
            
            return {
                "action": "workflow_complete",
                "intake_id": intake_id,
                "message": "🎉 All stages complete! Intake package ready for review.",
                "stages_completed": wf["stages_completed"],
                "data_collected": wf["data"],
                "next_steps": [
                    "Review all generated documents",
                    "Use get_intake_status to see document checklist",
                    "Submit for supervisor approval",
                ],
            }
        
        wf["current_stage"] = next_idx
        wf["stage_name"] = WORKFLOW_STAGES[next_idx]["name"]
        save_workflow(workflows)
        
        next_stage = WORKFLOW_STAGES[next_idx]
        progress_bar = "".join(["✅" if i <= current_idx else "🔲" for i in range(len(WORKFLOW_STAGES))])
        
        return {
            "action": "advanced",
            "intake_id": intake_id,
            "message": f"✅ Completed: {completed_stage}",
            "progress": f"{next_idx}/{len(WORKFLOW_STAGES)} stages",
            "progress_bar": progress_bar,
            "current_stage": {
                "number": next_idx + 1,
                "name": next_stage["name"],
                "description": next_stage["description"],
            },
            "next_actions": next_stage["next_actions"],
            "fields_to_collect": next_stage["fields"],
        }
    
    elif action == "complete":
        # Mark workflow as submitted
        if not intake_id:
            if not workflows:
                return {"error": "No active workflow"}
            intake_id = list(workflows.keys())[-1]
        
        wf = workflows.get(intake_id)
        if not wf:
            return {"error": f"Intake {intake_id} not found"}
        
        wf["status"] = "submitted"
        wf["submitted_at"] = datetime.utcnow().isoformat()
        if data:
            wf.setdefault("data", {}).update(data)
        save_workflow(workflows)
        
        return {
            "action": "submitted",
            "intake_id": intake_id,
            "message": "📤 Intake package submitted for approval!",
            "submitted_at": wf["submitted_at"],
            "status": "submitted",
            "summary": {
                "stages_completed": len(wf.get("stages_completed", [])),
                "data_fields": len(wf.get("data", {})),
            },
            "next_steps": [
                "Supervisor will review the package",
                "You'll be notified of approval status",
                "Estimated review time: 2-3 business days",
            ],
        }
    
    elif action == "reset":
        # Reset/delete a workflow
        if intake_id and intake_id in workflows:
            del workflows[intake_id]
            save_workflow(workflows)
            return {"action": "reset", "message": f"Workflow {intake_id} has been reset"}
        else:
            workflows.clear()
            save_workflow(workflows)
            return {"action": "reset", "message": "All workflows cleared"}
    
    else:
        return {
            "error": f"Unknown action: {action}",
            "valid_actions": ["start", "advance", "status", "complete", "reset"],
        }


# ── Compliance Matrix Handler ────────────────────────────────────────

def _exec_query_compliance_matrix(params: dict, tenant_id: str) -> dict:
    """Execute a compliance matrix operation (read-only, no tenant scoping)."""
    from .compliance_matrix import execute_operation

    # Support both direct dict and single-string-param wrapper
    raw = params.get("params", params)
    if isinstance(raw, str):
        raw = json.loads(raw)
    return execute_operation(raw)


# ── Admin CRUD Tool Handlers ─────────────────────────────────────────

def _exec_manage_skills(params: dict, tenant_id: str) -> dict:
    """CRUD handler for custom skills — wraps skill_store functions."""
    from app.skill_store import (
        create_skill, get_skill, update_skill, list_skills,
        delete_skill, publish_skill, submit_for_review, disable_skill,
    )
    action = params.get("action", "list")

    if action == "list":
        items = list_skills(tenant_id, status=params.get("status"))
        return {"action": "list", "count": len(items), "skills": items}

    if action == "get":
        skill_id = params.get("skill_id")
        if not skill_id:
            return {"error": "skill_id is required for get"}
        item = get_skill(tenant_id, skill_id)
        return {"action": "get", "skill": item} if item else {"error": f"Skill {skill_id} not found"}

    if action == "create":
        required = ["name", "display_name", "description", "prompt_body"]
        missing = [f for f in required if not params.get(f)]
        if missing:
            return {"error": f"Missing required fields: {', '.join(missing)}"}
        item = create_skill(
            tenant_id=tenant_id,
            owner_user_id=params.get("owner_user_id", "admin"),
            name=params["name"],
            display_name=params["display_name"],
            description=params["description"],
            prompt_body=params["prompt_body"],
            triggers=params.get("triggers"),
            tools=params.get("tools"),
            model=params.get("model"),
            visibility=params.get("visibility", "private"),
        )
        return {"action": "create", "skill": item}

    if action == "update":
        skill_id = params.get("skill_id")
        if not skill_id:
            return {"error": "skill_id is required for update"}
        updates = {k: v for k, v in params.items() if k not in ("action", "skill_id")}
        item = update_skill(tenant_id, skill_id, updates)
        return {"action": "update", "skill": item} if item else {"error": f"Skill {skill_id} not found or no updatable fields"}

    if action == "delete":
        skill_id = params.get("skill_id")
        if not skill_id:
            return {"error": "skill_id is required for delete"}
        ok = delete_skill(tenant_id, skill_id)
        return {"action": "delete", "deleted": ok, "skill_id": skill_id}

    if action == "submit":
        skill_id = params.get("skill_id")
        if not skill_id:
            return {"error": "skill_id is required for submit"}
        item = submit_for_review(tenant_id, skill_id)
        return {"action": "submit", "skill": item} if item else {"error": f"Skill {skill_id} not found or not in draft status"}

    if action == "publish":
        skill_id = params.get("skill_id")
        if not skill_id:
            return {"error": "skill_id is required for publish"}
        item = publish_skill(tenant_id, skill_id)
        return {"action": "publish", "skill": item} if item else {"error": f"Skill {skill_id} not found or not in review status"}

    if action == "disable":
        skill_id = params.get("skill_id")
        if not skill_id:
            return {"error": "skill_id is required for disable"}
        item = disable_skill(tenant_id, skill_id)
        return {"action": "disable", "skill": item} if item else {"error": f"Skill {skill_id} not found or not in active status"}

    return {"error": f"Unknown action: {action}. Valid: list, get, create, update, delete, submit, publish, disable"}


def _exec_manage_prompts(params: dict, tenant_id: str) -> dict:
    """CRUD handler for agent prompt overrides — wraps prompt_store functions."""
    from app.prompt_store import (
        put_prompt, get_prompt, delete_prompt, list_tenant_prompts, resolve_prompt,
    )
    action = params.get("action", "list")

    if action == "list":
        items = list_tenant_prompts(tenant_id)
        return {"action": "list", "count": len(items), "prompts": items}

    if action == "get":
        agent_name = params.get("agent_name")
        if not agent_name:
            return {"error": "agent_name is required for get"}
        item = get_prompt(tenant_id, agent_name)
        return {"action": "get", "prompt": item} if item else {"error": f"No prompt override for agent '{agent_name}'"}

    if action == "set":
        agent_name = params.get("agent_name")
        prompt_body = params.get("prompt_body")
        if not agent_name or not prompt_body:
            return {"error": "agent_name and prompt_body are required for set"}
        item = put_prompt(
            tenant_id=tenant_id,
            agent_name=agent_name,
            prompt_body=prompt_body,
            is_append=params.get("is_append", False),
        )
        return {"action": "set", "prompt": item}

    if action == "delete":
        agent_name = params.get("agent_name")
        if not agent_name:
            return {"error": "agent_name is required for delete"}
        ok = delete_prompt(tenant_id, agent_name)
        return {"action": "delete", "deleted": ok, "agent_name": agent_name}

    if action == "resolve":
        agent_name = params.get("agent_name")
        if not agent_name:
            return {"error": "agent_name is required for resolve"}
        body = resolve_prompt(tenant_id, agent_name)
        return {"action": "resolve", "agent_name": agent_name, "resolved_body": body}

    return {"error": f"Unknown action: {action}. Valid: list, get, set, delete, resolve"}


def _exec_manage_templates(params: dict, tenant_id: str) -> dict:
    """CRUD handler for document templates — wraps template_store functions."""
    from app.template_store import (
        put_template, get_template, delete_template, list_tenant_templates, resolve_template,
    )
    action = params.get("action", "list")

    if action == "list":
        items = list_tenant_templates(tenant_id, doc_type=params.get("doc_type"))
        return {"action": "list", "count": len(items), "templates": items}

    if action == "get":
        doc_type = params.get("doc_type")
        if not doc_type:
            return {"error": "doc_type is required for get"}
        item = get_template(tenant_id, doc_type, user_id=params.get("user_id", "shared"))
        return {"action": "get", "template": item} if item else {"error": f"No template for doc_type '{doc_type}'"}

    if action == "set":
        doc_type = params.get("doc_type")
        template_body = params.get("template_body")
        if not doc_type or not template_body:
            return {"error": "doc_type and template_body are required for set"}
        item = put_template(
            tenant_id=tenant_id,
            doc_type=doc_type,
            user_id=params.get("user_id", "shared"),
            template_body=template_body,
            display_name=params.get("display_name", ""),
        )
        return {"action": "set", "template": item}

    if action == "delete":
        doc_type = params.get("doc_type")
        if not doc_type:
            return {"error": "doc_type is required for delete"}
        ok = delete_template(tenant_id, doc_type, user_id=params.get("user_id", "shared"))
        return {"action": "delete", "deleted": ok, "doc_type": doc_type}

    if action == "resolve":
        doc_type = params.get("doc_type")
        if not doc_type:
            return {"error": "doc_type is required for resolve"}
        body = resolve_template(tenant_id, doc_type, user_id=params.get("user_id", "shared"))
        return {"action": "resolve", "doc_type": doc_type, "resolved_body": body}

    return {"error": f"Unknown action: {action}. Valid: list, get, set, delete, resolve"}


# ── Tool Dispatch ────────────────────────────────────────────────────

# Map of tool name → handler function
# Each handler takes (params, tenant_id) and optionally session_id
TOOL_DISPATCH = {
    "s3_document_ops": _exec_s3_document_ops,
    "dynamodb_intake": _exec_dynamodb_intake,
    "cloudwatch_logs": _exec_cloudwatch_logs,
    "search_far": _exec_search_far,
    "create_document": _exec_create_document,
    "get_intake_status": _exec_get_intake_status,
    "intake_workflow": _exec_intake_workflow,
    "query_compliance_matrix": _exec_query_compliance_matrix,
    # Knowledge base tools
    "knowledge_search": exec_knowledge_search,
    "knowledge_fetch": exec_knowledge_fetch,
    "manage_skills": _exec_manage_skills,
    "manage_prompts": _exec_manage_prompts,
    "manage_templates": _exec_manage_templates,
}

# Tools that need session_id for per-user scoping
TOOLS_NEEDING_SESSION = {"s3_document_ops", "create_document", "get_intake_status"}


def execute_tool(tool_name: str, tool_input: dict, session_id: str = None) -> str:
    """Execute a tool and return the result as a JSON string."""
    tenant_id = _extract_tenant_id(session_id)
    handler = TOOL_DISPATCH.get(tool_name)
    if handler:
        try:
            # Pass session_id to tools that need per-user scoping
            if tool_name in TOOLS_NEEDING_SESSION:
                result = handler(tool_input, tenant_id, session_id)
            else:
                result = handler(tool_input, tenant_id)
            return json.dumps(result, indent=2, default=str)
        except Exception as e:
            logger.error("Tool execution error (%s): %s", tool_name, e, exc_info=True)
            return json.dumps({
                "error": f"Tool execution failed: {str(e)}",
                "tool": tool_name,
                "suggestion": "Try again or use a different approach.",
            })
    else:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})


# ── Anthropic Client ─────────────────────────────────────────────────

def get_client() -> Any:
    """Create an Anthropic client.

    When USE_BEDROCK=true, returns an AnthropicBedrock client that routes
    requests through Amazon Bedrock using AWS credentials (no API key needed).
    Otherwise, uses the direct Anthropic API with ANTHROPIC_API_KEY.
    """
    try:
        import anthropic
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Anthropic SDK is required for legacy agentic_service chat path. "
            "Install 'anthropic' or use the Strands chat path."
        ) from exc

    if _USE_BEDROCK:
        return anthropic.AnthropicBedrock(aws_region=_BEDROCK_REGION)
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    return anthropic.Anthropic(api_key=api_key)


# DEPRECATED: use sdk_query() from sdk_agentic_service instead. Kept for reference only.
async def stream_chat(
    messages: List[dict],
    on_text: Any = None,
    on_tool_use: Any = None,
    on_tool_result: Any = None,
    session_id: str = None,
) -> dict:
    """
    Stream a chat response from Claude with full tool-use loop.

    Args:
        messages: Conversation history in Anthropic format
        on_text: async callback(text_delta: str) for streaming text
        on_tool_use: async callback(tool_name: str, tool_input: dict) for tool calls
        on_tool_result: async callback(tool_name: str, output: str) for tool results
        session_id: Session ID for tenant scoping

    Returns:
        dict with: text, usage, model, tools_called
    """
    import asyncio

    client = get_client()
    full_text = ""
    total_input_tokens = 0
    total_output_tokens = 0
    tools_called = []
    model_used = MODEL

    # Tool-use loop: keep going while the model wants to call tools (max 10 iterations)
    MAX_TOOL_ITERATIONS = 10
    iteration = 0
    while iteration < MAX_TOOL_ITERATIONS:
        iteration += 1
        current_text = ""
        tool_uses = []
        stop_reason = None
        text_deltas = []

        def _stream_with_deltas():
            nonlocal current_text, tool_uses, stop_reason
            nonlocal total_input_tokens, total_output_tokens, model_used

            with client.messages.stream(
                model=MODEL,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=EAGLE_TOOLS,
                messages=messages,
            ) as stream:
                for event in stream:
                    if event.type == "content_block_start":
                        if event.content_block.type == "tool_use":
                            tool_uses.append({
                                "id": event.content_block.id,
                                "name": event.content_block.name,
                                "input_json": "",
                            })
                    elif event.type == "content_block_delta":
                        if event.delta.type == "text_delta":
                            current_text += event.delta.text
                            text_deltas.append(event.delta.text)
                        elif event.delta.type == "input_json_delta":
                            if tool_uses:
                                tool_uses[-1]["input_json"] += event.delta.partial_json

                final = stream.get_final_message()
                stop_reason = final.stop_reason
                total_input_tokens += final.usage.input_tokens
                total_output_tokens += final.usage.output_tokens
                model_used = final.model

        await asyncio.to_thread(_stream_with_deltas)

        # Dispatch text deltas
        if on_text and text_deltas:
            for delta in text_deltas:
                await on_text(delta)

        full_text += current_text

        # If no tool calls, we're done
        if stop_reason != "tool_use" or not tool_uses:
            break

        # Process tool calls
        assistant_content = []
        if current_text:
            assistant_content.append({"type": "text", "text": current_text})
        for tu in tool_uses:
            try:
                tool_input = json.loads(tu["input_json"]) if tu["input_json"] else {}
            except json.JSONDecodeError:
                tool_input = {}
            assistant_content.append({
                "type": "tool_use",
                "id": tu["id"],
                "name": tu["name"],
                "input": tool_input,
            })

        messages.append({"role": "assistant", "content": assistant_content})

        # Execute tools and build tool_result message
        tool_results = []
        for tu in tool_uses:
            try:
                tool_input = json.loads(tu["input_json"]) if tu["input_json"] else {}
            except json.JSONDecodeError:
                tool_input = {}

            tools_called.append(tu["name"])
            if on_tool_use:
                await on_tool_use(tu["name"], tool_input)

            output = execute_tool(tu["name"], tool_input, session_id=session_id)

            if on_tool_result:
                await on_tool_result(tu["name"], output)

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu["id"],
                "content": output,
            })

        messages.append({"role": "user", "content": tool_results})

    return {
        "text": full_text,
        "usage": {
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
        },
        "model": model_used,
        "tools_called": tools_called,
    }
