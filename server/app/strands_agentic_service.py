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
import threading
import time as _time
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator

from strands import Agent, tool
from strands.models import BedrockModel

# Add server/ to path for eagle_skill_constants
_server_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)

from eagle_skill_constants import AGENTS, SKILLS, PLUGIN_CONTENTS

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
    """Strands callback handler that pushes text deltas and tool_use events into an async queue.

    Bedrock ConverseStream sends tool input across multiple events:
      - contentBlockStart  → toolUse.name + toolUse.toolUseId  (block begins)
      - contentBlockDelta  → toolUse.input  (JSON string fragments, streamed)
      - contentBlockStop   → (block ends — we emit the assembled tool_use event here)

    Text deltas arrive via the ``data`` kwarg and are emitted immediately.
    Tool input is accumulated in ``_pending_tool`` and flushed at contentBlockStop.

    Uses ``loop.call_soon_threadsafe`` to put items onto an ``asyncio.Queue``
    from the background Strands thread — instant delivery, no polling.
    """

    def __init__(self, async_queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
        self._queue = async_queue
        self._loop = loop
        self.tool_count = 0
        # Accumulator for in-flight tool block
        self._pending_tool: dict | None = None   # {"name": str, "id": str, "input_parts": list[str]}

    def _put(self, item: dict) -> None:
        """Thread-safe put into asyncio.Queue."""
        self._loop.call_soon_threadsafe(self._queue.put_nowait, item)

    def __call__(self, **kwargs: Any) -> None:
        event = kwargs.get("event", {})
        data = kwargs.get("data", "")

        # Text delta — emit immediately
        if data:
            self._put({"type": "text", "data": data})

        # contentBlockStart — a new content block (tool or text) is opening
        content_block_start = event.get("contentBlockStart", {})
        if content_block_start:
            tool_use_start = content_block_start.get("start", {}).get("toolUse")
            if tool_use_start:
                self._pending_tool = {
                    "name": tool_use_start.get("name", ""),
                    "id": tool_use_start.get("toolUseId", ""),
                    "input_parts": [],
                }

        # contentBlockDelta — JSON input fragment for the current tool block
        content_block_delta = event.get("contentBlockDelta", {})
        if content_block_delta and self._pending_tool is not None:
            delta_tool_use = content_block_delta.get("delta", {}).get("toolUse", {})
            fragment = delta_tool_use.get("input", "")
            if fragment:
                self._pending_tool["input_parts"].append(fragment)

        # contentBlockStop — tool block is complete; assemble and emit
        if "contentBlockStop" in event and self._pending_tool is not None:
            tool_name = self._pending_tool["name"]
            tool_id = self._pending_tool["id"]
            raw_input = "".join(self._pending_tool["input_parts"])

            parsed_input: dict = {}
            if raw_input:
                try:
                    parsed_input = json.loads(raw_input)
                except json.JSONDecodeError:
                    parsed_input = {"_raw": raw_input}

            self.tool_count += 1
            self._put({
                "type": "tool_use",
                "name": tool_name,
                "tool_use_id": tool_id,
                "input": parsed_input,
            })
            self._pending_tool = None


# -- Shared Model (module-level) -------------------------------------
# Created once at import time. Reused across all requests.
# boto3 handles SSO/IAM natively — no credential bridging needed.

_model = BedrockModel(
    model_id=os.getenv("EAGLE_BEDROCK_MODEL_ID", "us.amazon.nova-pro-v1:0"),
    region_name=os.getenv("AWS_REGION", "us-east-1"),
)


# -- Configuration ---------------------------------------------------

MODEL = os.getenv("EAGLE_BEDROCK_MODEL_ID", "us.amazon.nova-pro-v1:0")

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

# -- Trivial Message Fast-Path ------------------------------------------
# Regex matches greetings, acknowledgments, and simple conversational
# messages that don't need the full supervisor+tools pipeline.
_TRIVIAL_RE = re.compile(
    r"^(hi|hello|hey|howdy|good\s+(morning|afternoon|evening|day)|"
    r"thanks?|thank\s+you|thx|ok|okay|yes|no|sure|bye|goodbye|"
    r"what('?s)?\s+up|how\s+are\s+you|nice|great|cool|got\s+it|"
    r"sounds?\s+good|will\s+do|roger|acknowledged?|understood|yo|sup)[\s!?.]*$",
    re.IGNORECASE,
)

_TRIVIAL_SYSTEM_PROMPT = (
    "You are the EAGLE Acquisition Assistant for the NCI Office of Acquisitions. "
    "Respond to this greeting or conversational message with a brief, friendly reply. "
    "Keep it to 1-2 sentences. Be warm and professional. "
    "If the user seems to need help, mention you can assist with acquisition documents, "
    "FAR/DFARS guidance, and procurement workflows."
)


def _is_trivial_message(prompt: str) -> bool:
    """Return True if the message is a simple greeting/acknowledgment."""
    return bool(_TRIVIAL_RE.match(prompt.strip()))


# -- Supervisor Prompt Cache (60s TTL) ----------------------------------
_supervisor_prompt_cache: dict[str, dict] = {}
_SUPERVISOR_PROMPT_CACHE_TTL = 60


def _sup_cache_key(tenant_id: str, user_id: str, tier: str, workspace_id: str | None, agent_key: str) -> str:
    return f"{tenant_id}#{user_id}#{tier}#{workspace_id or 'none'}#{agent_key}"


def _sup_cache_get(tenant_id: str, user_id: str, tier: str, workspace_id: str | None, agent_key: str) -> str | None:
    key = _sup_cache_key(tenant_id, user_id, tier, workspace_id, agent_key)
    entry = _supervisor_prompt_cache.get(key)
    if entry and _time.time() < entry["ts"] + _SUPERVISOR_PROMPT_CACHE_TTL:
        return entry["prompt"]
    return None


def _sup_cache_set(tenant_id: str, user_id: str, tier: str, workspace_id: str | None, agent_key: str, prompt: str) -> None:
    key = _sup_cache_key(tenant_id, user_id, tier, workspace_id, agent_key)
    _supervisor_prompt_cache[key] = {"ts": _time.time(), "prompt": prompt}


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

# -- Skill Tools Cache (60s TTL) ------------------------------------
_skill_tools_cache: dict[str, dict] = {}
_SKILL_TOOLS_CACHE_TTL = 60


def _tools_cache_key(tenant_id: str, tier: str, workspace_id: str | None) -> str:
    return f"{tenant_id}#{tier}#{workspace_id or 'none'}"


def _tools_cache_get(tenant_id: str, tier: str, workspace_id: str | None) -> list | None:
    key = _tools_cache_key(tenant_id, tier, workspace_id)
    entry = _skill_tools_cache.get(key)
    if entry and _time.time() < entry["ts"] + _SKILL_TOOLS_CACHE_TTL:
        return entry["tools"]
    return None


def _tools_cache_set(tenant_id: str, tier: str, workspace_id: str | None, tools: list) -> None:
    _skill_tools_cache[_tools_cache_key(tenant_id, tier, workspace_id)] = {
        "ts": _time.time(), "tools": tools,
    }


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

    @tool(name=tool_name)
    def service_tool(params: str) -> str:
        """Placeholder docstring replaced below."""
        parsed = json.loads(params) if isinstance(params, str) else params
        try:
            if tool_name in TOOLS_NEEDING_SESSION:
                result = handler(parsed, tenant_id, session_id)
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
    result_queue: asyncio.Queue | None = None,
    loop: asyncio.AbstractEventLoop | None = None,
) -> list:
    """Build @tool wrappers for AWS service tools, scoped to the current tenant/user/session."""
    tools = []
    for name, desc in _SERVICE_TOOL_DEFS.items():
        tools.append(_make_service_tool(name, desc, tenant_id, user_id, session_id, result_queue, loop))
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
    # Cache hit for normal path (no skill_names filter)
    if skill_names is None:
        cached = _tools_cache_get(tenant_id, tier, workspace_id)
        if cached is not None:
            return cached

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

    # Always include the compliance matrix tool (read-only, no tenant scoping)
    tools.append(_compliance_matrix_tool)

    # Cache for normal path
    if skill_names is None:
        _tools_cache_set(tenant_id, tier, workspace_id, tools)

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
    Results are cached for 60s to avoid repeated DynamoDB calls.
    """
    names = agent_names or list(SKILL_AGENT_REGISTRY.keys())
    agent_key = ",".join(sorted(names))

    # Check cache first
    cached = _sup_cache_get(tenant_id, user_id, tier, workspace_id, agent_key)
    if cached is not None:
        return cached

    agent_list = "\n".join(
        f"- {name}: {SKILL_AGENT_REGISTRY[name]['description']}"
        for name in names
        if name in SKILL_AGENT_REGISTRY
    )

    # List service tools the supervisor has direct access to
    service_tool_names = [n for n in names if n in _SERVICE_TOOL_DEFS]
    service_list = "\n".join(
        f"- {name}: {_SERVICE_TOOL_DEFS[name]}"
        for name in service_tool_names
    ) if service_tool_names else ""

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

    result = (
        f"Tenant: {tenant_id} | User: {user_id} | Tier: {tier}\n\n"
        f"{base_prompt}\n\n"
        f"--- DIRECT HANDLING (NO DELEGATION) ---\n"
        f"For the following types of messages, respond directly WITHOUT using any tools:\n"
        f"- Greetings and pleasantries (hi, hello, good morning, thanks, etc.)\n"
        f"- Simple yes/no or acknowledgment responses\n"
        f"- Requests to repeat or clarify your last response\n"
        f"- General conversational messages not related to acquisition\n"
        f"For these, provide a brief, friendly response. Do NOT delegate to any specialist.\n\n"
        f"--- SPECIALIST DELEGATION ---\n"
        f"Available specialists for delegation:\n{agent_list}\n\n"
        f"For acquisition-related questions, regulatory queries, document generation, "
        f"and other substantive work: use the available tool functions to delegate to specialists. "
        f"Include relevant context in the query you pass to each specialist.\n\n"
        + (
            f"--- DIRECT SERVICE TOOLS ---\n"
            f"You also have direct access to these AWS service tools (call them directly, do NOT delegate):\n"
            f"{service_list}\n\n"
            f"When using service tools, pass a JSON string as the 'params' argument.\n"
            f"For document generation (create_document), always confirm with the user what was created "
            f"and provide the document type, title, and S3 location in your response."
            if service_list else ""
        )
    )

    _sup_cache_set(tenant_id, user_id, tier, workspace_id, agent_key, result)
    return result


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

    # Add AWS service tools (S3, DynamoDB, doc generation, FAR search, intake)
    composite_session = f"{tenant_id}#{tier}#{user_id}#{session_id or 'none'}"
    service_tools = _build_service_tools(tenant_id, user_id, composite_session)
    all_tools = skill_tools + service_tools

    system_prompt = build_supervisor_prompt(
        tenant_id=tenant_id,
        user_id=user_id,
        tier=tier,
        agent_names=[getattr(t, 'tool_spec', {}).get('name', t.__name__) for t in all_tools],
        workspace_id=resolved_workspace_id,
    )

    # Convert conversation history to Strands format (excludes current prompt)
    strands_history = _to_strands_messages(messages) if messages else None

    supervisor = Agent(
        model=_model,
        system_prompt=system_prompt,
        tools=all_tools,
        callback_handler=None,
        messages=strands_history,
    )

    # Call invoke_async directly — avoids Strands' run_async() which creates
    # a new ThreadPoolExecutor + asyncio.run() event loop on every call
    result = await supervisor.invoke_async(prompt)
    result_text = str(result)

    # Extract tool names called during execution from metrics.tool_metrics
    tools_called = []
    try:
        metrics = getattr(result, "metrics", None)
        if metrics and hasattr(metrics, "tool_metrics"):
            tools_called = list(metrics.tool_metrics.keys())
    except Exception:
        pass

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
    max_turns: int = 15,
    messages: list[dict] | None = None,
) -> AsyncGenerator[dict, None]:
    """Stream text deltas from the Strands supervisor agent.

    Unlike sdk_query() which waits for the full response, this yields
    {"type": "text", "data": "..."} chunks as they arrive from Bedrock
    ConverseStream, plus tool_use events with actual input data, and a
    final {"type": "complete", ...} event.

    Runs the synchronous Strands Agent in a background thread and bridges
    to async via a queue.

    Fast-path: trivial messages (greetings, acknowledgments) skip workspace
    resolution, tool building, and supervisor prompt construction. They use
    a lightweight no-tools Agent with a short system prompt for ~2-4x faster
    time-to-first-token.
    """
    t0 = _time.time()
    use_fast_path = _is_trivial_message(prompt) and not skill_names

    loop = asyncio.get_running_loop()
    chunk_queue: asyncio.Queue = asyncio.Queue()
    handler = QueueCallbackHandler(chunk_queue, loop)
    strands_history = _to_strands_messages(messages) if messages else None

    if use_fast_path:
        # Fast path: no workspace, no tools, short prompt
        logger.info("fast-path: trivial message detected (%r), skipping full pipeline", prompt[:40])
        supervisor = Agent(
            model=_model,
            system_prompt=_TRIVIAL_SYSTEM_PROMPT,
            tools=[],
            callback_handler=handler,
            messages=strands_history,
        )
        skill_tools = []
    else:
        # Full path: resolve workspace, build tools, build prompt
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

        # Add AWS service tools (S3, DynamoDB, doc generation, FAR search, intake)
        composite_session = f"{tenant_id}#{tier}#{user_id}#{session_id or 'none'}"
        service_tools = _build_service_tools(tenant_id, user_id, composite_session, chunk_queue, loop)
        all_tools = skill_tools + service_tools

        system_prompt = build_supervisor_prompt(
            tenant_id=tenant_id,
            user_id=user_id,
            tier=tier,
            agent_names=[getattr(t, 'tool_spec', {}).get('name', t.__name__) for t in all_tools],
            workspace_id=resolved_workspace_id,
        )

        supervisor = Agent(
            model=_model,
            system_prompt=system_prompt,
            tools=all_tools,
            callback_handler=handler,
            messages=strands_history,
        )

    t_setup = _time.time() - t0
    logger.info("agent setup took %.3fs (fast_path=%s, tools=%d)", t_setup, use_fast_path, len(all_tools) if not use_fast_path else 0)

    # Run synchronous Strands agent in a background thread.
    # The callback handler puts chunks into the asyncio.Queue via
    # loop.call_soon_threadsafe — instant delivery, no polling.
    result_holder: list = []
    error_holder: list = []

    def _run_agent():
        try:
            result = supervisor(prompt)
            result_holder.append(result)
        except Exception as exc:
            error_holder.append(exc)
        finally:
            loop.call_soon_threadsafe(chunk_queue.put_nowait, _SENTINEL)

    thread = threading.Thread(target=_run_agent, daemon=True)
    thread.start()

    # Yield chunks as they arrive — await is instant (no polling)
    full_text_parts: list[str] = []
    tools_called: list[str] = []
    ttft_logged = False

    while True:
        chunk = await chunk_queue.get()

        if chunk is _SENTINEL:
            break

        if chunk.get("type") == "text":
            if not ttft_logged:
                ttft = _time.time() - t0
                logger.info("TTFT: %.3fs (fast_path=%s)", ttft, use_fast_path)
                ttft_logged = True
            full_text_parts.append(chunk["data"])
            yield chunk
        elif chunk.get("type") == "tool_use":
            tools_called.append(chunk.get("name", ""))
            yield chunk
        elif chunk.get("type") == "tool_result":
            yield chunk

    thread.join(timeout=5)

    # Extract usage from result
    usage = {}
    if result_holder:
        result = result_holder[0]
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

    total_time = _time.time() - t0
    logger.info("stream complete: %.3fs total, %d tools, %d chars (fast_path=%s)",
                total_time, len(tools_called), len("".join(full_text_parts)), use_fast_path)

    if error_holder:
        yield {"type": "error", "error": str(error_holder[0])}
    else:
        yield {
            "type": "complete",
            "text": "".join(full_text_parts),
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
