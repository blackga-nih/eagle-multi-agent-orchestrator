"""
EAGLE - Strands-Based Agentic Service with Skill->Subagent Orchestration

Drop-in replacement for sdk_agentic_service.py. Same function signatures,
Strands Agents SDK under the hood instead of Claude Agent SDK.

Architecture:
  Supervisor (Agent + @tool subagents)
    |- oa-intake (@tool -> Agent, fresh per-call)
    |- legal-counsel (@tool -> Agent, fresh per-call)
    |- market-intelligence (@tool -> Agent, fresh per-call)
    |- tech-translator (@tool -> Agent, fresh per-call)
    |- public-interest (@tool -> Agent, fresh per-call)
    +- document-generator (@tool -> Agent, fresh per-call)

Key differences from sdk_agentic_service.py:
  - No subprocess — Strands runs in-process via boto3 converse
  - No credential bridging — boto3 handles SSO/IAM natively
  - AgentDefinition -> @tool-wrapped Agent()
  - ClaudeAgentOptions -> Agent() constructor
  - query() async generator -> agent() sync call + adapter yield
"""

import asyncio
import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from botocore.config import Config
from strands import Agent, tool
from strands.models import BedrockModel
from strands.models.model import CacheConfig

# Add server/ to path for eagle_skill_constants
_server_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)

# When imported directly (e.g. eval test runner), relative imports (.tools,
# .agentic_service, etc.) fail because there's no parent package context.
# Bootstrap the 'app' package so all `from .xxx` imports work everywhere.
if __package__ is None or __package__ == "":
    _app_dir = os.path.dirname(os.path.abspath(__file__))
    _parent = os.path.dirname(_app_dir)
    if _parent not in sys.path:
        sys.path.insert(0, _parent)
    import importlib
    if "app" not in sys.modules:
        importlib.import_module("app")
    __package__ = "app"

from eagle_skill_constants import AGENTS, SKILLS, PLUGIN_CONTENTS
from .tools.knowledge_tools import KNOWLEDGE_FETCH_TOOL, KNOWLEDGE_SEARCH_TOOL
from .tools.web_fetch import exec_web_fetch
from .tools.web_search import exec_web_search

logger = logging.getLogger("eagle.strands_agent")


# -- Langfuse OTEL exporter (lazy, one-shot) --------------------------
_langfuse_injected = False


def _ensure_langfuse_exporter():
    """Initialize Strands telemetry + Langfuse OTLP exporter (once).

    Must be called **before** the first ``Agent()`` so that the Agent's cached
    tracer references the real SDKTracerProvider (with the Langfuse exporter).
    """
    global _langfuse_injected
    if _langfuse_injected:
        return
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    if not public_key or not secret_key:
        logger.warning("[EAGLE] Langfuse credentials missing — traces will NOT be exported. "
                       "Set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY to enable.")
        return
    try:
        import base64
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from strands.telemetry import StrandsTelemetry

        st = StrandsTelemetry()
        provider = st.tracer_provider

        base = os.getenv(
            "LANGFUSE_OTEL_ENDPOINT",
            "https://us.cloud.langfuse.com/api/public/otel",
        )
        endpoint = f"{base.rstrip('/')}/v1/traces"
        auth = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()

        exporter = OTLPSpanExporter(
            endpoint=endpoint,
            headers={"Authorization": f"Basic {auth}"},
        )
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        _langfuse_injected = True
        logger.info("[EAGLE] Langfuse OTEL exporter injected → %s", endpoint)
        logging.getLogger("opentelemetry.context").setLevel(logging.CRITICAL)
    except Exception as exc:
        logger.warning("[EAGLE] Langfuse exporter injection failed: %s", exc)


async def _langfuse_set_session(
    trace_id_hex: str,
    session_id: str,
    user_id: str = "",
    tags: list | None = None,
    name: str = "",
) -> None:
    """Explicitly set sessionId (and optional tags/name) on a Langfuse trace via REST API.

    Called after sdk_query completes to ensure the OTEL trace's session ID
    is visible in Langfuse's sessionId field (OTEL attribute mapping alone
    is unreliable — this is the guaranteed path).

    Args:
        trace_id_hex: 32-char OTEL trace ID (from format_trace_id)
        session_id:   Langfuse sessionId value (e.g. "eval-t21-UC02-abc123")
        user_id:      Optional Langfuse userId
        tags:         Optional list of tags (e.g. ["eval", "test-21", "UC-02", "MVP1"])
        name:         Optional human-readable trace name override
    """
    pk = os.getenv("LANGFUSE_PUBLIC_KEY")
    sk = os.getenv("LANGFUSE_SECRET_KEY")
    host = os.getenv("LANGFUSE_HOST", "https://us.cloud.langfuse.com")
    if not pk or not sk or not trace_id_hex:
        return
    try:
        import base64
        import httpx
        auth = "Basic " + base64.b64encode(f"{pk}:{sk}".encode()).decode()
        payload: dict = {"id": trace_id_hex, "sessionId": session_id}
        if user_id:
            payload["userId"] = user_id
        if tags:
            payload["tags"] = tags
        if name:
            payload["name"] = name
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{host}/api/public/traces",
                json=payload,
                headers={"Authorization": auth},
            )
        if resp.status_code < 300:
            logger.debug(
                "[EAGLE] Langfuse trace patched: trace=%s session=%s tags=%s",
                trace_id_hex[:16], session_id, tags,
            )
        else:
            logger.debug(
                "[EAGLE] Langfuse trace patch non-2xx: %d %s",
                resp.status_code, resp.text[:100],
            )
    except Exception as exc:
        logger.debug("[EAGLE] Langfuse trace patch failed: %s", exc)


def _build_trace_attrs(
    *,
    tenant_id: str,
    user_id: str,
    tier: str,
    session_id: str = "",
    subagent: str = "",
    username: str = "",
    eval_test_id: str = "",
    eval_uc_id: str = "",
    eval_tags: list | None = None,
) -> dict:
    """Build trace_attributes dict for Langfuse/OTEL Agent() constructor.

    Tags every trace with sm-eagle source, local-vs-live environment,
    and hostname for source tracing.
    """
    import socket

    hostname = socket.gethostname()
    # EAGLE_ENV: local (dev machine), dev (ECS dev), staging, prod
    # Falls back to DEV_MODE for backward compatibility
    eagle_env = os.getenv("EAGLE_ENV", "")
    if not eagle_env:
        dev_mode = os.getenv("DEV_MODE", "false").lower() == "true"
        eagle_env = "local" if dev_mode else "live"

    # Tag eval runs: detect test-tenant/test-user from eval suite
    is_eval = tenant_id == "test-tenant" or user_id == "test-user"
    trace_env = "eval" if is_eval else eagle_env

    attrs = {
        "eagle.source": "sm-eagle",
        "eagle.environment": trace_env,
        "eagle.hostname": hostname,
        "eagle.tenant_id": tenant_id,
        "eagle.user_id": user_id,
        "eagle.tier": tier,
        "eagle.session_id": session_id or "",
        "session.id": session_id or "",
        "langfuse.session.id": session_id or "",
        "langfuse.user.id": username or user_id or "",
        "langfuse.metadata.environment": trace_env,
    }
    if is_eval:
        attrs["eagle.eval"] = "true"
    if eval_test_id:
        attrs["eagle.eval_test_id"] = eval_test_id
    if eval_uc_id:
        attrs["eagle.eval_uc_id"] = eval_uc_id
    if eval_tags:
        attrs["eagle.eval_tags"] = ",".join(eval_tags)
    if subagent:
        attrs["eagle.subagent"] = subagent

    try:
        local_ip = socket.gethostbyname(hostname)
        attrs["eagle.ip"] = local_ip
    except Exception:
        pass

    return attrs


# -- Adapter Messages ------------------------------------------------
# These match the interface expected by streaming_routes.py and main.py:
#   type(msg).__name__ == "AssistantMessage" | "ResultMessage"
#   AssistantMessage.content[].type, .text, .name, .input
#   ResultMessage.result, .usage


@dataclass
class TextBlock:
    """Adapter for text content blocks."""
    type: str = "text"
    text: str = ""


@dataclass
class ToolUseBlock:
    """Adapter for tool_use content blocks (subagent delegation info)."""
    type: str = "tool_use"
    name: str = ""
    input: dict = field(default_factory=dict)


@dataclass
class AssistantMessage:
    """Adapter matching Claude SDK AssistantMessage interface."""
    content: list = field(default_factory=list)


@dataclass
class ResultMessage:
    """Adapter matching Claude SDK ResultMessage interface."""
    result: str = ""
    usage: dict = field(default_factory=dict)


# -- Model Selection -------------------------------------------------
# If EAGLE_BEDROCK_MODEL_ID is explicitly set, use it.
# Otherwise, default to Sonnet 4.6 on the NCI account (695681773636)
# and Haiku 4.5 on any other account (personal dev, CI, etc.).

_NCI_ACCOUNT = "695681773636"
_SONNET = "us.anthropic.claude-sonnet-4-6"
_HAIKU = "us.anthropic.claude-haiku-4-5-20251001-v1:0"


def _default_model() -> str:
    env_model = os.getenv("EAGLE_BEDROCK_MODEL_ID")
    if env_model:
        return env_model
    try:
        import boto3
        account = boto3.client("sts").get_caller_identity()["Account"]
        return _SONNET if account == _NCI_ACCOUNT else _HAIKU
    except Exception:
        return _HAIKU


MODEL = _default_model()
logger.info("EAGLE model: %s", MODEL)


# -- Shared Model (module-level) -------------------------------------
# Created once at import time. Reused across all requests.
# boto3 handles SSO/IAM natively — no credential bridging needed.

_bedrock_client_config = Config(
    connect_timeout=int(os.getenv("EAGLE_BEDROCK_CONNECT_TIMEOUT", "60")),
    read_timeout=int(os.getenv("EAGLE_BEDROCK_READ_TIMEOUT", "300")),
    retries={
        "max_attempts": int(os.getenv("EAGLE_BEDROCK_MAX_ATTEMPTS", "4")),
        "mode": os.getenv("EAGLE_BEDROCK_RETRY_MODE", "adaptive"),
    },
    tcp_keepalive=True,
)

_model = BedrockModel(
    model_id=MODEL,
    region_name=os.getenv("AWS_REGION", "us-east-1"),
    boto_client_config=_bedrock_client_config,
    # Bedrock prompt caching — requires boto3>=1.37.24 (native cachePoint support).
    # cache_tools: appends cachePoint to toolConfig, caching 34 tool schemas (~17K tokens).
    # cache_config: auto-injects cachePoint at last user message for prefix caching.
    # 5-min TTL, refreshes on hit. ~2-4s TTFT reduction, ~90% input token cost savings.
    cache_tools="default",
    cache_config=CacheConfig(strategy="auto"),
)

# Tier-gated tool access (preserved from sdk_agentic_service.py)
# Note: Strands subagents don't use CLI tools like Read/Glob/Grep.
# These are kept for compatibility; in Strands, tool access is managed
# via the @tool functions registered on the Agent.
TIER_TOOLS = {
    "basic": [],
    "advanced": ["Read", "Glob", "Grep"],
    "premium": ["Read", "Glob", "Grep", "Bash"],
}

TIER_BUDGETS = {
    "basic": 0.10,
    "advanced": 0.25,
    "premium": 0.75,
}

# Fast-path document generation for explicit "generate document" requests.
# This avoids long multi-tool loops for straightforward document creation asks.
_DOC_TYPE_HINTS: list[tuple[str, list[str]]] = [
    ("sow", ["statement of work", " sow"]),
    ("igce", ["igce", "ige", "independent government estimate", "independent government cost estimate", "cost estimate"]),
    ("market_research", ["market research"]),
    ("acquisition_plan", ["acquisition plan"]),
    ("justification", ["justification", "j&a", "j and a", "sole source"]),
    ("eval_criteria", ["evaluation criteria", "eval criteria"]),
    ("security_checklist", ["security checklist"]),
    ("section_508", ["section 508", "508 compliance"]),
    ("cor_certification", ["cor certification"]),
    ("contract_type_justification", ["contract type justification"]),
]
_DOC_TYPE_LABELS: dict[str, str] = {
    "sow": "Statement of Work",
    "igce": "Independent Government Cost Estimate",
    "market_research": "Market Research",
    "acquisition_plan": "Acquisition Plan",
    "justification": "Justification & Approval",
    "eval_criteria": "Evaluation Criteria",
    "security_checklist": "Security Checklist",
    "section_508": "Section 508 Compliance",
    "cor_certification": "COR Certification",
    "contract_type_justification": "Contract Type Justification",
}
_DIRECT_DOC_VERBS = ("generate", "draft", "create", "write", "produce")
_DOC_EDIT_VERBS = ("edit", "update", "revise", "modify", "fill", "rewrite", "adjust", "amend")
_SLOW_PATH_HINTS = ("research", "far", "dfars", "policy", "compare", "analyze")
_DOC_REQUEST_BLOCKERS = (
    "what is",
    "what's",
    "how do i",
    "how to",
    "explain",
    "difference between",
)

_PROMPT_SECTION_ALIASES = {
    "project description": "project_description",
    "technical requirements": "technical_requirements",
    "scope of work": "scope_of_work",
    "deliverables": "deliverables",
    "environment tiers": "environment_tiers",
    "security": "security",
}


def _normalize_prompt(prompt: str) -> str:
    return re.sub(r"\s+", " ", prompt.strip().lower())


def _extract_user_request_from_prompt(prompt: str) -> str:
    """Extract the [USER REQUEST] block from document-viewer prompts."""
    if not prompt:
        return ""
    marker = "[USER REQUEST]"
    if marker not in prompt:
        return ""

    tail = prompt.split(marker, 1)[1]
    for stop in ("\n[", "\nInstruction:"):
        idx = tail.find(stop)
        if idx >= 0:
            tail = tail[:idx]
            break
    return tail.strip()


def _check_micropurchase_guardrail(parsed: dict) -> str | None:
    """Return a guardrail JSON string if the request is a micro-purchase (<$15K).

    Checks estimated_value from data dict, then scans title/content for dollar amounts.
    Returns None if no guardrail applies (proceed normally).
    """
    import re as _re_mp
    _mp_doc_types = {"sow", "acquisition_plan", "igce"}
    dt = str(parsed.get("doc_type", "")).strip().lower()
    if dt not in _mp_doc_types:
        return None

    data_raw = parsed.get("data") or {}
    if isinstance(data_raw, str):
        try:
            data_raw = json.loads(data_raw)
        except Exception:
            data_raw = {}

    ev_raw = str(data_raw.get("estimated_value", "")).replace(",", "").replace("$", "")
    ev_nums = _re_mp.findall(r'\d+\.?\d*', ev_raw)
    ev = float(ev_nums[0]) if ev_nums else 0.0

    if ev == 0.0:
        scan_text = f"{parsed.get('title', '')} {str(parsed.get('content', ''))[:500]}"
        dollar_matches = _re_mp.findall(r'\$\s*([\d,]+(?:\.\d+)?)', scan_text)
        amounts = [float(m.replace(",", "")) for m in dollar_matches]
        amounts_under = [a for a in amounts if 0 < a < 15000]
        if amounts_under:
            ev = min(amounts_under)

    if 0 < ev < 15000:
        return json.dumps({
            "status": "guardrail",
            "message": (
                f"Micro-purchase guardrail (FAR 13.2): ${ev:,.0f} is below the "
                f"$15,000 micro-purchase threshold. A formal {dt.upper()} is not required. "
                f"Micro-purchases use simplified procedures — purchase card or micro-purchase "
                f"order. No formal acquisition package is needed."
            ),
            "threshold": 15000,
            "value": ev,
            "word_count": 0,
        })
    return None


# ── Required-information prerequisites per doc type ─────────────────
# Each entry maps doc_type → list of (field_name, human_label) tuples.
# The guardrail checks both `data` dict fields AND scans `content` for evidence.

_DOC_PREREQUISITES: dict[str, list[tuple[str, str]]] = {
    "market_research": [
        ("requirement_description", "description of the requirement (what is being acquired)"),
        ("naics_code", "NAICS code or industry sector"),
        ("estimated_value", "estimated value or budget range"),
    ],
    "igce": [
        ("requirement_description", "description of the requirement"),
        ("labor_categories", "labor categories, product list, or line items"),
        ("period_of_performance", "period of performance"),
        ("estimated_value", "estimated value or budget range"),
    ],
    "justification": [
        ("requirement_description", "description of the requirement"),
        ("proposed_contractor", "proposed contractor or vendor name"),
        ("authority", "J&A authority (FAR 6.302 subsection)"),
    ],
    "acquisition_plan": [
        ("requirement_description", "description of the requirement"),
        ("estimated_value", "estimated value or budget range"),
        ("contract_type", "planned contract type (FFP, T&M, CR, etc.)"),
    ],
}

# Patterns that indicate unfilled template placeholders
_PLACEHOLDER_PATTERNS = [
    r"\{\{[A-Z_]+\}\}",           # {{VENDOR_NAME}}, {{PRICE_LOW}}
    r"\[TBD\]",                    # [TBD]
    r"\[Insert[^\]]*\]",           # [Insert vendor name here]
    r"\[Amount\]",                 # [Amount]
    r"\[Vendor\s*Name\]",          # [Vendor Name]
    r"\[Contractor\s*Name\]",      # [Contractor Name]
    r"\$\[",                       # $[Amount]
    r"\[PLACEHOLDER\]",            # [PLACEHOLDER]
]


def _check_document_prerequisites(parsed: dict) -> str | None:
    """Return a guardrail JSON string if required information is missing.

    Checks two things:
    1. Required structured fields in `data` for the doc type
    2. Content for placeholder patterns that indicate unfilled templates

    Returns None if all checks pass (proceed normally).
    """
    import re as _re_prereq

    dt = str(parsed.get("doc_type", "")).strip().lower()
    prereqs = _DOC_PREREQUISITES.get(dt)
    if not prereqs:
        return None  # No prerequisites defined for this doc type

    data_raw = parsed.get("data") or {}
    if isinstance(data_raw, str):
        try:
            data_raw = json.loads(data_raw)
        except Exception:
            data_raw = {}

    content = str(parsed.get("content", ""))

    # Check required fields — look in both data dict and content body
    missing = []
    for field_name, human_label in prereqs:
        # Check data dict
        val = str(data_raw.get(field_name, "")).strip()
        if val and val.lower() not in ("", "none", "n/a", "unknown", "tbd"):
            continue

        # Check if the information appears somewhere in the content
        # (agent may have embedded it in prose rather than structured data)
        found_in_content = False

        if field_name == "estimated_value":
            # Look for dollar amounts in content
            if _re_prereq.search(r'\$[\d,]+', content):
                found_in_content = True
        elif field_name == "naics_code":
            # Look for NAICS pattern (5-6 digits)
            if _re_prereq.search(r'\b\d{5,6}\b', content):
                found_in_content = True
        elif field_name == "period_of_performance":
            # Look for date ranges or duration mentions
            if _re_prereq.search(r'(?:month|year|day|week|PoP|period of performance)', content, _re_prereq.IGNORECASE):
                found_in_content = True
        elif field_name == "labor_categories":
            # Look for labor-related terms
            if _re_prereq.search(r'(?:labor|categor|position|role|staff|engineer|analyst|developer|specialist)', content, _re_prereq.IGNORECASE):
                found_in_content = True
        elif field_name == "proposed_contractor":
            # Must have a specific company name — hard to validate generically
            # Accept if content is substantial (>200 chars suggests real data)
            if len(content) > 200:
                found_in_content = True
        elif field_name == "requirement_description":
            # Accept if content has meaningful length
            if len(content) > 100:
                found_in_content = True
        elif field_name == "authority":
            if _re_prereq.search(r'(?:FAR\s*6\.302|sole.source|limited.source|unusual.urgent)', content, _re_prereq.IGNORECASE):
                found_in_content = True
        elif field_name == "contract_type":
            if _re_prereq.search(r'(?:firm.fixed|FFP|time.and.material|T&M|cost.reimburs|IDIQ|BPA)', content, _re_prereq.IGNORECASE):
                found_in_content = True

        if not found_in_content:
            missing.append(human_label)

    # Check content for placeholder patterns
    placeholders_found = []
    for pattern in _PLACEHOLDER_PATTERNS:
        matches = _re_prereq.findall(pattern, content)
        if matches:
            placeholders_found.extend(matches[:3])  # Cap at 3 examples per pattern

    # Build guardrail response if issues found
    issues = []
    if missing:
        issues.append(
            f"Missing required information: {', '.join(missing)}. "
            "Ask the user to provide this information before generating the document."
        )
    if placeholders_found:
        examples = ", ".join(dict.fromkeys(placeholders_found[:5]))  # Dedupe, cap at 5
        issues.append(
            f"Content contains placeholder markers ({examples}). "
            "Replace all placeholders with real data from research or conversation."
        )

    if not issues:
        return None

    doc_label = dt.replace("_", " ").title()
    return json.dumps({
        "status": "guardrail",
        "guardrail": "document_prerequisites",
        "message": (
            f"Cannot generate {doc_label} — prerequisites not met.\n\n"
            + "\n".join(f"• {issue}" for issue in issues)
            + "\n\nCollect the missing information from the user, then perform "
            "web research (web_search + web_fetch) before calling create_document."
        ),
        "missing_fields": missing,
        "placeholder_count": len(placeholders_found),
        "word_count": 0,
    })


def _extract_document_context_from_prompt(prompt: str) -> dict[str, str]:
    """Extract document viewer context blocks from wrapped prompts."""
    if not prompt:
        return {}

    out: dict[str, str] = {}
    lines = prompt.splitlines()
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        if line.lower().startswith("title:") and "title" not in out:
            out["title"] = line.split(":", 1)[1].strip()
            continue
        if line.lower().startswith("type:") and "document_type" not in out:
            doc_type = line.split(":", 1)[1].strip().lower().replace(" ", "_")
            if doc_type:
                out["document_type"] = doc_type

    excerpt_start = prompt.find("Current Content Excerpt:")
    if excerpt_start != -1:
        excerpt_body = prompt[excerpt_start + len("Current Content Excerpt:") :]
        end_markers = ["\n[ORIGIN SESSION CONTEXT]", "\n[USER REQUEST]"]
        excerpt_end = len(excerpt_body)
        for marker in end_markers:
            marker_index = excerpt_body.find(marker)
            if marker_index != -1:
                excerpt_end = min(excerpt_end, marker_index)
        excerpt = excerpt_body[:excerpt_end].strip()
        if excerpt:
            out["current_content"] = excerpt

    user_request = _extract_user_request_from_prompt(prompt)
    if user_request:
        out["user_request"] = user_request

    return out


def _infer_doc_type_from_prompt(prompt: str) -> str | None:
    lowered = f" {_normalize_prompt(prompt)} "
    for doc_type, hints in _DOC_TYPE_HINTS:
        if any(hint in lowered for hint in hints):
            return doc_type
    return None


def _is_document_generation_request(prompt: str) -> tuple[bool, str | None]:
    lowered = _normalize_prompt(prompt)
    doc_type = _infer_doc_type_from_prompt(prompt)
    if not doc_type:
        return False, None
    if any(lowered.startswith(blocker) for blocker in _DOC_REQUEST_BLOCKERS):
        return False, None
    if any(v in lowered for v in _DIRECT_DOC_VERBS):
        return True, doc_type

    # Document-viewer prompts include explicit wrappers; treat edit verbs in
    # [USER REQUEST] as document generation intent.
    if "[document context]" in lowered and "[user request]" in lowered:
        user_req = _extract_user_request_from_prompt(prompt).lower()
        if any(v in user_req for v in _DIRECT_DOC_VERBS) or any(v in user_req for v in _DOC_EDIT_VERBS):
            return True, doc_type

    phrase = _DOC_TYPE_LABELS.get(doc_type, doc_type.replace("_", " ")).lower()
    if lowered.startswith(phrase):
        return True, doc_type
    if re.search(rf"\b(need|want|please)\b.*\b{re.escape(phrase)}\b", lowered):
        return True, doc_type

    return False, None


def _should_use_fast_document_path(prompt: str) -> tuple[bool, str | None]:
    should_generate, doc_type = _is_document_generation_request(prompt)
    if not should_generate or not doc_type:
        return False, None

    lowered = _normalize_prompt(prompt)
    if "[document context]" in lowered:
        return False, None
    if any(h in lowered for h in _SLOW_PATH_HINTS):
        return False, None
    return True, doc_type


def _extract_prompt_sections(prompt: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None

    for raw_line in (prompt or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        heading = line.rstrip(":").strip().lower()
        if heading in _PROMPT_SECTION_ALIASES:
            current = _PROMPT_SECTION_ALIASES[heading]
            sections.setdefault(current, [])
            continue

        if line.startswith("- ") or line.startswith("* "):
            item = line[2:].strip().strip('"')
            if not item:
                continue
            bucket = current or "general"
            sections.setdefault(bucket, []).append(item)

    return sections


def _extract_context_data_from_prompt(prompt: str, doc_type: str) -> dict[str, Any]:
    """Derive create_document data fields from the current user prompt."""
    if not prompt:
        return {}

    data: dict[str, Any] = {}
    doc_ctx = _extract_document_context_from_prompt(prompt)
    if doc_ctx.get("current_content"):
        data["current_content"] = doc_ctx["current_content"]
    if doc_ctx.get("user_request"):
        data["edit_request"] = doc_ctx["user_request"]

    sections = _extract_prompt_sections(prompt)

    project_description = " ".join(sections.get("project_description", [])).strip()
    if project_description:
        data["description"] = project_description[:500]
        data["requirement"] = project_description[:500]
    else:
        user_req = _extract_user_request_from_prompt(prompt)
        if user_req:
            data["description"] = user_req[:500]
            data["requirement"] = user_req[:500]

    scope_items = sections.get("scope_of_work", [])
    tech_items = sections.get("technical_requirements", [])
    if doc_type == "sow":
        tasks = (scope_items + tech_items)[:20]
        if tasks:
            data["tasks"] = tasks
        if sections.get("deliverables"):
            data["deliverables"] = sections["deliverables"][:15]
        if sections.get("security"):
            data["security_requirements"] = "; ".join(sections["security"])[:600]
        if sections.get("environment_tiers"):
            data["place_of_performance"] = "; ".join(sections["environment_tiers"])[:300]
        if scope_items:
            data["scope"] = " ".join(scope_items)[:500]

    # Common budget/timeline extraction (best effort)
    m_money = re.search(r"\$[0-9][0-9,]*(?:\.[0-9]+)?", prompt)
    if m_money:
        money = m_money.group(0)
        data.setdefault("estimated_cost", money)
        data.setdefault("estimated_value", money)
        data.setdefault("total_estimate", money)

    m_period = re.search(r"\b\d+\s*(?:month|months|year|years)\b(?:[^.,;\n]{0,40})", prompt, flags=re.IGNORECASE)
    if m_period:
        period = m_period.group(0).strip()
        data.setdefault("period_of_performance", period)
        data.setdefault("timeline", period)

    return data


def _fast_path_title(prompt: str, doc_type: str) -> str:
    """Generate a descriptive title from the user prompt and doc type.

    Tries to extract the program/acquisition context that follows 'for', 'regarding',
    or 'about' in the prompt. Falls back to the generic doc-type label.
    """
    base = _DOC_TYPE_LABELS.get(doc_type, doc_type.replace("_", " ").title())
    if not prompt:
        return base

    lowered = prompt.lower()
    # Look for "for <context>" / "regarding <context>" / "about <context>"
    for marker in ("for ", "regarding ", "about "):
        idx = lowered.find(marker)
        if idx == -1:
            continue
        tail = prompt[idx + len(marker):].strip()
        # Take up to the first sentence end or 60 chars
        for stop in (".", "\n", "?", "!", ";"):
            stop_idx = tail.find(stop)
            if 0 < stop_idx < 80:
                tail = tail[:stop_idx]
                break
        tail = tail.strip().rstrip(",").strip()
        if tail and len(tail) > 3:
            return f"{base} - {tail[:80]}"

    return base


def _build_scoped_session_id(
    tenant_id: str,
    user_id: str,
    session_id: str | None,
) -> str:
    if session_id and "#" in session_id:
        return session_id
    return f"{tenant_id}#advanced#{user_id}#{session_id or ''}"


async def _maybe_fast_path_document_generation(
    prompt: str,
    tenant_id: str,
    user_id: str,
    session_id: str | None,
    package_context: Any = None,
) -> dict | None:
    should_fast_path, doc_type = _should_use_fast_document_path(prompt)
    if not should_fast_path or not doc_type:
        return None

    # -- Micro-purchase guardrail (FAR 13.2) --
    if doc_type in ("sow", "acquisition_plan", "igce"):
        import re as _re_mp_fp
        _dollar_matches = _re_mp_fp.findall(r'\$\s*([\d,]+(?:\.\d+)?)', prompt)
        _amounts = [float(m.replace(",", "")) for m in _dollar_matches]
        _amounts_under = [a for a in _amounts if 0 < a < 15000]
        if _amounts_under:
            _ev = min(_amounts_under)
            return {
                "doc_type": doc_type,
                "result": {
                    "status": "guardrail",
                    "message": (
                        f"Micro-purchase guardrail (FAR 13.2): ${_ev:,.0f} is below the "
                        f"$15,000 micro-purchase threshold. A formal {doc_type.upper()} is "
                        f"not required. Micro-purchases use simplified procedures — purchase "
                        f"card or micro-purchase order. No formal acquisition package is needed."
                    ),
                    "word_count": 0,
                },
                "guardrail": True,
            }

    from .agentic_service import _exec_create_document

    doc_ctx = _extract_document_context_from_prompt(prompt)
    params: dict[str, Any] = {
        "doc_type": doc_type,
        "title": doc_ctx.get("title") or _fast_path_title(prompt, doc_type),
    }
    contextual_data = _extract_context_data_from_prompt(prompt, doc_type)
    if contextual_data:
        params["data"] = contextual_data
    if (
        package_context is not None
        and getattr(package_context, "is_package_mode", False)
        and getattr(package_context, "package_id", None)
    ):
        params["package_id"] = package_context.package_id

    scoped_session_id = _build_scoped_session_id(tenant_id, user_id, session_id)
    result = await asyncio.to_thread(
        _exec_create_document,
        params,
        tenant_id,
        scoped_session_id,
    )
    return {
        "doc_type": doc_type,
        "result": result,
    }


async def _ensure_create_document_for_direct_request(
    prompt: str,
    tenant_id: str,
    user_id: str,
    session_id: str | None,
    package_context: Any,
    tools_called: list[str],
) -> dict | None:
    """Force a create_document call for direct doc requests that missed the tool.

    This reconciles cases where the model produced inline draft content without
    invoking create_document, which breaks document-card/editing UX.
    """
    should_generate, doc_type = _is_document_generation_request(prompt)
    if not should_generate or not doc_type or "create_document" in tools_called:
        return None

    from .agentic_service import _exec_create_document

    doc_ctx = _extract_document_context_from_prompt(prompt)
    params: dict[str, Any] = {
        "doc_type": doc_type,
        "title": doc_ctx.get("title") or _fast_path_title(prompt, doc_type),
    }
    contextual_data = _extract_context_data_from_prompt(prompt, doc_type)
    if contextual_data:
        params["data"] = contextual_data
    if (
        package_context is not None
        and getattr(package_context, "is_package_mode", False)
        and getattr(package_context, "package_id", None)
    ):
        params["package_id"] = package_context.package_id

    scoped_session_id = _build_scoped_session_id(tenant_id, user_id, session_id)
    result = await asyncio.to_thread(
        _exec_create_document,
        params,
        tenant_id,
        scoped_session_id,
    )
    if isinstance(result, dict) and result.get("error"):
        logger.warning(
            "Forced create_document failed for prompt='%s': %s",
            prompt[:160],
            result.get("error"),
        )
        return None

    return {
        "doc_type": doc_type,
        "result": result,
    }

# -- Tool Schemas (for health/status endpoints) -------------------------
# These are the Anthropic tool_use format schemas used by main.py and
# streaming_routes.py to report available tools. They do NOT drive the
# Strands agent (which uses @tool functions).
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
            "application logs, debug issues, or audit user activity. "
            "Pass user_id to scope results to a specific user."
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
                "user_id": {
                    "type": "string",
                    "description": "Filter logs to this specific user ID",
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
    # Progressive disclosure tools
    {
        "name": "list_skills",
        "description": (
            "List available skills, agents, and data files with descriptions and triggers. "
            "Use to discover capabilities before diving deeper."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["skills", "agents", "data", ""],
                    "description": "Filter: 'skills', 'agents', 'data', or '' for all",
                },
            },
        },
    },
    {
        "name": "load_skill",
        "description": (
            "Load full skill or agent instructions by name. Returns the complete "
            "SKILL.md or agent.md content for following workflows without spawning a subagent."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Skill or agent name (e.g. 'oa-intake', 'compliance')",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "load_data",
        "description": (
            "Load reference data from the plugin data directory. Access thresholds, "
            "contract types, document requirements, approval chains, contract vehicles."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Data file name (e.g. 'matrix', 'thresholds', 'contract-vehicles')",
                },
                "section": {
                    "type": "string",
                    "description": "Optional section key (e.g. 'thresholds', 'doc_rules', 'approval_chains')",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "search_far",
        "description": (
            "Search the Federal Acquisition Regulation (FAR) and Defense Federal "
            "Acquisition Regulation Supplement (DFARS) for relevant clauses, "
            "requirements, and guidance. Returns part numbers, sections, titles, "
            "summaries, and s3_keys for full document retrieval. After receiving "
            "results, call knowledge_fetch on s3_keys to read the full document."
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
    KNOWLEDGE_SEARCH_TOOL,
    KNOWLEDGE_FETCH_TOOL,
    {
        "name": "web_search",
        "description": (
            "Search the web for real-time information using Amazon Nova Web Grounding. "
            "Use for current market data, vendor info, pricing, GSA schedule rates, "
            "policy updates, regulatory changes, or any topic needing up-to-date info "
            "beyond the knowledge base. Returns an answer with source citations."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language search query",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "web_fetch",
        "description": (
            "Fetch a web page and return its full content as clean markdown. "
            "Use AFTER web_search to read the actual content of source URLs. "
            "Returns the page title and markdown-formatted body text (max 15K chars)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to fetch (must be http or https)",
                },
            },
            "required": ["url"],
        },
    },
    {
        "name": "create_document",
        "description": (
            "Generate acquisition documents including SOW, IGCE, Market Research, "
            "J&A, Acquisition Plan, Evaluation Criteria, Security Checklist, "
            "Section 508 Statement, COR Certification, Contract Type "
            "Justification, Statement of Need, Buy American DF, Subcontracting Plan, "
            "and Conference Request. Documents are saved to S3. "
            "Each doc_type has a defined section structure — fill EVERY section."
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
                        "contract_type_justification",
                        "son_products", "son_services", "buy_american",
                        "subk_plan", "conference_request"
                    ],
                    "description": "Type of acquisition document to generate",
                },
                "title": {
                    "type": "string",
                    "description": "Descriptive document title including the program or acquisition name (e.g. 'SOW - Cloud Computing Services for NCI Research Portal' or 'IGCE - IT Support Services FY2026'). Never use a generic type label alone.",
                },
                "content": {
                    "type": "string",
                    "description": (
                        "Full document content as markdown. Write complete, "
                        "section-by-section content using the conversation context "
                        "before calling this tool. This becomes the saved document body. "
                        "Cover ALL sections defined in the template schema."
                    ),
                },
                "data": {
                    "type": "object",
                    "description": "Document-specific fields (description, estimated_value, period_of_performance, competition, contract_type, etc.) for template population.",
                },
            },
            "required": ["doc_type", "title"],
        },
    },
    {
        "name": "edit_docx_document",
        "description": (
            "Apply targeted edits to an existing DOCX document in S3 using "
            "python-docx. Use this to preserve Word formatting while replacing "
            "specific existing text in the document."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "document_key": {
                    "type": "string",
                    "description": "Full S3 key for the target .docx document",
                },
                "edits": {
                    "type": "array",
                    "description": "Exact text replacements to apply",
                    "items": {
                        "type": "object",
                        "properties": {
                            "search_text": {
                                "type": "string",
                                "description": "Exact current text to find in the DOCX preview",
                            },
                            "replacement_text": {
                                "type": "string",
                                "description": "Replacement text to apply while preserving formatting",
                            },
                        },
                        "required": ["search_text", "replacement_text"],
                    },
                },
                "checkbox_edits": {
                    "type": "array",
                    "description": "Optional checkbox toggles using visible checkbox label text from the DOCX preview",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label_text": {
                                "type": "string",
                                "description": "Visible checkbox label text from the preview",
                            },
                            "checked": {
                                "type": "boolean",
                                "description": "Whether the checkbox should be checked",
                            },
                        },
                        "required": ["label_text", "checked"],
                    },
                },
            },
            "required": ["document_key"],
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
        "name": "manage_package",
        "description": (
            "Create, read, update, or list acquisition packages. Packages track "
            "the full acquisition lifecycle — required documents, completed documents, "
            "checklist progress, and status (intake → drafting → review → approved). "
            "Call with operation='create' after gathering intake info (title, estimated "
            "value, requirement type) to activate the checklist panel."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["create", "get", "update", "list", "checklist"],
                    "description": "Package operation to perform",
                },
                "package_id": {
                    "type": "string",
                    "description": "Package ID for get/update/checklist operations (e.g. PKG-2026-0001)",
                },
                "title": {
                    "type": "string",
                    "description": "Package title (for create)",
                },
                "requirement_type": {
                    "type": "string",
                    "description": "Requirement type: services, supplies, IT, construction, R&D (for create)",
                },
                "estimated_value": {
                    "type": "number",
                    "description": "Estimated contract dollar value (for create/update)",
                },
                "acquisition_method": {
                    "type": "string",
                    "description": "Acquisition method code: sap, sealed_bidding, negotiated, sole_source, 8a, micro_purchase (for create/update)",
                },
                "contract_type": {
                    "type": "string",
                    "description": "Contract type code: ffp, fpif, cpff, cpif, cpaf, cr, tm, idiq, bpa (for create/update)",
                },
                "contract_vehicle": {
                    "type": "string",
                    "description": "Contract vehicle if applicable: NITAAC, GSA, existing BPA (for create/update)",
                },
                "notes": {
                    "type": "string",
                    "description": "Additional notes or context (for create/update)",
                },
                "updates": {
                    "type": "object",
                    "description": "Fields to update (for update operation)",
                },
                "status": {
                    "type": "string",
                    "description": "Filter by status for list operation",
                },
            },
            "required": ["operation"],
        },
    },
]

# Max prompt size per subagent to avoid context overflow
MAX_SKILL_PROMPT_CHARS = 4000


# -- Skill -> @tool Registry (built from plugin metadata) ------------

_PLUGIN_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "eagle-plugin"
)
_PLUGIN_JSON_PATH = os.path.join(_PLUGIN_DIR, "plugin.json")


def _load_plugin_config() -> dict:
    """Load plugin config, merging DynamoDB manifest with bundled plugin.json.

    The DynamoDB PLUGIN#manifest only stores version/agent_count/skill_count —
    it does NOT include the 'data' index needed by load_data(). Always load
    the bundled plugin.json as the base, then overlay any DynamoDB manifest
    fields on top.
    """
    # Always start from the bundled plugin.json (has 'data', 'capabilities', etc.)
    config: dict = {}
    try:
        with open(_PLUGIN_JSON_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    # Overlay DynamoDB manifest fields (version, agent_count, skill_count)
    try:
        from .plugin_store import get_plugin_manifest
        manifest = get_plugin_manifest()
        if manifest:
            config.update(manifest)
    except Exception:
        pass

    return config


def _build_registry() -> dict:
    """Build SKILL_AGENT_REGISTRY dynamically from AGENTS + SKILLS metadata.

    Uses plugin.json to determine which agents/skills are wired as subagents.
    The supervisor agent is excluded (it's the orchestrator, not a subagent).
    """
    config = _load_plugin_config()
    active_agents = set(config.get("agents", []))
    active_skills = set(config.get("skills", []))

    registry = {}

    for name, entry in AGENTS.items():
        if name == config.get("agent", "supervisor"):
            continue
        if active_agents and name not in active_agents:
            continue
        registry[name] = {
            "description": entry["description"],
            "skill_key": name,
            "tools": entry["tools"] if entry["tools"] else [],
            "model": entry["model"],
        }

    for name, entry in SKILLS.items():
        if active_skills and name not in active_skills:
            continue
        registry[name] = {
            "description": entry["description"],
            "skill_key": name,
            "tools": entry["tools"] if entry["tools"] else [],
            "model": entry["model"],
        }

    return registry


SKILL_AGENT_REGISTRY = _build_registry()


def _truncate_skill(content: str, max_chars: int = MAX_SKILL_PROMPT_CHARS) -> str:
    """Truncate skill content to fit within subagent context budget."""
    if len(content) <= max_chars:
        return content
    return content[:max_chars] + "\n\n[... truncated for context budget]"


# -- @tool Factory ---------------------------------------------------

def _build_subagent_kb_tools(
    tenant_id: str,
    session_id: str,
    result_queue: asyncio.Queue | None = None,
    loop: asyncio.AbstractEventLoop | None = None,
) -> list:
    """Build knowledge-base tools that subagents can use to ground analysis.

    Gives subagents access to knowledge_search, knowledge_fetch, and search_far
    so they can retrieve actual documents instead of relying solely on
    parametric knowledge.

    Uses proper named parameters (not ``params: str``) so the Strands-generated
    schema matches what Bedrock models naturally send.
    """
    from .tools.knowledge_tools import exec_knowledge_search, exec_knowledge_fetch
    from .agentic_service import _exec_search_far

    def _emit_input(name: str, tool_input: dict) -> None:
        """Push tool input so the stream can update the card with real params."""
        if result_queue and loop:
            loop.call_soon_threadsafe(
                result_queue.put_nowait,
                {"type": "tool_input", "name": name, "input": tool_input},
            )

    @tool(name="knowledge_search")
    def kb_search(
        query: str = "",
        topic: str = "",
        document_type: str = "",
        agent: str = "",
        authority_level: str = "",
        keywords: list[str] | None = None,
        limit: int = 10,
    ) -> str:
        """Search the acquisition knowledge base for relevant documents, templates, and guidance. Use 'query' for specific identifiers like case numbers or citations. Use 'topic' for broad subject searches.

        Args:
            query: Search query — case numbers, citations, identifiers, or keywords
            topic: Broad topic filter (e.g. "competition", "small business")
            document_type: Filter by document type
            agent: Filter by agent/specialist
            authority_level: Filter by authority level
            keywords: List of keyword filters
            limit: Maximum results to return (default 10)
        """
        params = {k: v for k, v in {
            "query": query, "topic": topic, "document_type": document_type,
            "agent": agent, "authority_level": authority_level,
            "keywords": keywords, "limit": limit,
        }.items() if v}
        _emit_input("knowledge_search", params)
        result = exec_knowledge_search(params, tenant_id, session_id)
        return json.dumps(result, indent=2, default=str)

    @tool(name="knowledge_fetch")
    def kb_fetch(s3_key: str) -> str:
        """Fetch full document content from the knowledge base by s3_key. REQUIRES an s3_key from a prior knowledge_search or search_far result.

        Args:
            s3_key: S3 key path from a knowledge_search or search_far result
        """
        _emit_input("knowledge_fetch", {"s3_key": s3_key})
        result = exec_knowledge_fetch({"s3_key": s3_key}, tenant_id, session_id)
        return json.dumps(result, indent=2, default=str)

    @tool(name="search_far")
    def far_search(query: str, parts: list[str] | None = None) -> str:
        """Search FAR/DFARS for clauses, requirements, and guidance. Returns s3_keys for full documents — ALWAYS call knowledge_fetch on returned s3_keys before responding.

        Args:
            query: Search query — topic, clause number, or keyword
            parts: Optional list of FAR part numbers to filter (e.g. ["6", "16"])
        """
        _emit_input("search_far", {"query": query, "parts": parts})
        result = _exec_search_far({"query": query, "parts": parts}, tenant_id)
        return json.dumps(result, indent=2, default=str)

    @tool(name="web_search")
    def web_search(query: str) -> str:
        """Search the web for real-time information. Use for current market data, vendor info, pricing, policy updates, or any topic needing up-to-date info beyond the knowledge base.

        IMPORTANT: After EVERY web_search call, you MUST call web_fetch on the top 5 source URLs returned. Search snippets are incomplete — they miss pricing tiers, licensing terms, compliance details, and contract vehicle numbers. Never cite a source you have not web_fetched.

        Args:
            query: Natural language search query
        """
        _emit_input("web_search", {"query": query})
        result = exec_web_search(query)
        return json.dumps(result, indent=2, default=str)

    @tool(name="web_fetch")
    def web_fetch(url: str) -> str:
        """Fetch a web page and return its content as clean markdown. MUST be called on top 5 source URLs after EVERY web_search. Search snippets alone are unreliable — always read the full page.

        Args:
            url: The URL to fetch (must be http or https)
        """
        _emit_input("web_fetch", {"url": url})
        result = exec_web_fetch(url)
        return json.dumps(result, indent=2, default=str)

    return [kb_search, kb_fetch, far_search, web_search, web_fetch]


def _build_subagent_doc_tools(
    tenant_id: str,
    user_id: str,
    session_id: str,
    result_queue: asyncio.Queue | None = None,
    loop: asyncio.AbstractEventLoop | None = None,
) -> list:
    """Build document tools (create_document, edit_docx_document) for subagents.

    Gives subagents like market-intelligence the ability to create and modify
    documents directly within their own context window, rather than relying
    on the supervisor to do it after the subagent returns.

    Simpler than the supervisor's versions — no prompt-context enrichment
    since the subagent *is* the author and has full context.
    Documents are always scoped to the user, never to tenant or system.
    """
    from .agentic_service import TOOL_DISPATCH

    scoped_session_id = session_id
    if not scoped_session_id or "#" not in scoped_session_id:
        scoped_session_id = f"{tenant_id}#advanced#{user_id}#{session_id or ''}"

    def _emit(name: str, result) -> None:
        if not result_queue or not loop:
            return
        emit_result = result
        if name != "create_document" and isinstance(result, dict):
            text_val = result.get("content") or result.get("text") or result.get("result")
            if isinstance(text_val, str) and len(text_val) > 2000:
                emit_result = {**result}
                key = "content" if "content" in result else "text" if "text" in result else "result"
                emit_result[key] = text_val[:2000] + "..."
        loop.call_soon_threadsafe(
            result_queue.put_nowait,
            {"type": "tool_result", "name": name, "result": emit_result},
        )

    @tool(name="create_document")
    def create_document_tool(
        doc_type: str,
        title: str = "",
        content: str = "",
        data: dict | None = None,
        package_id: str = "",
        output_format: str = "",
        update_existing_key: str = "",
        template_id: str = "",
    ) -> str:
        """Generate acquisition documents (SOW, IGCE, Market Research, J&A, Acquisition Plan, Eval Criteria, Security Checklist, Section 508, COR Certification, Contract Type Justification). Documents are saved to S3.

        CRITICAL: Always provide the `content` parameter with the FULL document markdown you have written using conversation context, intake data, and web research results. Do NOT call this tool with empty content — it produces placeholder-only stubs. YOU are the document author; this tool saves your work.

        Args:
            doc_type: Document type (sow, igce, market_research, justification, acquisition_plan, eval_criteria, security_checklist, section_508, cor_certification, contract_type_justification)
            title: Descriptive document title that includes the program or acquisition name
            content: REQUIRED — Full document content in markdown with all sections filled using real data
            data: Supplementary structured metadata (estimated_value, period_of_performance, naics_code, etc.)
            package_id: Acquisition package ID to associate document with
            output_format: Output format override
            update_existing_key: S3 key of existing document to update/revise
            template_id: Template ID to use for generation
        """
        parsed = {
            "doc_type": doc_type, "title": title, "content": content,
            "data": data, "package_id": package_id,
            "output_format": output_format, "update_existing_key": update_existing_key,
            "template_id": template_id,
        }
        try:
            # -- Micro-purchase guardrail (FAR 13.2) --
            _mp_block = _check_micropurchase_guardrail(parsed)
            if _mp_block:
                return _mp_block

            # -- Document prerequisites guardrail --
            _prereq_block = _check_document_prerequisites(parsed)
            if _prereq_block:
                return _prereq_block

            result = TOOL_DISPATCH["create_document"](parsed, tenant_id, scoped_session_id)
            _emit("create_document", result)
            return json.dumps(result, indent=2, default=str)
        except Exception as exc:
            logger.error("Subagent create_document failed: %s", exc, exc_info=True)
            return json.dumps({"error": str(exc), "tool": "create_document"})

    @tool(name="edit_docx_document")
    def edit_docx_document_tool(
        document_key: str,
        edits: list | None = None,
        checkbox_edits: list | None = None,
    ) -> str:
        """Apply targeted edits to an existing DOCX document. Use for text replacements or checkbox toggles.

        Args:
            document_key: S3 key of the DOCX document to edit
            edits: List of edit objects, each with 'search_text' and 'replacement_text'
            checkbox_edits: List of checkbox edit objects, each with 'label_text' and 'checked' (bool)
        """
        parsed = {"document_key": document_key, "edits": edits or [], "checkbox_edits": checkbox_edits or []}
        try:
            result = TOOL_DISPATCH["edit_docx_document"](parsed, tenant_id, scoped_session_id)
            _emit("edit_docx_document", result)
            return json.dumps(result, indent=2, default=str)
        except Exception as exc:
            logger.error("Subagent edit_docx_document failed: %s", exc, exc_info=True)
            return json.dumps({"error": str(exc), "tool": "edit_docx_document"})

    return [create_document_tool, edit_docx_document_tool]


class _SubagentEventForwarder:
    """Strands CallbackHandler that forwards subagent internal events to the parent stream.

    Pushes tool_use, agent_status, and reasoning events from a subagent's
    execution into the parent result_queue so they appear in the SSE stream
    in real-time (instead of the frontend showing only loading dots).
    """

    def __init__(self, parent_name: str, rq: asyncio.Queue, loop: asyncio.AbstractEventLoop):
        self.parent_name = parent_name
        self.rq = rq
        self.loop = loop
        self._seen_tool_ids: set[str] = set()

    def _push(self, event: dict) -> None:
        self.loop.call_soon_threadsafe(self.rq.put_nowait, event)

    def __call__(self, **kwargs: Any) -> None:
        # --- Tool use start (from contentBlockStart) ---
        event = kwargs.get("event", {})
        if isinstance(event, dict):
            tool_use = (
                event.get("contentBlockStart", {})
                .get("start", {})
                .get("toolUse")
            )
            if tool_use:
                tid = tool_use.get("toolUseId", "")
                tname = tool_use.get("name", "")
                if tid and tid not in self._seen_tool_ids:
                    self._seen_tool_ids.add(tid)
                    self._push({
                        "type": "tool_use",
                        "name": tname,
                        "input": {},
                        "tool_use_id": tid,
                    })
                    display_parent = self.parent_name.replace("_", " ").title()
                    from .telemetry.status_messages import get_tool_status_message
                    status = get_tool_status_message(tname, {})
                    self._push({
                        "type": "agent_status",
                        "status": f"{display_parent}: {status}",
                        "detail": tname,
                    })

        # --- Reasoning / extended thinking ---
        reasoning = kwargs.get("reasoningText")
        if reasoning and isinstance(reasoning, str):
            self._push({"type": "reasoning", "data": reasoning})


def _make_subagent_tool(
    skill_name: str,
    description: str,
    prompt_body: str,
    result_queue: asyncio.Queue | None = None,
    loop: asyncio.AbstractEventLoop | None = None,
    tenant_id: str = "",
    user_id: str = "",
    tier: str = "",
    session_id: str = "",
    extra_tools: list | None = None,
):
    """Create a @tool-wrapped subagent from skill registry entry.

    Each invocation constructs a fresh Agent with the resolved prompt.
    The shared _model is reused (no per-request boto3 overhead).
    Subagents receive knowledge_search, knowledge_fetch, and search_far
    tools so they can ground analysis in actual documents.

    Args:
        extra_tools: Additional tools to give this subagent beyond the
            standard KB tools (e.g. create_document for market-intelligence).
    """
    safe_name = skill_name.replace("-", "_")

    @tool(name=safe_name)
    def subagent_tool(query: str) -> str:
        """Placeholder docstring replaced below."""
        # Push real input so frontend can update the tool card
        if result_queue and loop:
            loop.call_soon_threadsafe(
                result_queue.put_nowait,
                {"type": "tool_input", "name": safe_name, "input": {"query": query}},
            )
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S UTC")
        subagent_context = (
            f"Tenant: {tenant_id} | User: {user_id} | Tier: {tier} | Current datetime: {now_utc}\n"
            f"You are the {skill_name} specialist.\n\n"
        )
        _ensure_langfuse_exporter()

        # Give subagents KB tools so they can retrieve actual documents
        kb_tools = _build_subagent_kb_tools(tenant_id, session_id, result_queue, loop)
        all_tools = kb_tools + (extra_tools or [])

        agent = Agent(
            model=_model,
            system_prompt=subagent_context + prompt_body,
            tools=all_tools,
            callback_handler=(
                _SubagentEventForwarder(safe_name, result_queue, loop)
                if result_queue and loop else None
            ),
            trace_attributes=_build_trace_attrs(
                tenant_id=tenant_id,
                user_id=user_id,
                tier=tier,
                session_id=session_id,
                subagent=safe_name,
            ),
        )
        raw = str(agent(query))

        # Emit tool_result so the frontend can show the specialist's report
        if result_queue and loop:
            truncated = raw[:3000] + "..." if len(raw) > 3000 else raw
            loop.call_soon_threadsafe(
                result_queue.put_nowait,
                {"type": "tool_result", "name": safe_name, "result": {"report": truncated}},
            )

        return raw

    # Override docstring (required for Strands schema extraction)
    subagent_tool.__doc__ = (
        f"{description}\n\n"
        f"Args:\n"
        f"    query: The question or task for this specialist"
    )
    return subagent_tool



# -- Progressive Disclosure @tools ------------------------------------
# These give the supervisor on-demand access to skill metadata and
# plugin data WITHOUT spawning subagents or bloating the system prompt.
# Pattern: Layer 1 (system prompt hints) → Layer 2 (list_skills) →
#          Layer 3 (load_skill) → Layer 4 (load_data)
#
# Each is a factory function that closes over result_queue/loop so
# tool_result events reach the frontend for tool card observability.


def _emit_tool_result(
    tool_name: str,
    result_str: str,
    result_queue: asyncio.Queue | None,
    loop: asyncio.AbstractEventLoop | None,
):
    """Emit a tool_result event to the frontend via result_queue."""
    if not result_queue or not loop:
        return
    try:
        parsed = json.loads(result_str) if isinstance(result_str, str) else result_str
    except (json.JSONDecodeError, TypeError):
        parsed = {"raw": result_str[:2000]} if result_str else {}
    # Truncate large text fields to avoid SSE bloat
    if isinstance(parsed, dict):
        for key in ("content", "text", "body"):
            val = parsed.get(key)
            if isinstance(val, str) and len(val) > 2000:
                parsed = {**parsed, key: val[:2000] + "..."}
                break
    loop.call_soon_threadsafe(
        result_queue.put_nowait,
        {"type": "tool_result", "name": tool_name, "result": parsed},
    )


def _emit_package_state(
    tool_result: dict,
    tool_name: str,
    tenant_id: str,
    result_queue: asyncio.Queue,
    loop: asyncio.AbstractEventLoop,
):
    """Emit package state_update events after tools that affect the checklist.

    Pushes ``state_update`` chunks into result_queue so the streaming_routes
    layer can forward them as SSE metadata events for ``usePackageState``.
    """
    try:
        package_id = tool_result.get("package_id")
        if not package_id:
            return

        from app.package_store import get_package_checklist

        checklist = get_package_checklist(tenant_id, package_id)

        total = len(checklist.get("required", []))
        completed = len(checklist.get("completed", []))
        progress_pct = int((completed / total) * 100) if total > 0 else 0

        if tool_name == "create_document":
            # Emit document_ready + checklist_update
            doc_type = tool_result.get("doc_type") or tool_result.get("document_type")
            loop.call_soon_threadsafe(
                result_queue.put_nowait,
                {
                    "type": "state_update",
                    "state_type": "document_ready",
                    "package_id": package_id,
                    "doc_type": doc_type,
                    "checklist": checklist,
                    "progress_pct": progress_pct,
                },
            )

        # Always emit a checklist_update
        loop.call_soon_threadsafe(
            result_queue.put_nowait,
            {
                "type": "state_update",
                "state_type": "checklist_update",
                "package_id": package_id,
                "checklist": checklist,
                "progress_pct": progress_pct,
            },
        )

        # For finalize_package, emit compliance warnings if any
        if tool_name == "finalize_package":
            warnings = tool_result.get("compliance_warnings", [])
            if warnings:
                loop.call_soon_threadsafe(
                    result_queue.put_nowait,
                    {
                        "type": "state_update",
                        "state_type": "compliance_alert",
                        "package_id": package_id,
                        "severity": "warning",
                        "items": [{"name": w, "note": ""} for w in warnings[:5]],
                    },
                )
    except Exception:
        logger.debug("_emit_package_state failed (non-critical)", exc_info=True)


def _build_end_of_turn_state(package_context, tenant_id: str) -> list[dict]:
    """Build a checklist_update state event from the current package context.

    Called at the end of every turn so the frontend always has the latest
    package state — even when no document tool was called but user input
    changed acquisition method, flags, or other metadata.

    Returns a list of dicts (0 or 1) that can be yielded as SSE chunks.
    """
    try:
        if package_context is None:
            return []
        pkg_id = getattr(package_context, "package_id", None)
        if not pkg_id:
            return []

        from app.package_store import get_package_checklist, get_package

        # Re-fetch the package to pick up any mid-turn metadata changes
        pkg = get_package(tenant_id, pkg_id)
        if not pkg:
            return []

        checklist = get_package_checklist(tenant_id, pkg_id)
        total = len(checklist.get("required", []))
        completed = len(checklist.get("completed", []))
        progress_pct = int((completed / total) * 100) if total > 0 else 0

        return [{
            "type": "state_update",
            "state_type": "checklist_update",
            "package_id": pkg_id,
            "checklist": checklist,
            "progress_pct": progress_pct,
            "phase": pkg.get("status", "drafting"),
            "title": pkg.get("title", ""),
            "acquisition_method": pkg.get("acquisition_method"),
            "contract_type": pkg.get("contract_type"),
        }]
    except Exception:
        logger.debug("_build_end_of_turn_state failed (non-critical)", exc_info=True)
        return []


def _build_state_updates(tool_result: dict, tool_name: str, tenant_id: str) -> list[dict]:
    """Build state_update dicts for yield paths (fast-path / forced-doc).

    Returns a list of dicts that can be yielded directly as SSE chunks.
    Non-critical — returns empty list on error.
    """
    try:
        package_id = tool_result.get("package_id")
        if not package_id:
            return []

        from app.package_store import get_package_checklist

        checklist = get_package_checklist(tenant_id, package_id)
        total = len(checklist.get("required", []))
        completed = len(checklist.get("completed", []))
        progress_pct = int((completed / total) * 100) if total > 0 else 0

        events: list[dict] = []

        if tool_name == "create_document":
            doc_type = tool_result.get("doc_type") or tool_result.get("document_type")
            events.append({
                "type": "state_update",
                "state_type": "document_ready",
                "package_id": package_id,
                "doc_type": doc_type,
                "checklist": checklist,
                "progress_pct": progress_pct,
            })

        events.append({
            "type": "state_update",
            "state_type": "checklist_update",
            "package_id": package_id,
            "checklist": checklist,
            "progress_pct": progress_pct,
        })

        return events
    except Exception:
        logger.debug("_build_state_updates failed (non-critical)", exc_info=True)
        return []


def _make_list_skills_tool(
    result_queue: asyncio.Queue | None = None,
    loop: asyncio.AbstractEventLoop | None = None,
):
    @tool(name="list_skills")
    def list_skills_tool(category: str = "") -> str:
        """List available skills, agents, and data files with descriptions and triggers. Use this to discover what capabilities and reference data are available before diving deeper.

        Args:
            category: Filter by category: "skills", "agents", "data", or "" for all
        """
        result: dict[str, Any] = {}

        if category in ("", "skills"):
            skills_list = []
            for name, entry in SKILLS.items():
                skills_list.append({
                    "name": name,
                    "description": entry.get("description", ""),
                    "triggers": entry.get("triggers", []),
                })
            result["skills"] = skills_list

        if category in ("", "agents"):
            agents_list = []
            for name, entry in AGENTS.items():
                if name == "supervisor":
                    continue
                agents_list.append({
                    "name": name,
                    "description": entry.get("description", ""),
                    "triggers": entry.get("triggers", []),
                })
            result["agents"] = agents_list

        if category in ("", "data"):
            config = _load_plugin_config()
            data_index = config.get("data", {})
            data_list = []
            if isinstance(data_index, dict):
                for name, meta in data_index.items():
                    data_list.append({
                        "name": name,
                        "description": meta.get("description", ""),
                        "sections": meta.get("sections", []),
                    })
            result["data"] = data_list

        out = json.dumps(result, indent=2)
        _emit_tool_result("list_skills", out, result_queue, loop)
        return out

    return list_skills_tool


def _make_load_skill_tool(
    result_queue: asyncio.Queue | None = None,
    loop: asyncio.AbstractEventLoop | None = None,
):
    @tool(name="load_skill")
    def load_skill_tool(name: str) -> str:
        """Load full skill or agent instructions by name. Returns the complete SKILL.md or agent.md content so you can follow the workflow yourself without spawning a subagent. Use this when you need to understand a skill's detailed procedures, decision trees, or templates.

        Args:
            name: Skill or agent name (e.g. "oa-intake", "legal-counsel", "compliance")
        """
        entry = PLUGIN_CONTENTS.get(name)
        if not entry:
            available = sorted(PLUGIN_CONTENTS.keys())
            out = json.dumps({
                "error": f"No skill or agent named '{name}'",
                "available": available,
            })
        else:
            out = entry["body"]
        _emit_tool_result("load_skill", out, result_queue, loop)
        return out

    return load_skill_tool


def _make_load_data_tool(
    result_queue: asyncio.Queue | None = None,
    loop: asyncio.AbstractEventLoop | None = None,
):
    @tool(name="load_data")
    def load_data_tool(name: str, section: str = "") -> str:
        """Load reference data from the eagle-plugin data directory. Use this to access thresholds, contract types, document requirements, approval chains, contract vehicles, and other acquisition reference data on demand.

        Args:
            name: Data file name (e.g. "matrix", "thresholds", "contract-vehicles")
            section: Optional top-level key to extract (e.g. "thresholds", "doc_rules", "approval_chains", "contract_types"). Omit to get the full file.
        """
        config = _load_plugin_config()
        data_index = config.get("data", {})

        # Handle legacy array format: convert ["far-database.json", ...] → dict
        if isinstance(data_index, list):
            data_index = {
                f.replace(".json", ""): {"file": f"data/{f}"}
                for f in data_index
                if isinstance(f, str)
            }

        meta = data_index.get(name)
        if not meta:
            out = json.dumps({
                "error": f"No data file named '{name}'",
                "available": sorted(data_index.keys()),
            })
            _emit_tool_result("load_data", out, result_queue, loop)
            return out

        file_rel = meta.get("file", f"data/{name}.json")
        file_path = os.path.join(_PLUGIN_DIR, file_rel)

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            out = json.dumps({"error": f"Data file not found: {file_rel}"})
            _emit_tool_result("load_data", out, result_queue, loop)
            return out
        except json.JSONDecodeError as exc:
            out = json.dumps({"error": f"Invalid JSON in {file_rel}: {str(exc)}"})
            _emit_tool_result("load_data", out, result_queue, loop)
            return out

        if section:
            value = data.get(section)
            if value is None:
                out = json.dumps({
                    "error": f"Section '{section}' not found in '{name}'",
                    "available_sections": list(data.keys()),
                })
                _emit_tool_result("load_data", out, result_queue, loop)
                return out
            out = json.dumps({section: value}, indent=2, default=str)
            _emit_tool_result("load_data", out, result_queue, loop)
            return out

        out = json.dumps(data, indent=2, default=str)
        _emit_tool_result("load_data", out, result_queue, loop)
        return out

    return load_data_tool


# -- All Service @tools with named parameters -------------------------
# Replaces the generic _make_service_tool factory which used ``params: str``
# causing Pydantic schema mismatch with Bedrock models.  Each tool now
# exposes named parameters so the Strands-generated schema matches what
# Bedrock models actually send (e.g. {"operation": "list"} not {"params": "..."}).

def _build_all_service_tools(
    tenant_id: str,
    user_id: str,
    session_id: str | None,
    prompt_context: str | None = None,
    package_context: Any = None,
    result_queue: asyncio.Queue | None = None,
    loop: asyncio.AbstractEventLoop | None = None,
) -> list:
    """Build 14 service @tool functions with proper named parameters."""
    from .agentic_service import TOOL_DISPATCH
    from .compliance_matrix import execute_operation

    # Compute scoped session id once for per-user S3 scoping
    scoped_session_id = session_id
    if not scoped_session_id or "#" not in scoped_session_id:
        scoped_session_id = f"{tenant_id}#advanced#{user_id}#{session_id or ''}"

    def _emit(name: str, result) -> None:
        """Emit tool_result to frontend, truncating large text fields for non-document tools."""
        if not result_queue or not loop:
            return
        emit_result = result
        if name != "create_document" and isinstance(result, dict):
            text_val = result.get("content") or result.get("text") or result.get("result")
            if isinstance(text_val, str) and len(text_val) > 2000:
                emit_result = {**result}
                key = "content" if "content" in result else "text" if "text" in result else "result"
                emit_result[key] = text_val[:2000] + "..."
        loop.call_soon_threadsafe(
            result_queue.put_nowait,
            {"type": "tool_result", "name": name, "result": emit_result},
        )

    def _emit_input(name: str, tool_input: dict) -> None:
        """Push tool input so the stream loop can update the card."""
        if result_queue and loop:
            loop.call_soon_threadsafe(
                result_queue.put_nowait,
                {"type": "tool_input", "name": name, "input": tool_input},
            )

    # ---- 1. s3_document_ops ----
    @tool(name="s3_document_ops")
    def s3_document_ops_tool(operation: str, bucket: str = "", key: str = "", content: str = "") -> str:
        """Read, write, or list documents in S3 scoped per-tenant. Operations: list, read, write.

        Args:
            operation: S3 operation — 'list', 'read', or 'write'
            bucket: S3 bucket name (defaults to tenant bucket)
            key: S3 object key path
            content: Content to write (for 'write' operation)
        """
        parsed = {"operation": operation, "bucket": bucket, "key": key, "content": content}
        try:
            result = TOOL_DISPATCH["s3_document_ops"](parsed, tenant_id, scoped_session_id)
            _emit("s3_document_ops", result)
            return json.dumps(result, indent=2, default=str)
        except Exception as exc:
            logger.error("Service tool s3_document_ops failed: %s", exc, exc_info=True)
            return json.dumps({"error": str(exc), "tool": "s3_document_ops"})

    # ---- 2. dynamodb_intake ----
    @tool(name="dynamodb_intake")
    def dynamodb_intake_tool(operation: str, table: str = "eagle", item_id: str = "", data: dict | None = None) -> str:
        """Create, read, update, list, or query intake records in DynamoDB. Operations: create, read, update, list, query.

        Args:
            operation: DynamoDB operation — 'create', 'read', 'update', 'list', or 'query'
            table: DynamoDB table name (default 'eagle')
            item_id: Item identifier for read/update operations
            data: Data payload for create/update operations
        """
        parsed = {"operation": operation, "table": table, "item_id": item_id, "data": data or {}}
        try:
            result = TOOL_DISPATCH["dynamodb_intake"](parsed, tenant_id)
            _emit("dynamodb_intake", result)
            return json.dumps(result, indent=2, default=str)
        except Exception as exc:
            logger.error("Service tool dynamodb_intake failed: %s", exc, exc_info=True)
            return json.dumps({"error": str(exc), "tool": "dynamodb_intake"})

    # ---- 3. create_document (special prompt-context enrichment) ----
    @tool(name="create_document")
    def create_document_tool(
        doc_type: str,
        title: str = "",
        content: str = "",
        data: dict | None = None,
        package_id: str = "",
        output_format: str = "",
        update_existing_key: str = "",
        template_id: str = "",
    ) -> str:
        """Generate acquisition documents (SOW, IGCE, Market Research, J&A, Acquisition Plan, Eval Criteria, Security Checklist, Section 508, COR Certification, Contract Type Justification). Documents are saved to S3.

        CRITICAL: Always provide the `content` parameter with the FULL document markdown you have written using conversation context, intake data, and web research results. Do NOT call this tool with empty content — it produces placeholder-only stubs. YOU are the document author; this tool saves your work.

        Args:
            doc_type: Document type (sow, igce, market_research, justification, acquisition_plan, eval_criteria, security_checklist, section_508, cor_certification, contract_type_justification)
            title: Descriptive document title that includes the program or acquisition name — e.g. "SOW - Cloud Computing Services for NCI Research Portal" or "IGCE - IT Support Services FY2026". Never use a generic label like "Statement of Work" alone.
            content: REQUIRED — Full document content in markdown with all sections filled using real data from conversation context, intake answers, and web research results. This is the primary document body.
            data: Supplementary structured metadata (estimated_value, period_of_performance, naics_code, etc.) for template population. Not a substitute for content.
            package_id: Acquisition package ID to associate document with
            output_format: Output format override
            update_existing_key: S3 key of existing document to update/revise
            template_id: Template ID to use for generation
        """
        parsed = {
            "doc_type": doc_type, "title": title, "content": content,
            "data": data, "package_id": package_id,
            "output_format": output_format, "update_existing_key": update_existing_key,
            "template_id": template_id,
        }
        try:
            # -- Micro-purchase guardrail (FAR 13.2) --
            _mp_block = _check_micropurchase_guardrail(parsed)
            if _mp_block:
                return _mp_block

            # -- Document prerequisites guardrail --
            _prereq_block = _check_document_prerequisites(parsed)
            if _prereq_block:
                return _prereq_block

            # -- Prompt-context enrichment (same logic as prior factory) --
            prompt_doc_ctx = _extract_document_context_from_prompt(prompt_context or "")

            dt = str(parsed.get("doc_type", "")).strip().lower()
            if not dt:
                dt = (
                    prompt_doc_ctx.get("document_type")
                    or _infer_doc_type_from_prompt(prompt_context or "")
                    or ""
                )
                if dt:
                    parsed["doc_type"] = dt

            t = str(parsed.get("title", "")).strip()
            if not t:
                inferred_title = (
                    prompt_doc_ctx.get("title")
                    or _DOC_TYPE_LABELS.get(dt or "", "")
                    or "Untitled Acquisition"
                )
                parsed["title"] = inferred_title

            prompt_data = _extract_context_data_from_prompt(prompt_context or "", dt)
            existing_data = parsed.get("data")
            if not isinstance(existing_data, dict):
                existing_data = {}
            if prompt_data:
                for k, v in prompt_data.items():
                    existing_data.setdefault(k, v)
            current_content = prompt_doc_ctx.get("current_content")
            if current_content:
                existing_data.setdefault("current_content", current_content)
            user_request = prompt_doc_ctx.get("user_request")
            if user_request:
                existing_data.setdefault("edit_request", user_request)
            if existing_data:
                parsed["data"] = existing_data

            # Package context injection
            if (
                package_context is not None
                and getattr(package_context, "is_package_mode", False)
                and getattr(package_context, "package_id", None)
            ):
                parsed.setdefault("package_id", package_context.package_id)

            # Auto-create package if none exists — ensures checklist activates
            # even if the agent forgot to call manage_package first
            if not parsed.get("package_id"):
                try:
                    from decimal import Decimal as _Dec
                    from app.package_store import list_packages as _list_pkgs, create_package as _create_pkg

                    # Extract owner from session_id (format: tenant#tier#user#session)
                    _owner = ""
                    if session_id and "#" in session_id:
                        _parts = session_id.split("#")
                        if len(_parts) >= 3:
                            _owner = _parts[2]

                    # First: check if a package already exists for this session
                    _session_pkg = None
                    if session_id:
                        _existing_pkgs = _list_pkgs(tenant_id, owner_user_id=_owner or None)
                        for _p in _existing_pkgs:
                            if _p.get("session_id") == session_id:
                                _session_pkg = _p
                                break

                    if _session_pkg:
                        # Reuse existing session package
                        parsed["package_id"] = _session_pkg["package_id"]
                        logger.info(
                            "create_document: reusing existing session package %s",
                            _session_pkg["package_id"],
                        )
                    else:
                        # Create new package only if none exists for this session
                        _data = parsed.get("data") or {}
                        _est = _data.get("estimated_value") or _data.get("total_value") or 0
                        _title = parsed.get("title") or "Acquisition Package"
                        _req_type = _data.get("requirement_type") or "services"
                        _pkg = _create_pkg(
                            tenant_id=tenant_id,
                            owner_user_id=_owner,
                            title=_title,
                            requirement_type=_req_type,
                            estimated_value=_Dec(str(_est)),
                            session_id=session_id,
                            acquisition_method=_data.get("acquisition_method") or None,
                            contract_type=_data.get("contract_type") or None,
                        )
                        _auto_pkg_id = _pkg.get("package_id")
                        if _auto_pkg_id:
                            parsed["package_id"] = _auto_pkg_id
                            logger.info(
                                "create_document: auto-created package %s for first document",
                                _auto_pkg_id,
                            )
                            # Emit initial package state
                            if result_queue and loop:
                                _emit_package_state(_pkg, "manage_package", tenant_id, result_queue, loop)
                except Exception:
                    logger.debug("Auto-create package in create_document failed (non-critical)", exc_info=True)

            # Auto-detect existing document: if package_id + doc_type are known
            # and no update_existing_key was provided, check for an existing doc
            # and route to update mode instead of creating a duplicate.
            _pkg_id = parsed.get("package_id")
            _dt = parsed.get("doc_type", "").strip().lower()
            _upd_key = parsed.get("update_existing_key", "").strip()
            if _pkg_id and _dt and not _upd_key:
                try:
                    existing = TOOL_DISPATCH["get_latest_document"](
                        {"package_id": _pkg_id, "doc_type": _dt}, tenant_id,
                    )
                    existing_s3_key = (existing.get("document") or {}).get("s3_key", "")
                    if existing_s3_key:
                        parsed["update_existing_key"] = existing_s3_key
                        logger.info(
                            "create_document: existing %s found in package %s — routing to update (%s)",
                            _dt, _pkg_id, existing_s3_key,
                        )
                except Exception:
                    pass  # No existing doc or lookup failed — create new

            result = TOOL_DISPATCH["create_document"](parsed, tenant_id, scoped_session_id)
            _emit("create_document", result)

            if result_queue and loop and isinstance(result, dict):
                _emit_package_state(result, "create_document", tenant_id, result_queue, loop)

            return json.dumps(result, indent=2, default=str)
        except Exception as exc:
            logger.error("Service tool create_document failed: %s", exc, exc_info=True)
            return json.dumps({"error": str(exc), "tool": "create_document"})

    # ---- 4. edit_docx_document ----
    @tool(name="edit_docx_document")
    def edit_docx_document_tool(
        document_key: str,
        edits: list | None = None,
        checkbox_edits: list | None = None,
    ) -> str:
        """Apply targeted edits to an existing DOCX document. Use for text replacements or checkbox toggles.

        Args:
            document_key: S3 key of the DOCX document to edit
            edits: List of edit objects, each with 'search_text' and 'replacement_text'
            checkbox_edits: List of checkbox edit objects, each with 'label_text' and 'checked' (bool)
        """
        parsed = {"document_key": document_key, "edits": edits or [], "checkbox_edits": checkbox_edits or []}
        try:
            result = TOOL_DISPATCH["edit_docx_document"](parsed, tenant_id, scoped_session_id)
            _emit("edit_docx_document", result)
            return json.dumps(result, indent=2, default=str)
        except Exception as exc:
            logger.error("Service tool edit_docx_document failed: %s", exc, exc_info=True)
            return json.dumps({"error": str(exc), "tool": "edit_docx_document"})

    # ---- 5. get_intake_status ----
    @tool(name="get_intake_status")
    def get_intake_status_tool(intake_id: str = "") -> str:
        """Get current intake package status and completeness — shows which documents exist, which are missing, and next actions.

        Args:
            intake_id: Optional intake ID to check status for
        """
        parsed = {"intake_id": intake_id}
        try:
            result = TOOL_DISPATCH["get_intake_status"](parsed, tenant_id, scoped_session_id)
            _emit("get_intake_status", result)
            return json.dumps(result, indent=2, default=str)
        except Exception as exc:
            logger.error("Service tool get_intake_status failed: %s", exc, exc_info=True)
            return json.dumps({"error": str(exc), "tool": "get_intake_status"})

    # ---- 6. intake_workflow ----
    @tool(name="intake_workflow")
    def intake_workflow_tool(action: str, intake_id: str = "", data: dict | None = None) -> str:
        """Manage the acquisition intake workflow: start, advance, status, complete, reset.

        Args:
            action: Workflow action — 'start', 'advance', 'status', 'complete', or 'reset'
            intake_id: Intake ID to act on
            data: Additional data for the action
        """
        parsed = {"action": action, "intake_id": intake_id, "data": data or {}}
        try:
            result = TOOL_DISPATCH["intake_workflow"](parsed, tenant_id)
            _emit("intake_workflow", result)
            return json.dumps(result, indent=2, default=str)
        except Exception as exc:
            logger.error("Service tool intake_workflow failed: %s", exc, exc_info=True)
            return json.dumps({"error": str(exc), "tool": "intake_workflow"})

    # ---- 7. manage_skills ----
    @tool(name="manage_skills")
    def manage_skills_tool(
        action: str = "list",
        skill_id: str = "",
        name: str = "",
        display_name: str = "",
        description: str = "",
        prompt_body: str = "",
        triggers: list | None = None,
        tools_list: list | None = None,
        model: str = "",
        visibility: str = "private",
    ) -> str:
        """Create, list, update, delete, or publish custom skills. Actions: list, get, create, update, delete, submit, publish, disable.

        Args:
            action: Skill action — 'list', 'get', 'create', 'update', 'delete', 'submit', 'publish', 'disable'
            skill_id: Skill identifier for get/update/delete
            name: Skill name for create
            display_name: Human-readable display name
            description: Skill description
            prompt_body: Skill prompt content
            triggers: List of trigger phrases
            tools_list: List of tool names the skill can use
            model: Model override for the skill
            visibility: Skill visibility — 'private' or 'shared'
        """
        parsed = {
            "action": action, "skill_id": skill_id, "name": name,
            "display_name": display_name, "description": description,
            "prompt_body": prompt_body, "triggers": triggers or [],
            "tools": tools_list or [], "model": model, "visibility": visibility,
        }
        try:
            result = TOOL_DISPATCH["manage_skills"](parsed, tenant_id)
            _emit("manage_skills", result)
            return json.dumps(result, indent=2, default=str)
        except Exception as exc:
            logger.error("Service tool manage_skills failed: %s", exc, exc_info=True)
            return json.dumps({"error": str(exc), "tool": "manage_skills"})

    # ---- 8. manage_prompts ----
    @tool(name="manage_prompts")
    def manage_prompts_tool(
        action: str = "list",
        agent_name: str = "",
        prompt_body: str = "",
        is_append: bool = False,
    ) -> str:
        """List, view, set, or delete agent prompt overrides. Actions: list, get, set, delete, resolve.

        Args:
            action: Prompt action — 'list', 'get', 'set', 'delete', 'resolve'
            agent_name: Agent name to manage prompts for
            prompt_body: Prompt content for set action
            is_append: Whether to append to existing prompt (default false)
        """
        parsed = {
            "action": action, "agent_name": agent_name,
            "prompt_body": prompt_body, "is_append": is_append,
        }
        try:
            result = TOOL_DISPATCH["manage_prompts"](parsed, tenant_id)
            _emit("manage_prompts", result)
            return json.dumps(result, indent=2, default=str)
        except Exception as exc:
            logger.error("Service tool manage_prompts failed: %s", exc, exc_info=True)
            return json.dumps({"error": str(exc), "tool": "manage_prompts"})

    # ---- 9. manage_templates ----
    @tool(name="manage_templates")
    def manage_templates_tool(
        action: str = "list",
        doc_type: str = "",
        template_body: str = "",
        display_name: str = "",
        scope: str = "shared",
    ) -> str:
        """List, view, set, or delete document templates. Actions: list, get, set, delete, resolve.

        Args:
            action: Template action — 'list', 'get', 'set', 'delete', 'resolve'
            doc_type: Document type for the template
            template_body: Template content for set action
            display_name: Human-readable template name
            scope: Template scope — 'shared' or user-specific identifier
        """
        parsed = {
            "action": action, "doc_type": doc_type,
            "template_body": template_body, "display_name": display_name,
            "user_id": scope,
        }
        try:
            result = TOOL_DISPATCH["manage_templates"](parsed, tenant_id)
            _emit("manage_templates", result)
            return json.dumps(result, indent=2, default=str)
        except Exception as exc:
            logger.error("Service tool manage_templates failed: %s", exc, exc_info=True)
            return json.dumps({"error": str(exc), "tool": "manage_templates"})

    # ---- 10. document_changelog_search ----
    @tool(name="document_changelog_search")
    def document_changelog_search_tool(package_id: str, doc_type: str = "", limit: int = 20) -> str:
        """Search changelog history for a document or package.

        Args:
            package_id: Acquisition package ID (required)
            doc_type: Optional document type filter
            limit: Maximum results to return (default 20)
        """
        parsed = {"package_id": package_id, "doc_type": doc_type, "limit": limit}
        try:
            result = TOOL_DISPATCH["document_changelog_search"](parsed, tenant_id)
            _emit("document_changelog_search", result)
            return json.dumps(result, indent=2, default=str)
        except Exception as exc:
            logger.error("Service tool document_changelog_search failed: %s", exc, exc_info=True)
            return json.dumps({"error": str(exc), "tool": "document_changelog_search"})

    # ---- 11. get_latest_document ----
    @tool(name="get_latest_document")
    def get_latest_document_tool(package_id: str, doc_type: str) -> str:
        """Get latest document version with recent changelog entries.

        Args:
            package_id: Acquisition package ID (required)
            doc_type: Document type (required)
        """
        parsed = {"package_id": package_id, "doc_type": doc_type}
        try:
            result = TOOL_DISPATCH["get_latest_document"](parsed, tenant_id)
            _emit("get_latest_document", result)
            return json.dumps(result, indent=2, default=str)
        except Exception as exc:
            logger.error("Service tool get_latest_document failed: %s", exc, exc_info=True)
            return json.dumps({"error": str(exc), "tool": "get_latest_document"})

    # ---- 12. finalize_package (emits package state) ----
    @tool(name="finalize_package")
    def finalize_package_tool(package_id: str, auto_submit: bool = False) -> str:
        """Validate acquisition package completeness — checks for missing documents, draft-status docs, unfilled template markers, and compliance warnings.

        Args:
            package_id: Acquisition package ID (required)
            auto_submit: Whether to auto-submit if validation passes (default false)
        """
        parsed = {"package_id": package_id, "auto_submit": auto_submit}
        try:
            result = TOOL_DISPATCH["finalize_package"](parsed, tenant_id)
            _emit("finalize_package", result)
            if result_queue and loop and isinstance(result, dict):
                _emit_package_state(result, "finalize_package", tenant_id, result_queue, loop)
            return json.dumps(result, indent=2, default=str)
        except Exception as exc:
            logger.error("Service tool finalize_package failed: %s", exc, exc_info=True)
            return json.dumps({"error": str(exc), "tool": "finalize_package"})

    # ---- 13. cloudwatch_logs ----
    @tool(name="cloudwatch_logs")
    def cloudwatch_logs_tool(
        operation: str = "recent",
        log_group: str = "/eagle/app",
        filter_pattern: str = "",
        start_time: str = "",
        end_time: str = "",
        limit: int = 50,
    ) -> str:
        """Query CloudWatch Logs for application monitoring. Operations: recent, search, filter.

        Args:
            operation: Log operation — 'recent', 'search', or 'filter'
            log_group: CloudWatch log group path (default '/eagle/app')
            filter_pattern: CloudWatch filter pattern expression
            start_time: Start time — ISO 8601 or relative like '-1h', '-30m'
            end_time: End time — ISO 8601 or relative
            limit: Maximum log entries to return (default 50)
        """
        parsed = {
            "operation": operation, "log_group": log_group,
            "filter_pattern": filter_pattern, "start_time": start_time,
            "end_time": end_time, "limit": limit, "user_id": user_id,
        }
        try:
            result = TOOL_DISPATCH["cloudwatch_logs"](parsed, tenant_id)
            _emit("cloudwatch_logs", result)
            return json.dumps(result, indent=2, default=str)
        except Exception as exc:
            logger.error("Service tool cloudwatch_logs failed: %s", exc, exc_info=True)
            return json.dumps({"error": str(exc), "tool": "cloudwatch_logs"})

    # ---- 14. query_compliance_matrix ----
    @tool(name="query_compliance_matrix")
    def query_compliance_matrix_tool(
        operation: str,
        contract_value: float = 0,
        acquisition_method: str = "",
        contract_type: str = "",
        is_it: bool = False,
        is_small_business: bool = False,
        is_rd: bool = False,
        is_human_subjects: bool = False,
        is_services: bool = True,
        keyword: str = "",
    ) -> str:
        """Query NCI/NIH contract requirements decision tree. Operations: query, list_methods, list_types, list_thresholds, search_far, suggest_vehicle.

        Args:
            operation: Matrix operation — 'query', 'list_methods', 'list_types', 'list_thresholds', 'search_far', 'suggest_vehicle'
            contract_value: Contract dollar value
            acquisition_method: Acquisition method code (e.g. 'sap', 'sealed_bidding')
            contract_type: Contract type code (e.g. 'ffp', 'cpff')
            is_it: Whether this is an IT acquisition
            is_small_business: Whether small business set-aside applies
            is_rd: Whether this is R&D
            is_human_subjects: Whether human subjects are involved
            is_services: Whether this is a services contract (default true)
            keyword: Keyword search term
        """
        parsed = {
            "operation": operation, "contract_value": contract_value,
            "acquisition_method": acquisition_method, "contract_type": contract_type,
            "is_it": is_it, "is_small_business": is_small_business,
            "is_rd": is_rd, "is_human_subjects": is_human_subjects,
            "is_services": is_services, "keyword": keyword,
        }
        try:
            _emit_input("query_compliance_matrix", parsed)
            result = execute_operation(parsed)
            out = json.dumps(result, indent=2, default=str)
            _emit("query_compliance_matrix", result if isinstance(result, dict) else {"result": result})
            return out
        except Exception as exc:
            logger.error("Service tool query_compliance_matrix failed: %s", exc, exc_info=True)
            return json.dumps({"error": str(exc), "tool": "query_compliance_matrix"})

    # ---- 15. manage_package (emits package state) ----
    @tool(name="manage_package")
    def manage_package_tool(
        operation: str,
        package_id: str = "",
        title: str = "",
        requirement_type: str = "",
        estimated_value: float = 0,
        acquisition_method: str = "",
        contract_type: str = "",
        contract_vehicle: str = "",
        notes: str = "",
        updates: dict | None = None,
        status: str = "",
    ) -> str:
        """Create, read, update, or list acquisition packages. Packages track required/completed documents, checklist progress, and lifecycle status. Call 'create' after gathering intake info to activate the checklist panel.

        Args:
            operation: Package operation — 'create', 'get', 'update', 'list', or 'checklist'
            package_id: Package ID for get/update/checklist (e.g. PKG-2026-0001)
            title: Package title (for create)
            requirement_type: Requirement type — services, supplies, IT, construction, R&D (for create)
            estimated_value: Estimated contract dollar value (for create/update)
            acquisition_method: Acquisition method code (for create/update)
            contract_type: Contract type code (for create/update)
            contract_vehicle: Contract vehicle if applicable (for create/update)
            notes: Additional notes (for create/update)
            updates: Fields to update (for update operation)
            status: Filter by status (for list operation)
        """
        parsed = {
            "operation": operation, "package_id": package_id,
            "title": title, "requirement_type": requirement_type,
            "estimated_value": estimated_value,
            "acquisition_method": acquisition_method,
            "contract_type": contract_type,
            "contract_vehicle": contract_vehicle,
            "notes": notes, "updates": updates or {},
            "status": status,
        }
        try:
            result = TOOL_DISPATCH["manage_package"](parsed, tenant_id, scoped_session_id)
            _emit("manage_package", result)

            # Emit SSE state_update for create/update/checklist operations
            if result_queue and loop and isinstance(result, dict):
                pkg_id = result.get("package_id")
                if pkg_id and operation in ("create", "update"):
                    _emit_package_state(result, "manage_package", tenant_id, result_queue, loop)

                    # Also emit initial package_created event for create
                    if operation == "create":
                        from app.package_store import get_package_checklist
                        checklist = get_package_checklist(tenant_id, pkg_id)
                        total = len(checklist.get("required", []))
                        completed = len(checklist.get("completed", []))
                        progress_pct = int((completed / total) * 100) if total > 0 else 0
                        loop.call_soon_threadsafe(
                            result_queue.put_nowait,
                            {
                                "type": "state_update",
                                "state_type": "checklist_update",
                                "package_id": pkg_id,
                                "checklist": checklist,
                                "progress_pct": progress_pct,
                                "phase": result.get("status", "intake"),
                                "title": result.get("title", ""),
                                "acquisition_method": result.get("acquisition_method"),
                                "contract_type": result.get("contract_type"),
                            },
                        )

            return json.dumps(result, indent=2, default=str)
        except Exception as exc:
            logger.error("Service tool manage_package failed: %s", exc, exc_info=True)
            return json.dumps({"error": str(exc), "tool": "manage_package"})

    return [
        s3_document_ops_tool,
        dynamodb_intake_tool,
        create_document_tool,
        edit_docx_document_tool,
        get_intake_status_tool,
        intake_workflow_tool,
        manage_skills_tool,
        manage_prompts_tool,
        manage_templates_tool,
        document_changelog_search_tool,
        get_latest_document_tool,
        finalize_package_tool,
        cloudwatch_logs_tool,
        query_compliance_matrix_tool,
        manage_package_tool,
    ]


def _build_kb_service_tools(
    tenant_id: str,
    user_id: str,
    session_id: str | None,
    result_queue: asyncio.Queue | None = None,
    loop: asyncio.AbstractEventLoop | None = None,
) -> list:
    """Build KB tools with proper named parameters so Bedrock models send structured args.

    The generic _make_service_tool factory uses ``params: str`` which generates a schema
    like ``{"params": {"type": "string"}}``.  Models frequently ignore the wrapper and
    send ``{"query": "..."}`` directly, causing Pydantic validation to fail and the tool
    to receive empty input.  These dedicated @tool definitions expose each field by name
    so the model schema matches natural tool-calling behaviour.
    """
    from .agentic_service import _exec_search_far
    from .tools.knowledge_tools import exec_knowledge_search, exec_knowledge_fetch

    def _emit_input(name: str, tool_input: dict) -> None:
        """Push tool input so the stream loop can update the card."""
        if result_queue and loop:
            loop.call_soon_threadsafe(
                result_queue.put_nowait,
                {"type": "tool_input", "name": name, "input": tool_input},
            )

    def _emit(name: str, result: dict) -> None:
        if result_queue and loop:
            truncated_result = {k: (v[:3000] + "..." if isinstance(v, str) and len(v) > 3000 else v)
                                for k, v in result.items()} if isinstance(result, dict) else result
            loop.call_soon_threadsafe(
                result_queue.put_nowait,
                {"type": "tool_result", "name": name, "result": truncated_result},
            )

    @tool(name="search_far")
    def search_far(query: str, parts: list[str] | None = None) -> str:
        """Search FAR/DFARS for clauses, requirements, and guidance. Returns s3_keys for full document retrieval — ALWAYS call knowledge_fetch on returned s3_keys before responding.

        Args:
            query: Search query — topic, clause number, or keyword
            parts: Optional list of FAR part numbers to filter (e.g. ["6", "16"])
        """
        _emit_input("search_far", {"query": query, "parts": parts})
        result = _exec_search_far({"query": query, "parts": parts}, tenant_id)
        _emit("search_far", result)
        return json.dumps(result, indent=2, default=str)

    @tool(name="knowledge_search")
    def knowledge_search(
        query: str = "",
        topic: str = "",
        document_type: str = "",
        agent: str = "",
        authority_level: str = "",
        keywords: list[str] | None = None,
        limit: int = 10,
    ) -> str:
        """Search the acquisition knowledge base metadata in DynamoDB. Use 'query' for specific identifiers like case numbers, citations, or keywords. Use 'topic' for broad subject searches.

        Args:
            query: Search query — case numbers, citations, identifiers, or keywords
            topic: Broad topic filter (e.g. "competition", "small business")
            document_type: Filter by document type
            agent: Filter by agent/specialist
            authority_level: Filter by authority level
            keywords: List of keyword filters
            limit: Maximum results to return (default 10)
        """
        params = {k: v for k, v in {
            "query": query, "topic": topic, "document_type": document_type,
            "agent": agent, "authority_level": authority_level,
            "keywords": keywords, "limit": limit,
        }.items() if v}
        _emit_input("knowledge_search", params)
        result = exec_knowledge_search(params, tenant_id, session_id)
        _emit("knowledge_search", result)
        return json.dumps(result, indent=2, default=str)

    @tool(name="knowledge_fetch")
    def knowledge_fetch(s3_key: str) -> str:
        """Fetch full knowledge document content from S3. REQUIRES an s3_key from a prior knowledge_search or search_far result.

        Args:
            s3_key: S3 key path from a knowledge_search or search_far result
        """
        _emit_input("knowledge_fetch", {"s3_key": s3_key})
        result = exec_knowledge_fetch({"s3_key": s3_key}, tenant_id, session_id)
        _emit("knowledge_fetch", result)
        return json.dumps(result, indent=2, default=str)

    @tool(name="web_search")
    def web_search_tool(query: str) -> str:
        """Search the web for real-time information. Use for current market data, vendor info, pricing, policy updates, or any topic needing up-to-date info beyond the knowledge base.

        IMPORTANT: After EVERY web_search call, you MUST call web_fetch on the top 5 source URLs returned. Search snippets are incomplete — they miss pricing tiers, licensing terms, compliance details, and contract vehicle numbers. Never cite a source you have not web_fetched.

        Args:
            query: Natural language search query
        """
        _emit_input("web_search", {"query": query})
        result = exec_web_search(query)
        _emit("web_search", result)
        return json.dumps(result, indent=2, default=str)

    @tool(name="web_fetch")
    def web_fetch_tool(url: str) -> str:
        """Fetch a web page and return its content as clean markdown. MUST be called on top 5 source URLs after EVERY web_search. Search snippets alone are unreliable — always read the full page.

        Args:
            url: The URL to fetch (must be http or https)
        """
        _emit_input("web_fetch", {"url": url})
        result = exec_web_fetch(url)
        _emit("web_fetch", result)
        return json.dumps(result, indent=2, default=str)

    return [search_far, knowledge_search, knowledge_fetch, web_search_tool, web_fetch_tool]


def _build_service_tools(
    tenant_id: str,
    user_id: str,
    session_id: str | None,
    prompt_context: str | None = None,
    package_context: Any = None,
    result_queue: asyncio.Queue | None = None,
    loop: asyncio.AbstractEventLoop | None = None,
) -> list:
    """Build @tool wrappers for AWS service tools, scoped to the current tenant/user/session."""
    tools = _build_all_service_tools(
        tenant_id, user_id, session_id,
        prompt_context=prompt_context,
        package_context=package_context,
        result_queue=result_queue, loop=loop,
    )
    # Add KB tools with proper named parameters
    tools.extend(_build_kb_service_tools(tenant_id, user_id, session_id, result_queue, loop))
    # Add progressive disclosure tools
    tools.append(_make_list_skills_tool(result_queue, loop))
    tools.append(_make_load_skill_tool(result_queue, loop))
    tools.append(_make_load_data_tool(result_queue, loop))
    return tools


# -- build_skill_tools() ---------------------------------------------

def build_skill_tools(
    tier: str = "advanced",
    skill_names: list[str] | None = None,
    tenant_id: str = "demo-tenant",
    user_id: str = "demo-user",
    workspace_id: str | None = None,
    session_id: str = "",
    result_queue: asyncio.Queue | None = None,
    loop: asyncio.AbstractEventLoop | None = None,
) -> list:
    """Build @tool-wrapped subagent functions from skill registry.

    Same 4-layer prompt resolution as sdk_agentic_service.build_skill_agents():
      1. Workspace override (wspc_store)
      2. DynamoDB PLUGIN# canonical (plugin_store)
      3. Bundled eagle-plugin/ files (PLUGIN_CONTENTS)
      4. Tenant custom SKILL# items (skill_store)

    Returns:
        List of @tool-decorated functions suitable for Agent(tools=[...])
    """
    tools = []

    # Build doc tools once — only given to subagents that need them
    _doc_tools = _build_subagent_doc_tools(tenant_id, user_id, session_id, result_queue, loop)
    # Subagents that get document creation/editing capabilities
    _DOC_TOOL_AGENTS = {"market-intelligence"}

    for name, meta in SKILL_AGENT_REGISTRY.items():
        if skill_names and name not in skill_names:
            continue

        # Resolve prompt through workspace chain when workspace_id is available
        prompt_body = ""
        if workspace_id:
            try:
                from .wspc_store import resolve_skill
                prompt_body, _source = resolve_skill(tenant_id, user_id, workspace_id, name)
            except Exception as exc:
                logger.warning("wspc_store.resolve_skill failed for %s: %s -- using bundled", name, exc)
                prompt_body = ""

        # Fall back to bundled PLUGIN_CONTENTS
        if not prompt_body:
            entry = PLUGIN_CONTENTS.get(meta["skill_key"])
            if not entry:
                logger.warning("Plugin content not found for %s (key=%s)", name, meta["skill_key"])
                continue
            prompt_body = entry["body"]

        extra = _doc_tools if name in _DOC_TOOL_AGENTS else None

        tools.append(_make_subagent_tool(
            skill_name=name,
            description=meta["description"],
            prompt_body=_truncate_skill(prompt_body),
            result_queue=result_queue,
            loop=loop,
            tenant_id=tenant_id,
            user_id=user_id,
            tier=tier,
            session_id=session_id,
            extra_tools=extra,
        ))

    # Merge active user-created SKILL# items
    try:
        from .skill_store import list_active_skills
        user_skills = list_active_skills(tenant_id)
        for skill in user_skills:
            name = skill.get("name", "")
            if not name:
                continue
            if skill_names and name not in skill_names:
                continue
            skill_prompt = skill.get("prompt_body", "")
            if not skill_prompt:
                continue
            tools.append(_make_subagent_tool(
                skill_name=name,
                description=skill.get("description", f"{name} specialist"),
                prompt_body=_truncate_skill(skill_prompt),
                result_queue=result_queue,
                loop=loop,
                tenant_id=tenant_id,
                user_id=user_id,
                tier=tier,
                session_id=session_id,
            ))
    except Exception as exc:
        logger.warning("skill_store.list_active_skills failed for %s: %s -- skipping user skills", tenant_id, exc)

    return tools


# -- Document Section Hints (injected into supervisor prompt) --------

def _build_doc_type_section_hints() -> str:
    """Build concise section hints for each doc type, for the supervisor prompt.

    Returns a compact string with one line per doc type listing section names.
    """
    try:
        from app.template_schema import load_template_schemas
        schemas = load_template_schemas()
    except Exception:
        return ""

    lines = []
    # Only include the primary doc types with rich schemas
    priority_types = [
        "sow", "igce", "acquisition_plan", "market_research", "justification",
    ]
    for dt in priority_types:
        schema = schemas.get(dt)
        if not schema or not schema.sections:
            continue
        section_names = [
            f"{s.number}. {s.title}" if s.number else s.title
            for s in schema.sections[:12]  # Cap at 12 for prompt brevity
        ]
        lines.append(f"    {dt.upper()}: {' | '.join(section_names)}")

    if lines:
        return "\n".join(lines) + "\n"
    return ""


# Pre-compute at module load — output is static (changes only on deployment)
_DOC_SECTION_HINTS: str = _build_doc_type_section_hints()


# -- Supervisor Prompt -----------------------------------------------

import time as _time

_supervisor_prompt_cache: dict[tuple, tuple[float, str]] = {}
_PROMPT_CACHE_TTL = 120  # seconds


def _build_supervisor_prompt_body(
    tenant_id: str,
    user_id: str,
    tier: str,
    agent_names: list[str] | None,
    workspace_id: str | None,
) -> str:
    """Build the supervisor prompt body (everything except the timestamp header).

    Resolves through the 4-layer chain: workspace override → DynamoDB →
    bundled content → fallback.
    """
    names = agent_names or list(SKILL_AGENT_REGISTRY.keys())
    agent_list = "\n".join(
        f"- {name}: {SKILL_AGENT_REGISTRY[name]['description']}"
        for name in names
        if name in SKILL_AGENT_REGISTRY
    )

    # Resolve supervisor prompt via workspace chain
    base_prompt = ""
    if workspace_id:
        try:
            from .wspc_store import resolve_agent
            base_prompt, _source = resolve_agent(tenant_id, user_id, workspace_id, "supervisor")
        except Exception as exc:
            logger.warning("wspc_store.resolve_agent failed for supervisor: %s -- using bundled", exc)

    if not base_prompt:
        supervisor_entry = AGENTS.get("supervisor")
        base_prompt = supervisor_entry["body"].strip() if supervisor_entry else "You are the EAGLE Supervisor Agent for NCI Office of Acquisitions."

    return (
        f"{base_prompt}\n\n"
        f"--- ACTIVE SPECIALISTS ---\n"
        f"Available specialists for delegation:\n{agent_list}\n\n"
        "Progressive Disclosure (how to find information):\n"
        "  You have layered access to skills and data. Use the lightest layer that answers the question:\n"
        "  Layer 1 — System prompt hints (you already have short descriptions above).\n"
        "  Layer 2 — list_skills(): Discover available skills, agents, and data files with descriptions.\n"
        "  Layer 3 — load_skill(name): Read full skill instructions/workflows to follow them yourself.\n"
        "  Layer 4 — load_data(name, section?): Fetch reference data (thresholds, vehicles, doc rules).\n"
        "  Only spawn a specialist subagent when you need expert reasoning, not for simple lookups.\n\n"
        "RESEARCH CASCADE — INTERNAL SOURCES FIRST (applies to MOST responses):\n"
        "Before answering any acquisition, compliance, regulation, threshold, document, or procedural "
        "question, follow this mandatory order. Do NOT skip to web_search without checking internal "
        "sources first.\n\n"
        "  STEP 1 — Knowledge Base:\n"
        "    a) Call knowledge_search with relevant query, topic, and/or keywords.\n"
        "    b) If results found, call knowledge_fetch on the top 1-3 relevant s3_keys.\n"
        "    c) The KB is your primary source of truth — approved FAR/DFARS text, NIH policies, "
        "templates, precedents.\n"
        "    d) Prefer knowledge_search/knowledge_fetch over search_far when KB can answer.\n"
        "    e) When search_far returns results with non-empty s3_keys, you MUST call "
        "knowledge_fetch on the top result's s3_key to read the full FAR document "
        "BEFORE responding. Never answer from the summary alone.\n"
        "    f) If a search_far result has empty s3_keys, the summary is the best available.\n\n"
        "  STEP 2 — Compliance Matrix:\n"
        "    a) Call query_compliance_matrix when the question involves dollar thresholds, "
        "required documents, contract types, acquisition methods, competition rules, "
        "vehicle selection, or approval levels.\n"
        "    b) The matrix encodes current FAR thresholds (FAC 2025-06), document requirements "
        "by value tier, and NCI-specific rules — do NOT answer these from memory.\n"
        "    c) For vehicle recommendations, use operation='suggest_vehicle'.\n"
        "    d) For threshold/document checks, use operation='query' with contract_value.\n\n"
        "  STEP 3 — Web Search (only when internal sources insufficient):\n"
        "    a) Use web_search for current market data, vendor info, pricing, GSA rates, "
        "recent policy changes, or any topic needing real-time info beyond the KB.\n"
        "    b) After web_search, ALWAYS call web_fetch on the top 2-3 source URLs to read "
        "the full page content. web_search only returns snippets.\n"
        "    c) Never cite a source you have not web_fetched.\n\n"
        "  EXCEPTIONS (skip cascade): Greetings, document edits, package management ops, "
        "or when user explicitly requests web search.\n\n"
        "  CITATION — In final answers, include a Sources section with title + s3_key for KB docs "
        "and URL for web sources. If no KB results, explicitly say so.\n\n"
        "COLLECT BEFORE RESEARCH — Before performing web research for any document, you MUST\n"
        "first collect a minimum set of information from the user. If any item is missing,\n"
        "ASK the user — do NOT assume or invent values.\n\n"
        "  Required intake for market_research:\n"
        "    - What is being acquired? (requirement description)\n"
        "    - NAICS code or industry sector\n"
        "    - Estimated value or budget range\n"
        "  Required intake for igce:\n"
        "    - What is being acquired? (requirement description)\n"
        "    - Labor categories, products, or line items to price\n"
        "    - Period of performance\n"
        "    - Estimated value or budget range\n"
        "  Required intake for justification (J&A):\n"
        "    - What is being acquired? (requirement description)\n"
        "    - Proposed contractor name\n"
        "    - J&A authority (FAR 6.302 subsection)\n"
        "  Required intake for acquisition_plan:\n"
        "    - What is being acquired? (requirement description)\n"
        "    - Estimated value or budget range\n"
        "    - Planned contract type (FFP, T&M, CR, etc.)\n\n"
        "  If the user says 'generate market research' without providing these details,\n"
        "  respond: 'I need a few details before I can research and generate your document:'\n"
        "  and list the missing items as a numbered checklist.\n\n"
        "RESEARCH BEFORE DOCUMENT — Required steps before calling create_document:\n"
        "  Do NOT generate any document with placeholder data. Gather real data first.\n"
        "  NOTE: create_document has a code-level guardrail that will REJECT documents\n"
        "  missing required fields or containing placeholder markers. Ensure you have\n"
        "  collected the required intake AND completed research before calling it.\n\n"
        "  market_research:\n"
        "    1. web_search for vendor landscape ('{requirement} vendors government contract')\n"
        "    2. web_search for pricing/rates ('{requirement} GSA schedule pricing')\n"
        "    3. web_search for small business sources ('{requirement} small business SAM.gov')\n"
        "    4. web_fetch on the top 2-3 URLs from EACH search to read full content\n"
        "    5. 'content' MUST include: real vendor names, actual pricing ranges, specific contract vehicles, and a Sources section with URLs\n"
        "    6. If web_search returns no useful results for a section, state 'No sources identified' — do NOT insert placeholder text\n"
        "    ALTERNATIVE: Delegate to market_intelligence with a detailed query\n\n"
        "  igce:\n"
        "    1. web_search for current GSA schedule rates for the labor categories/products needed\n"
        "    2. web_fetch on top pricing sources to get actual rate tables\n"
        "    3. 'content' MUST include specific dollar amounts (not $[Amount]) with sourced rates\n"
        "    4. If pricing from user-provided quote, still search for independent benchmarks\n\n"
        "  justification:\n"
        "    1. Market research must be completed first (document or in-conversation research)\n"
        "    2. web_search to verify proposed contractor's unique qualifications\n"
        "    3. search_far for the specific FAR 6.302 authority, then knowledge_fetch full text\n"
        "    4. 'content' MUST reference specific market findings, named alternatives considered\n\n"
        "  acquisition_plan:\n"
        "    1. Market research findings must be available\n"
        "    2. Cost/pricing data must be available\n"
        "    3. search_far for FAR 7.105 (AP structure), 16.1 (contract type)\n\n"
        "  sow:\n"
        "    1. Gather requirements from conversation (tasks, deliverables, PoP)\n"
        "    2. If user has not provided detailed tasks, ASK — do not invent requirements\n"
        "    3. Do NOT generate with generic '[Task Name]' placeholders\n\n"
        "  All other doc types:\n"
        "    1. Gather specifics from intake discussion — no placeholders\n\n"
        "  CITATION RULE — ALL documents with web research MUST include a Sources section:\n"
        "    - Source description, URL, date accessed\n\n"
        "MICRO-PURCHASE GUARDRAIL (FAR 13.2):\n"
        "If the estimated value is under $15,000, do NOT generate a formal SOW, IGCE, or "
        "Acquisition Plan — these are not required for micro-purchases. Respond with guidance "
        "on simplified purchase procedures (purchase card, micro-purchase order) instead. "
        "If the user explicitly asks for a SOW for a micro-purchase, redirect: 'For purchases "
        "under $15K, a formal SOW is not required under FAR 13.2. You need a purchase "
        "description or simple requirements document. Would you like help with that instead?'\n\n"
        "Document Output Rules:\n"
        "0) CHECK BEFORE CREATE: Before generating any document, call get_latest_document "
        "with the package_id and doc_type to check if one already exists. If it does:\n"
        "   - For CONTENT changes (add sections, rewrite, regenerate): call create_document "
        "with update_existing_key set to the existing document's s3_key. Write the FULL "
        "updated content incorporating the requested changes.\n"
        "   - For TARGETED edits (fix a typo, change a name, toggle a checkbox): call "
        "edit_docx_document with the document_key and specific edits.\n"
        "   - Only create a brand-new document (no update_existing_key) if no existing "
        "document was found for that doc_type.\n"
        "1) If the user asks to generate/draft/create a document, you MUST call create_document — "
        "EXCEPT when the value is under $15,000 (micro-purchase threshold per FAR 13.2). "
        "For micro-purchases, do NOT generate a formal SOW/IGCE/AP — redirect to simplified purchase procedures.\n"
        "1a) CRITICAL: Write the COMPLETE document content as the 'content' field (markdown with "
        "section headings, filled-in details from the conversation). Do NOT leave template "
        "placeholders — fill every section with specifics from the intake discussion.\n"
        "1a-i) NEVER pass content containing {{PLACEHOLDER}}, [TBD], [Insert...], [Amount], "
        "[Vendor Name] or similar template markers. If data is missing, research it first "
        "or write 'Information not yet gathered — requires [specific action]'.\n"
        "1a-ii) For market_research and igce doc types: if you have NOT called web_search "
        "at least once in this conversation, you MUST do so before calling create_document.\n"
        "1b) Also pass structured fields in 'data' (description, estimated_value, "
        "period_of_performance, competition, contract_type, deliverables, tasks, etc.) "
        "for template population.\n"
        "1c) If the user asks to revise an existing DOCX document, use edit_docx_document "
        "for targeted edits and checkbox_edits for checklist toggles.\n"
        "1d) SECTION GUIDANCE — each document type has required sections. Fill ALL of them:\n"
        f"{_DOC_SECTION_HINTS}"
        "2) Do not paste full document bodies in chat unless the user explicitly asks for inline text.\n"
        "3) After create_document, respond briefly and direct the user to open/edit the document card.\n\n"
        "FAST vs DEEP routing:\n"
        "  FAST (seconds):\n"
        "    - load_data('matrix', 'thresholds') for threshold lookups.\n"
        "    - load_data('contract-vehicles', 'nitaac') for vehicle details.\n"
        "    - query_compliance_matrix for computed compliance decisions.\n"
        "    - search_far → knowledge_fetch(s3_key) for FAR/DFARS clause lookups (search, then read full doc).\n"
        "    - knowledge_search → knowledge_fetch for KB documents.\n"
        "    - web_search → web_fetch(top URLs) for current market data, news, vendor info, pricing.\n"
        "    - load_skill(name) to read a workflow and follow it yourself.\n"
        "  DEEP (specialist): Delegate to specialist subagents only for complex analysis,\n"
        "    multi-factor evaluation, or expert reasoning — not simple factual lookups.\n"
        "  ALWAYS prefer FAST tools first. Only delegate to a specialist when FAST tools don't suffice.\n\n"
        "IMPORTANT: Use the available tool functions to delegate to specialists. "
        "Include relevant context in the query you pass to each specialist. "
        "Do not try to answer specialized questions yourself -- delegate to the expert."
    )


def build_supervisor_prompt(
    tenant_id: str = "demo-tenant",
    user_id: str = "demo-user",
    tier: str = "advanced",
    agent_names: list[str] | None = None,
    workspace_id: str | None = None,
    preloaded_context: str | None = None,
) -> str:
    """Build the supervisor system prompt with available subagent descriptions.

    Caches the prompt body per (tenant_id, workspace_id, tier) with 120s TTL.
    Only the timestamp header and preloaded_context are dynamic on every call.
    """
    cache_key = (tenant_id, workspace_id or "", tier)
    now = _time.time()
    entry = _supervisor_prompt_cache.get(cache_key)

    if entry and now < entry[0]:
        body = entry[1]
    else:
        body = _build_supervisor_prompt_body(tenant_id, user_id, tier, agent_names, workspace_id)
        _supervisor_prompt_cache[cache_key] = (now + _PROMPT_CACHE_TTL, body)

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S UTC")
    header = f"Tenant: {tenant_id} | User: {user_id} | Tier: {tier} | Current datetime: {now_utc}"
    if preloaded_context:
        header = f"{header}\n\n{preloaded_context}"
    return f"{header}\n\n{body}"


# -- SDK Query Wrappers (same signatures as sdk_agentic_service.py) --

def _to_strands_messages(anthropic_messages: list[dict]) -> list[dict]:
    """Convert Anthropic-format messages to Strands Message format.

    Anthropic: [{"role": "user", "content": "text"}, ...]
    Strands:   [{"role": "user", "content": [{"text": "text"}]}, ...]
    """
    strands_msgs = []
    for msg in anthropic_messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, str):
            strands_msgs.append({"role": role, "content": [{"text": content}]})
        elif isinstance(content, list):
            # Already in block format — pass through
            strands_msgs.append({"role": role, "content": content})
    return strands_msgs


async def sdk_query(
    prompt: str,
    tenant_id: str = "demo-tenant",
    user_id: str = "demo-user",
    tier: str = "advanced",
    model: str = None,
    skill_names: list[str] | None = None,
    session_id: str | None = None,
    workspace_id: str | None = None,
    package_context: Any = None,
    max_turns: int = 15,
    messages: list[dict] | None = None,
    username: str | None = None,
    tags: list[str] | None = None,
) -> AsyncGenerator[Any, None]:
    """Run a supervisor query with skill subagents (Strands implementation).

    Same signature as sdk_agentic_service.sdk_query(). Yields adapter objects
    that match the AssistantMessage/ResultMessage interface expected by callers.

    Args:
        prompt: User's query/request
        tenant_id: Tenant identifier for multi-tenant isolation
        user_id: User identifier
        tier: Subscription tier (basic/advanced/premium)
        model: Model override (unused in Strands -- model is shared)
        skill_names: Subset of skills to make available
        session_id: Session ID for session persistence
        workspace_id: Active workspace for per-user prompt resolution
        max_turns: Max tool-use iterations (reserved for future use)
        messages: Conversation history in Anthropic format (excludes current prompt)

    Yields:
        AssistantMessage and ResultMessage adapter objects
    """
    fast_path = await _maybe_fast_path_document_generation(
        prompt=prompt,
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        package_context=package_context,
    )
    if fast_path is not None:
        result = fast_path["result"]
        if fast_path.get("guardrail"):
            yield AssistantMessage(content=[TextBlock(text=result["message"])])
            yield ResultMessage(result=result["message"], usage={})
            return
        if "error" in result:
            yield AssistantMessage(content=[TextBlock(text=f"Document generation failed: {result['error']}")])
            yield ResultMessage(result=f"Document generation failed: {result['error']}", usage={})
            return

        text = (
            f"Generated a draft {fast_path['doc_type'].replace('_', ' ')} document. "
            "You can open it from the document card."
        )
        yield AssistantMessage(
            content=[
                TextBlock(text=text),
                ToolUseBlock(name="create_document"),
            ]
        )
        yield ResultMessage(
            result=text,
            usage={"tools_called": 1, "tools": ["create_document"], "fast_path": True},
        )
        return

    # Resolve active workspace when none provided
    resolved_workspace_id = workspace_id
    if not resolved_workspace_id:
        try:
            from .workspace_store import get_or_create_default
            ws = get_or_create_default(tenant_id, user_id)
            resolved_workspace_id = ws.get("workspace_id")
        except Exception as exc:
            logger.warning("workspace_store.get_or_create_default failed: %s -- using bundled prompts", exc)

    # Fire preload concurrently with sync tool-building
    from .session_preloader import preload_session_context, format_context_for_prompt
    _pkg_id = package_context.package_id if package_context and package_context.is_package_mode else None
    _preload_task = asyncio.create_task(
        preload_session_context(tenant_id, user_id, package_id=_pkg_id),
    )

    skill_tools = build_skill_tools(
        tier=tier,
        skill_names=skill_names,
        tenant_id=tenant_id,
        user_id=user_id,
        workspace_id=resolved_workspace_id,
        session_id=session_id or "",
    )

    # Build service tools (S3, DynamoDB, create_document, search_far, etc.)
    service_tools = _build_service_tools(
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        prompt_context=prompt,
        package_context=package_context,
    )

    preloaded_ctx = await _preload_task
    _ctx_str = format_context_for_prompt(preloaded_ctx)

    system_prompt = build_supervisor_prompt(
        tenant_id=tenant_id,
        user_id=user_id,
        tier=tier,
        agent_names=[t.__name__ for t in skill_tools],
        workspace_id=resolved_workspace_id,
        preloaded_context=_ctx_str or None,
    )

    # Convert conversation history to Strands format (excludes current prompt)
    strands_history = _to_strands_messages(messages) if messages else None

    _ensure_langfuse_exporter()
    supervisor = Agent(
        model=_model,
        system_prompt=system_prompt,
        tools=skill_tools + service_tools,
        callback_handler=None,
        messages=strands_history,
        trace_attributes=_build_trace_attrs(
            tenant_id=tenant_id,
            user_id=user_id,
            tier=tier,
            session_id=session_id or "",
            username=username or "",
            eval_tags=tags,
        ),
    )

    # Synchronous call -- Strands handles the agentic loop internally
    result = supervisor(prompt)
    result_text = str(result)

    # Explicitly register sessionId (and tags) in Langfuse via REST API.
    # OTEL span attribute langfuse.session.id is set, but Langfuse's OTEL
    # receiver may not always propagate it to the sessionId field. This
    # REST patch ensures the trace is always findable by session and tags.
    if session_id and supervisor.trace_span:
        try:
            from opentelemetry.trace import format_trace_id
            span_ctx = supervisor.trace_span.get_span_context()
            if span_ctx and span_ctx.is_valid:
                await _langfuse_set_session(
                    format_trace_id(span_ctx.trace_id),
                    session_id,
                    user_id=user_id,
                    tags=tags,
                )
        except Exception:
            pass

    # Extract tool names called during execution from metrics.tool_metrics
    tools_called = []
    try:
        metrics = getattr(result, "metrics", None)
        if metrics and hasattr(metrics, "tool_metrics"):
            tools_called = list(metrics.tool_metrics.keys())
    except Exception:
        pass

    forced_doc = await _ensure_create_document_for_direct_request(
        prompt=prompt,
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        package_context=package_context,
        tools_called=tools_called,
    )
    if forced_doc is not None:
        tools_called.append("create_document")
        result_text = (
            f"Generated a draft {forced_doc['doc_type'].replace('_', ' ')} document. "
            "Open the document card to review or edit it."
        )

    # Build content blocks for AssistantMessage
    content_blocks = [TextBlock(text=result_text)]
    for tool_name in tools_called:
        content_blocks.append(ToolUseBlock(name=tool_name))

    # Yield adapter messages matching Claude SDK interface
    yield AssistantMessage(content=content_blocks)

    # Extract usage if available
    usage = {}
    try:
        metrics = getattr(result, "metrics", None)
        if metrics:
            acc = getattr(metrics, "accumulated_usage", None)
            if acc and isinstance(acc, dict):
                usage = acc
            else:
                # Fallback: report cycle count and tool call count
                usage = {
                    "cycle_count": getattr(metrics, "cycle_count", 0),
                    "tools_called": len(tools_called),
                }
    except Exception:
        pass

    yield ResultMessage(result=result_text, usage=usage)


async def sdk_query_streaming(
    prompt: str,
    tenant_id: str = "demo-tenant",
    user_id: str = "demo-user",
    tier: str = "advanced",
    skill_names: list[str] | None = None,
    session_id: str | None = None,
    workspace_id: str | None = None,
    package_context: Any = None,
    max_turns: int = 15,
    messages: list[dict] | None = None,
    username: str | None = None,
    tags: list[str] | None = None,
) -> AsyncGenerator[dict, None]:
    """Stream text deltas from the Strands supervisor agent.

    Unlike sdk_query() which waits for the full response, this yields
    {"type": "text", "data": "..."} chunks as they arrive from Bedrock
    ConverseStream, plus a final {"type": "complete", ...} event.

    Uses Agent.stream_async() which handles the sync→async bridge
    internally. Factory tools push results via an asyncio.Queue that
    is drained between stream events.
    """
    fast_path = await _maybe_fast_path_document_generation(
        prompt=prompt,
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        package_context=package_context,
    )
    if fast_path is not None:
        result = fast_path["result"]
        if fast_path.get("guardrail"):
            yield {"type": "text", "data": result["message"]}
            yield {"type": "complete", "text": result["message"], "tools_called": [], "usage": {}}
            return
        if "error" in result:
            yield {"type": "error", "error": result["error"]}
            return
        yield {"type": "tool_use", "name": "create_document"}
        yield {"type": "tool_result", "name": "create_document", "result": result}
        # Emit package state update for fast-path document creation
        for state_evt in _build_state_updates(result, "create_document", tenant_id):
            yield state_evt
        text = (
            f"Generated a draft {fast_path['doc_type'].replace('_', ' ')} document. "
            "Open the document card to review or edit it."
        )
        yield {"type": "text", "data": text}
        # End-of-turn state refresh for fast-path
        for state_evt in _build_end_of_turn_state(package_context, tenant_id):
            yield state_evt
        yield {
            "type": "complete",
            "text": text,
            "tools_called": ["create_document"],
            "usage": {"tools_called": 1, "tools": ["create_document"], "fast_path": True},
        }
        return

    # Resolve workspace
    resolved_workspace_id = workspace_id
    if not resolved_workspace_id:
        try:
            from .workspace_store import get_or_create_default
            ws = get_or_create_default(tenant_id, user_id)
            resolved_workspace_id = ws.get("workspace_id")
        except Exception as exc:
            logger.warning("workspace_store.get_or_create_default failed: %s", exc)

    # --- stream_async() approach: SDK handles sync→async bridge ---
    # result_queue is still used by factory tools to push tool_result events.
    # These are drained between stream events in the main async for loop.

    result_queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    # Fire preload concurrently with sync tool-building
    from .session_preloader import preload_session_context, format_context_for_prompt
    _pkg_id = package_context.package_id if package_context and package_context.is_package_mode else None
    _preload_task = asyncio.create_task(
        preload_session_context(tenant_id, user_id, package_id=_pkg_id),
    )

    skill_tools = build_skill_tools(
        tier=tier,
        skill_names=skill_names,
        tenant_id=tenant_id,
        user_id=user_id,
        workspace_id=resolved_workspace_id,
        session_id=session_id or "",
        result_queue=result_queue,
        loop=loop,
    )

    # Build service tools (S3, DynamoDB, create_document, search_far, etc.)
    service_tools = _build_service_tools(
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        prompt_context=prompt,
        package_context=package_context,
        result_queue=result_queue,
        loop=loop,
    )

    preloaded_ctx = await _preload_task
    _ctx_str = format_context_for_prompt(preloaded_ctx)

    system_prompt = build_supervisor_prompt(
        tenant_id=tenant_id,
        user_id=user_id,
        tier=tier,
        agent_names=[t.__name__ for t in skill_tools],
        workspace_id=resolved_workspace_id,
        preloaded_context=_ctx_str or None,
    )

    strands_history = _to_strands_messages(messages) if messages else None

    _ensure_langfuse_exporter()
    supervisor = Agent(
        model=_model,
        system_prompt=system_prompt,
        tools=skill_tools + service_tools,
        callback_handler=None,  # stream_async yields events directly
        messages=strands_history,
        trace_attributes=_build_trace_attrs(
            tenant_id=tenant_id,
            user_id=user_id,
            tier=tier,
            session_id=session_id or "",
            username=username or "",
            eval_tags=tags,
        ),
    )

    # Yield chunks via stream_async — SDK bridges sync→async internally
    import time as _time
    _agent_start = _time.perf_counter()
    full_text_parts: list[str] = []
    tools_called: list[str] = []
    _current_tool_id: str | None = None
    error_holder: list[Exception] = []
    agent_result = None

    def _drain_tool_results() -> list[dict]:
        """Drain events pushed by factory tools / subagent callbacks via result_queue."""
        drained: list[dict] = []
        while True:
            try:
                item = result_queue.get_nowait()
                # Items with a name are tool events — track them
                name = item.get("name")
                if name:
                    tools_called.append(name)
                # Forward all items (tool_use, tool_result, agent_status, reasoning, etc.)
                drained.append(item)
            except asyncio.QueueEmpty:
                break
        return drained

    try:
        # Use a polling loop so we can drain result_queue every 0.5s
        # even while stream_async is blocked (e.g., during subagent execution).
        # This makes subagent internal events appear in real-time.
        _stream_iter = supervisor.stream_async(prompt).__aiter__()
        _pending_next: asyncio.Task | None = None
        _stream_done = False

        while not _stream_done:
            if _pending_next is None:
                _pending_next = asyncio.ensure_future(_stream_iter.__anext__())

            done, _ = await asyncio.wait({_pending_next}, timeout=0.5)

            # Always drain queue (subagent callback events may have arrived)
            for tool_result_chunk in _drain_tool_results():
                yield tool_result_chunk

            if not done:
                continue  # Timeout — loop back to drain again

            try:
                event = _pending_next.result()
            except StopAsyncIteration:
                _stream_done = True
                break
            _pending_next = None

            # --- Reasoning / extended thinking ---
            raw_event = event.get("event", {})
            if isinstance(raw_event, dict):
                delta = raw_event.get("contentBlockDelta", {}).get("delta", {})
                reasoning_text = delta.get("reasoningContent", {}).get("text", "")
                if reasoning_text:
                    yield {"type": "reasoning", "data": reasoning_text}
                    continue

            # --- Text streaming ---
            data = event.get("data")
            if data and isinstance(data, str):
                full_text_parts.append(data)
                yield {"type": "text", "data": data}
                continue

            # --- Tool use start ---
            # Emit immediately for fast UX. Input is empty at this
            # point (Strands hasn't finished streaming it). The real
            # input arrives later via tool_input events pushed by the
            # tool functions themselves through result_queue.
            current_tool = event.get("current_tool_use")
            if current_tool and isinstance(current_tool, dict):
                tool_id = current_tool.get("toolUseId", "")
                if tool_id and tool_id != _current_tool_id:
                    _current_tool_id = tool_id
                    tool_name = current_tool.get("name", "")
                    tools_called.append(tool_name)
                    from .telemetry.status_messages import (
                        is_subagent_tool, get_tool_status_message,
                    )
                    if is_subagent_tool(tool_name):
                        display = tool_name.replace("_", " ").title()
                        yield {
                            "type": "handoff",
                            "target": tool_name,
                            "reason": f"Delegating to {display}",
                        }
                    yield {
                        "type": "tool_use",
                        "name": tool_name,
                        "input": {},
                        "tool_use_id": tool_id,
                    }
                    status_msg = get_tool_status_message(tool_name, {})
                    yield {
                        "type": "agent_status",
                        "status": status_msg,
                        "detail": tool_name,
                    }
                continue

            # --- Bedrock contentBlockStart fallback ---
            cbs_event = event.get("event", {})
            if isinstance(cbs_event, dict):
                cbs_tool = (
                    cbs_event
                    .get("contentBlockStart", {})
                    .get("start", {})
                    .get("toolUse")
                )
                if cbs_tool:
                    tool_id = cbs_tool.get("toolUseId", "")
                    if tool_id != _current_tool_id:
                        _current_tool_id = tool_id
                        tool_name = cbs_tool.get("name", "")
                        tools_called.append(tool_name)
                        from .telemetry.status_messages import (
                            is_subagent_tool, get_tool_status_message,
                        )
                        if is_subagent_tool(tool_name):
                            display = tool_name.replace("_", " ").title()
                            yield {
                                "type": "handoff",
                                "target": tool_name,
                                "reason": f"Delegating to {display}",
                            }
                        yield {
                            "type": "tool_use",
                            "name": tool_name,
                            "input": {},
                            "tool_use_id": tool_id,
                        }
                        status_msg = get_tool_status_message(tool_name, {})
                        yield {
                            "type": "agent_status",
                            "status": status_msg,
                            "detail": tool_name,
                        }
                    continue

            # --- Agent result (final event) ---
            if "result" in event and hasattr(event.get("result"), "metrics"):
                agent_result = event["result"]

    except Exception as exc:
        error_holder.append(exc)
        logger.error("stream_async error: %s", exc)
        # Classify and tag the Langfuse trace for filtering
        from .telemetry.langfuse_client import notify_trace_error
        notify_trace_error(session_id or "", str(exc))

    # Final drain of any remaining tool results
    for tool_result_chunk in _drain_tool_results():
        yield tool_result_chunk

    # Extract usage from result
    usage = {}
    if agent_result is not None:
        if not full_text_parts:
            try:
                final_text = str(agent_result)
                if final_text:
                    full_text_parts.append(final_text)
                    yield {"type": "text", "data": final_text}
            except Exception:
                pass
        try:
            metrics = getattr(agent_result, "metrics", None)
            if metrics:
                acc = getattr(metrics, "accumulated_usage", None)
                if acc and isinstance(acc, dict):
                    usage = acc
                else:
                    usage = {
                        "cycle_count": getattr(metrics, "cycle_count", 0),
                        "tools_called": len(tools_called),
                    }
                if hasattr(metrics, "tool_metrics"):
                    tools_called = list(metrics.tool_metrics.keys())
        except Exception:
            pass

    forced_doc = None
    if not error_holder:
        forced_doc = await _ensure_create_document_for_direct_request(
            prompt=prompt,
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            package_context=package_context,
            tools_called=tools_called,
        )
        if forced_doc is not None:
            tools_called.append("create_document")
            yield {"type": "tool_use", "name": "create_document"}
            yield {"type": "tool_result", "name": "create_document", "result": forced_doc["result"]}
            # Emit package state update for forced document creation
            for state_evt in _build_state_updates(forced_doc["result"], "create_document", tenant_id):
                yield state_evt
            if not full_text_parts:
                summary = (
                    f"Generated a draft {forced_doc['doc_type'].replace('_', ' ')} document. "
                    "Open the document card to review or edit it."
                )
                full_text_parts.append(summary)
                yield {"type": "text", "data": summary}

    # Explicitly register sessionId (and tags) in Langfuse via REST API
    if session_id and supervisor.trace_span:
        try:
            from opentelemetry.trace import format_trace_id
            span_ctx = supervisor.trace_span.get_span_context()
            if span_ctx and span_ctx.is_valid:
                asyncio.ensure_future(
                    _langfuse_set_session(
                        format_trace_id(span_ctx.trace_id),
                        session_id,
                        user_id=user_id,
                        tags=tags,
                    )
                )
        except Exception:
            pass

    # Emit agent.timing telemetry to CloudWatch
    _agent_duration_ms = int((_time.perf_counter() - _agent_start) * 1000)
    try:
        from .telemetry.cloudwatch_emitter import emit_telemetry_event
        emit_telemetry_event(
            event_type="agent.timing",
            tenant_id=tenant_id,
            data={
                "agent_name": "supervisor",
                "duration_ms": _agent_duration_ms,
                "tools_called": tools_called,
                "session_id": session_id or "",
            },
            session_id=session_id,
            user_id=user_id,
        )
    except Exception:
        logger.debug("Failed to emit agent.timing telemetry", exc_info=True)

    # End-of-turn state refresh — always emit latest package state
    for state_evt in _build_end_of_turn_state(package_context, tenant_id):
        yield state_evt

    if error_holder:
        yield {"type": "error", "error": str(error_holder[0])}
    else:
        final_text = "".join(full_text_parts)
        if not final_text.strip():
            called = ", ".join(tools_called[:3]) if tools_called else "none"
            final_text = (
                "I completed the tool steps but did not receive a final answer text. "
                f"Tools called: {called}. Please retry your request."
            )
        yield {
            "type": "complete",
            "text": final_text,
            "tools_called": tools_called,
            "usage": usage,
        }


async def sdk_query_single_skill(
    prompt: str,
    skill_name: str,
    tenant_id: str = "demo-tenant",
    user_id: str = "demo-user",
    tier: str = "advanced",
    model: str = None,
    max_turns: int = 5,
) -> AsyncGenerator[Any, None]:
    """Run a query directly against a single skill (no supervisor).

    Same signature as sdk_agentic_service.sdk_query_single_skill().
    Direct Agent call with skill content as system_prompt.

    Args:
        prompt: User's query
        skill_name: Skill key from SKILL_CONSTANTS
        tenant_id: Tenant identifier
        user_id: User identifier
        tier: Subscription tier
        model: Model override (unused -- shared model)
        max_turns: Max tool-use iterations (reserved)

    Yields:
        AssistantMessage and ResultMessage adapter objects
    """
    skill_key = SKILL_AGENT_REGISTRY.get(skill_name, {}).get("skill_key", skill_name)
    entry = PLUGIN_CONTENTS.get(skill_key)
    if not entry:
        raise ValueError(f"Skill not found: {skill_name} (key={skill_key})")
    skill_content = entry["body"]

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S UTC")
    tenant_context = (
        f"Tenant: {tenant_id} | User: {user_id} | Tier: {tier} | Current datetime: {now_utc}\n"
        f"You are operating as the {skill_name} specialist for this tenant.\n\n"
    )

    _ensure_langfuse_exporter()
    agent = Agent(
        model=_model,
        system_prompt=tenant_context + skill_content,
        callback_handler=None,
        trace_attributes=_build_trace_attrs(
            tenant_id=tenant_id,
            user_id=user_id,
            tier=tier,
            subagent=skill_name,
        ),
    )

    result = agent(prompt)
    result_text = str(result)

    yield AssistantMessage(content=[TextBlock(text=result_text)])

    usage = {}
    try:
        metrics = getattr(result, "metrics", None)
        if metrics:
            acc = getattr(metrics, "accumulated_usage", None)
            if acc and isinstance(acc, dict):
                usage = acc
            else:
                usage = {"cycle_count": getattr(metrics, "cycle_count", 0)}
    except Exception:
        pass

    yield ResultMessage(result=result_text, usage=usage)
