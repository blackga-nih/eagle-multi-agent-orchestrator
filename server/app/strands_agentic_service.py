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

import json
import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator

from strands import Agent, tool
from strands.models import BedrockModel

# Add server/ to path for eagle_skill_constants
_server_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)

from eagle_skill_constants import SKILL_CONSTANTS, AGENTS, SKILLS, PLUGIN_CONTENTS

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
        f"IMPORTANT: Use the available tool functions to delegate to specialists. "
        f"Include relevant context in the query you pass to each specialist. "
        f"Do not try to answer specialized questions yourself -- delegate to the expert."
    )


# -- SDK Query Wrappers (same signatures as sdk_agentic_service.py) --

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
        session_id: Session ID (reserved for future session persistence)
        workspace_id: Active workspace for per-user prompt resolution
        max_turns: Max tool-use iterations (reserved for future use)

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

    system_prompt = build_supervisor_prompt(
        tenant_id=tenant_id,
        user_id=user_id,
        tier=tier,
        agent_names=[t.__name__ for t in skill_tools],
        workspace_id=resolved_workspace_id,
    )

    supervisor = Agent(
        model=_model,
        system_prompt=system_prompt,
        tools=skill_tools,
        callback_handler=None,
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
