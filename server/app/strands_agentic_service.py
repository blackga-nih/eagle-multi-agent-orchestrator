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
import queue
import re
import sys
import threading
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator

from strands import Agent, tool
from strands.models import BedrockModel

# Add server/ to path for eagle_skill_constants
_server_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)

from eagle_skill_constants import SKILL_CONSTANTS, AGENTS, SKILLS, PLUGIN_CONTENTS
from .tools.knowledge_tools import KNOWLEDGE_FETCH_TOOL, KNOWLEDGE_SEARCH_TOOL

logger = logging.getLogger("eagle.strands_agent")


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


# -- Streaming Callback Handler ----------------------------------------

_SENTINEL = object()  # Signals end of stream


class QueueCallbackHandler:
    """Strands callback handler that pushes text deltas into a thread-safe queue.

    Used by sdk_query_streaming() to yield tokens as they arrive from Bedrock
    ConverseStream, instead of waiting for the full agent response.
    """

    def __init__(self, chunk_queue: queue.Queue):
        self._queue = chunk_queue
        self.tool_count = 0

    def __call__(self, **kwargs: Any) -> None:
        data = kwargs.get("data", "")
        complete = kwargs.get("complete", False)
        tool_use = kwargs.get("event", {}).get("contentBlockStart", {}).get("start", {}).get("toolUse")

        if data:
            self._queue.put({"type": "text", "data": data})

        if tool_use:
            self.tool_count += 1
            self._queue.put({"type": "tool_use", "name": tool_use.get("name", "")})

        if complete and not data:
            # Stream finished — don't send sentinel here, let the caller handle it
            pass


# -- Model Selection -------------------------------------------------
# If EAGLE_BEDROCK_MODEL_ID is explicitly set, use it.
# Otherwise, default to Sonnet 4.6 on the NCI account (695681773636)
# and Haiku 4.5 on any other account (personal dev, CI, etc.).

_NCI_ACCOUNT = "695681773636"
_SONNET = "us.anthropic.claude-sonnet-4-6"
_HAIKU = "us.anthropic.claude-haiku-4-5-20251001-v1:0"


def _default_model() -> str:
    if os.getenv("EAGLE_BEDROCK_MODEL_ID"):
        return os.getenv("EAGLE_BEDROCK_MODEL_ID")
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

_model = BedrockModel(
    model_id=MODEL,
    region_name=os.getenv("AWS_REGION", "us-east-1"),
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
    ("igce", ["igce", "independent government cost estimate", "cost estimate"]),
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
_SLOW_PATH_HINTS = ("research", "far", "dfars", "policy", "compare", "analyze")
_DOC_REQUEST_BLOCKERS = (
    "what is",
    "what's",
    "how do i",
    "how to",
    "explain",
    "difference between",
)


def _normalize_prompt(prompt: str) -> str:
    return re.sub(r"\s+", " ", prompt.strip().lower())


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
    if any(h in lowered for h in _SLOW_PATH_HINTS):
        return False, None
    return True, doc_type


def _fast_path_title(prompt: str, doc_type: str) -> str:
    return _DOC_TYPE_LABELS.get(doc_type, doc_type.replace("_", " ").title())


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

    from .agentic_service import _exec_create_document

    params: dict[str, Any] = {
        "doc_type": doc_type,
        "title": _fast_path_title(prompt, doc_type),
    }
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

    params: dict[str, Any] = {
        "doc_type": doc_type,
        "title": _fast_path_title(prompt, doc_type),
    }
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
    KNOWLEDGE_SEARCH_TOOL,
    KNOWLEDGE_FETCH_TOOL,
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
]

# Max prompt size per subagent to avoid context overflow
MAX_SKILL_PROMPT_CHARS = 4000


# -- Skill -> @tool Registry (built from plugin metadata) ------------

_PLUGIN_JSON_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "eagle-plugin", "plugin.json"
)


def _load_plugin_config() -> dict:
    """Load plugin manifest -- prefers DynamoDB PLUGIN#manifest, falls back to bundled file."""
    try:
        from .plugin_store import get_plugin_manifest
        manifest = get_plugin_manifest()
        if manifest:
            return manifest
    except Exception:
        pass

    try:
        with open(_PLUGIN_JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


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

def _make_subagent_tool(skill_name: str, description: str, prompt_body: str):
    """Create a @tool-wrapped subagent from skill registry entry.

    Each invocation constructs a fresh Agent with the resolved prompt.
    The shared _model is reused (no per-request boto3 overhead).
    """
    safe_name = skill_name.replace("-", "_")

    @tool(name=safe_name)
    def subagent_tool(query: str) -> str:
        """Placeholder docstring replaced below."""
        agent = Agent(
            model=_model,
            system_prompt=prompt_body,
            callback_handler=None,
        )
        return str(agent(query))

    # Override docstring (required for Strands schema extraction)
    subagent_tool.__doc__ = (
        f"{description}\n\n"
        f"Args:\n"
        f"    query: The question or task for this specialist"
    )
    return subagent_tool



# -- Compliance Matrix @tool (available to all agents) ----------------

@tool(name="query_compliance_matrix")
def _compliance_matrix_tool(params: str) -> str:
    """Query NCI/NIH contract requirements decision tree. Pass a JSON string with keys: operation (required), contract_value, acquisition_method, contract_type, is_it, is_small_business, is_rd, is_human_subjects, is_services, keyword. Operations: query, list_methods, list_types, list_thresholds, search_far, suggest_vehicle.

    Args:
        params: JSON string, e.g. {"operation":"query","contract_value":85000,"acquisition_method":"sap","contract_type":"ffp","is_services":true}
    """
    from .compliance_matrix import execute_operation

    parsed = json.loads(params) if isinstance(params, str) else params
    result = execute_operation(parsed)
    return json.dumps(result, indent=2, default=str)


# -- AWS Service @tools (S3, DynamoDB, CloudWatch, Documents) ----------
# These call the handlers in agentic_service.py directly with the real
# tenant_id and session_id from the authenticated context — bypassing
# execute_tool() which has stub _extract_tenant_id/_extract_user_id.

def _make_service_tool(
    tool_name: str,
    description: str,
    tenant_id: str,
    user_id: str,
    session_id: str | None,
    package_context: Any = None,
    result_queue: asyncio.Queue | None = None,
    loop: asyncio.AbstractEventLoop | None = None,
):
    """Create a Strands @tool that calls agentic_service handlers directly.

    The handler receives the real tenant_id (from Cognito auth) and a
    composite session_id (tenant-tier-user-session) for per-user S3 scoping.

    If result_queue and loop are provided, tool results for create_document
    are emitted as tool_result chunks so the frontend can render document cards.
    """
    from .agentic_service import TOOL_DISPATCH, TOOLS_NEEDING_SESSION

    handler = TOOL_DISPATCH.get(tool_name)
    if not handler:
        raise ValueError(f"No handler for tool: {tool_name}")

    # Ensure legacy handlers receive a composite session id format:
    # {tenant_id}#{tier}#{user_id}#{session}
    # This preserves per-user S3 scoping and avoids demo-user fallback.
    scoped_session_id = session_id
    if not scoped_session_id or "#" not in scoped_session_id:
        scoped_session_id = f"{tenant_id}#advanced#{user_id}#{session_id or ''}"

    @tool(name=tool_name)
    def service_tool(params: str) -> str:
        """Placeholder docstring replaced below."""
        parsed = json.loads(params) if isinstance(params, str) else params
        try:
            if (
                tool_name == "create_document"
                and package_context is not None
                and getattr(package_context, "is_package_mode", False)
                and getattr(package_context, "package_id", None)
            ):
                parsed.setdefault("package_id", package_context.package_id)

            if tool_name in TOOLS_NEEDING_SESSION:
                result = handler(parsed, tenant_id, scoped_session_id)
            else:
                result = handler(parsed, tenant_id)

            # Emit tool_result for create_document so frontend renders DocumentCard
            # Only emit for successful results (not error responses)
            if tool_name == "create_document" and result_queue and loop and "error" not in result:
                loop.call_soon_threadsafe(
                    result_queue.put_nowait,
                    {"type": "tool_result", "name": tool_name, "result": result},
                )

            return json.dumps(result, indent=2, default=str)
        except Exception as exc:
            logger.error("Service tool %s failed: %s", tool_name, exc, exc_info=True)
            return json.dumps({"error": str(exc), "tool": tool_name})

    service_tool.__doc__ = (
        f"{description}\n\n"
        f"Args:\n"
        f"    params: JSON string with operation and operation-specific fields"
    )
    return service_tool


# Tool definitions: name -> description (schemas are in EAGLE_TOOLS above)
_SERVICE_TOOL_DEFS = {
    "s3_document_ops": (
        "Read, write, or list documents in S3 scoped per-tenant. "
        "Operations: list, read, write. Pass JSON with 'operation' and optional 'key', 'content'."
    ),
    "dynamodb_intake": (
        "Create, read, update, list, or query intake records in DynamoDB. "
        "Operations: create, read, update, list, query. Pass JSON with 'operation' and optional 'item_id', 'data'."
    ),
    "create_document": (
        "Generate acquisition documents (SOW, IGCE, Market Research, J&A, Acquisition Plan, "
        "Eval Criteria, Security Checklist, Section 508, COR Certification, Contract Type Justification). "
        "Documents are saved to S3. Pass JSON with 'doc_type', 'title', and optional 'data'."
    ),
    "get_intake_status": (
        "Get the current intake package status and completeness — shows which documents exist, "
        "which are missing, and next actions. Pass JSON with optional 'intake_id'."
    ),
    "intake_workflow": (
        "Manage the acquisition intake workflow: start, advance, status, complete, reset. "
        "Pass JSON with 'action' and optional 'intake_id', 'data'."
    ),
    "search_far": (
        "Search the FAR and DFARS for clauses, requirements, and guidance. "
        "Pass JSON with 'query' and optional 'parts' array."
    ),
    "knowledge_search": (
        "Search the acquisition knowledge base metadata in DynamoDB. "
        "Pass JSON with optional fields: topic, document_type, agent, authority_level, keywords, limit."
    ),
    "knowledge_fetch": (
        "Fetch full knowledge document content from S3. "
        "Pass JSON with s3_key (or document_id)."
    ),
    "manage_skills": (
        "Create, list, update, delete, or publish custom skills. "
        "Pass JSON: {action, skill_id?, name?, display_name?, description?, prompt_body?, triggers?, tools?, model?, visibility?}. "
        "Actions: list, get, create, update, delete, submit, publish, disable."
    ),
    "manage_prompts": (
        "List, view, set, or delete agent prompt overrides. "
        "Pass JSON: {action, agent_name?, prompt_body?, is_append?}. "
        "Actions: list, get, set, delete, resolve."
    ),
    "manage_templates": (
        "List, view, set, or delete document templates. "
        "Pass JSON: {action, doc_type?, template_body?, display_name?, user_id?}. "
        "Actions: list, get, set, delete, resolve."
    ),
}


def _build_service_tools(
    tenant_id: str,
    user_id: str,
    session_id: str | None,
    package_context: Any = None,
    result_queue: asyncio.Queue | None = None,
    loop: asyncio.AbstractEventLoop | None = None,
) -> list:
    """Build @tool wrappers for AWS service tools, scoped to the current tenant/user/session."""
    tools = []
    for name, desc in _SERVICE_TOOL_DEFS.items():
        tools.append(
            _make_service_tool(
                name,
                desc,
                tenant_id,
                user_id,
                session_id,
                package_context,
                result_queue,
                loop,
            )
        )
    return tools


# -- build_skill_tools() ---------------------------------------------

def build_skill_tools(
    tier: str = "advanced",
    skill_names: list[str] | None = None,
    tenant_id: str = "demo-tenant",
    user_id: str = "demo-user",
    workspace_id: str | None = None,
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

        tools.append(_make_subagent_tool(
            skill_name=name,
            description=meta["description"],
            prompt_body=_truncate_skill(prompt_body),
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
            ))
    except Exception as exc:
        logger.warning("skill_store.list_active_skills failed for %s: %s -- skipping user skills", tenant_id, exc)

    return tools


# -- Supervisor Prompt -----------------------------------------------

def build_supervisor_prompt(
    tenant_id: str = "demo-tenant",
    user_id: str = "demo-user",
    tier: str = "advanced",
    agent_names: list[str] | None = None,
    workspace_id: str | None = None,
) -> str:
    """Build the supervisor system prompt with available subagent descriptions.

    Loads the base supervisor prompt from the 4-layer resolution chain when
    workspace_id is provided; otherwise falls back to AGENTS bundled content.
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
        f"Tenant: {tenant_id} | User: {user_id} | Tier: {tier}\n\n"
        f"{base_prompt}\n\n"
        f"--- ACTIVE SPECIALISTS ---\n"
        f"Available specialists for delegation:\n{agent_list}\n\n"
        "KB Retrieval Rules:\n"
        "1) For policy/regulation/procedure/template questions, call knowledge_search first.\n"
        "2) If search returns results, call knowledge_fetch on the top 1-3 relevant docs.\n"
        "3) In final answer, include a Sources section with title + s3_key.\n"
        "4) If no results, explicitly say no KB match and ask a refinement question.\n"
        "5) Prefer knowledge_search/knowledge_fetch over search_far when KB can answer.\n"
        "6) Use search_far only as fallback reference.\n\n"
        "Document Output Rules:\n"
        "1) If the user asks to generate/draft/create a document, you MUST call create_document.\n"
        "2) Do not paste full document bodies in chat unless the user explicitly asks for inline text.\n"
        "3) After create_document, respond briefly and direct the user to open/edit the document card.\n\n"
        f"IMPORTANT: Use the available tool functions to delegate to specialists. "
        f"Include relevant context in the query you pass to each specialist. "
        f"Do not try to answer specialized questions yourself -- delegate to the expert."
    )


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

    skill_tools = build_skill_tools(
        tier=tier,
        skill_names=skill_names,
        tenant_id=tenant_id,
        user_id=user_id,
        workspace_id=resolved_workspace_id,
    )

    # Build service tools (S3, DynamoDB, create_document, search_far, etc.)
    service_tools = _build_service_tools(
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        package_context=package_context,
    )

    system_prompt = build_supervisor_prompt(
        tenant_id=tenant_id,
        user_id=user_id,
        tier=tier,
        agent_names=[t.__name__ for t in skill_tools],
        workspace_id=resolved_workspace_id,
    )

    # Convert conversation history to Strands format (excludes current prompt)
    strands_history = _to_strands_messages(messages) if messages else None

    supervisor = Agent(
        model=_model,
        system_prompt=system_prompt,
        tools=skill_tools + service_tools,
        callback_handler=None,
        messages=strands_history,
    )

    # Synchronous call -- Strands handles the agentic loop internally
    result = supervisor(prompt)
    result_text = str(result)

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
) -> AsyncGenerator[dict, None]:
    """Stream text deltas from the Strands supervisor agent.

    Unlike sdk_query() which waits for the full response, this yields
    {"type": "text", "data": "..."} chunks as they arrive from Bedrock
    ConverseStream, plus a final {"type": "complete", ...} event.

    Runs the synchronous Strands Agent in a background thread and bridges
    to async via a queue.
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
        if "error" in result:
            yield {"type": "error", "error": result["error"]}
            return
        yield {"type": "tool_use", "name": "create_document"}
        yield {"type": "tool_result", "name": "create_document", "result": result}
        text = (
            f"Generated a draft {fast_path['doc_type'].replace('_', ' ')} document. "
            "Open the document card to review or edit it."
        )
        yield {"type": "text", "data": text}
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

    skill_tools = build_skill_tools(
        tier=tier,
        skill_names=skill_names,
        tenant_id=tenant_id,
        user_id=user_id,
        workspace_id=resolved_workspace_id,
    )

    # Build service tools (S3, DynamoDB, create_document, search_far, etc.)
    # Pass an async result queue so create_document can emit tool_result chunks.
    result_queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()
    service_tools = _build_service_tools(
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        package_context=package_context,
        result_queue=result_queue,
        loop=loop,
    )

    system_prompt = build_supervisor_prompt(
        tenant_id=tenant_id,
        user_id=user_id,
        tier=tier,
        agent_names=[t.__name__ for t in skill_tools],
        workspace_id=resolved_workspace_id,
    )

    strands_history = _to_strands_messages(messages) if messages else None
    chunk_queue: queue.Queue = queue.Queue()

    handler = QueueCallbackHandler(chunk_queue)

    supervisor = Agent(
        model=_model,
        system_prompt=system_prompt,
        tools=skill_tools + service_tools,
        callback_handler=handler,
        messages=strands_history,
    )

    # Run synchronous Strands agent in a background thread
    result_holder: list = []
    error_holder: list = []

    def _run_agent():
        try:
            result = supervisor(prompt)
            result_holder.append(result)
        except Exception as exc:
            error_holder.append(exc)
        finally:
            chunk_queue.put(_SENTINEL)

    thread = threading.Thread(target=_run_agent, daemon=True)
    thread.start()

    # Yield chunks as they arrive from the callback handler
    full_text_parts: list[str] = []
    tools_called: list[str] = []

    def _drain_tool_results() -> list[dict]:
        drained: list[dict] = []
        while True:
            try:
                item = result_queue.get_nowait()
                name = item.get("name")
                if name:
                    tools_called.append(name)
                drained.append(item)
            except asyncio.QueueEmpty:
                break
        return drained

    while True:
        for tool_result_chunk in _drain_tool_results():
            yield tool_result_chunk

        try:
            # Poll queue with short timeout to stay async-friendly
            chunk = await asyncio.to_thread(chunk_queue.get, timeout=0.1)
        except Exception:
            # queue.Empty on timeout — check if thread is still alive
            if not thread.is_alive():
                break
            continue

        if chunk is _SENTINEL:
            break

        if chunk.get("type") == "text":
            full_text_parts.append(chunk["data"])
            yield chunk
        elif chunk.get("type") == "tool_use":
            tools_called.append(chunk.get("name", ""))
            yield chunk

        for tool_result_chunk in _drain_tool_results():
            yield tool_result_chunk

    # Wait for thread to finish
    thread.join(timeout=5)
    for tool_result_chunk in _drain_tool_results():
        yield tool_result_chunk

    # Extract usage from result
    usage = {}
    if result_holder:
        result = result_holder[0]
        if not full_text_parts:
            # Some Strands responses may not emit token deltas through callback_handler.
            # Fall back to the final rendered result text so streaming clients still
            # receive assistant content before COMPLETE.
            try:
                final_text = str(result)
                if final_text:
                    full_text_parts.append(final_text)
                    # Yield as text event so SSE consumers receive it before COMPLETE
                    yield {"type": "text", "data": final_text}
            except Exception:
                pass
        try:
            metrics = getattr(result, "metrics", None)
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
            if not full_text_parts:
                summary = (
                    f"Generated a draft {forced_doc['doc_type'].replace('_', ' ')} document. "
                    "Open the document card to review or edit it."
                )
                full_text_parts.append(summary)
                yield {"type": "text", "data": summary}

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

    tenant_context = (
        f"Tenant: {tenant_id} | User: {user_id} | Tier: {tier}\n"
        f"You are operating as the {skill_name} specialist for this tenant.\n\n"
    )

    agent = Agent(
        model=_model,
        system_prompt=tenant_context + skill_content,
        callback_handler=None,
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
