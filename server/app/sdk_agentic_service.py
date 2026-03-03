"""
EAGLE – SDK-Based Agentic Service with Skill→Subagent Orchestration

Uses claude-agent-sdk with AgentDefinition to convert skills into subagents
with separate context windows. The supervisor delegates to skill subagents
via the Task tool — each gets a fresh context window.

Architecture:
  Supervisor (system_prompt + Task tool)
    ├── oa-intake (AgentDefinition, fresh context)
    ├── legal-counsel (AgentDefinition, fresh context)
    ├── market-intelligence (AgentDefinition, fresh context)
    ├── tech-translator (AgentDefinition, fresh context)
    ├── public-interest (AgentDefinition, fresh context)
    └── document-generator (AgentDefinition, fresh context)

Key difference from agentic_service.py:
  - agentic_service.py: skills = prompt text injected into one system prompt (shared context)
  - sdk_agentic_service.py: skills = AgentDefinitions with separate context windows per skill
"""

import json
import logging
import os
import sys
from typing import Any, AsyncGenerator

from claude_agent_sdk import (
    query,
    ClaudeAgentOptions,
    AgentDefinition,
)

# Add server/ to path for eagle_skill_constants
_server_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)

from eagle_skill_constants import SKILL_CONSTANTS, AGENTS, SKILLS, PLUGIN_CONTENTS

logger = logging.getLogger("eagle.sdk_agent")


def _get_bedrock_env() -> dict:
    """Resolve AWS credentials via boto3 (handles SSO, IAM roles, env vars) and
    return as a flat env dict for the Claude CLI subprocess.

    The bundled Claude Code CLI is Node.js and cannot use botocore's SSO resolver,
    so we bridge the gap: resolve here in Python and pass static creds to the CLI.
    """
    import boto3

    env: dict = {
        "CLAUDE_CODE_USE_BEDROCK": "1",
        "AWS_REGION": os.getenv("AWS_REGION", "us-east-1"),
        "HOME": os.getenv("HOME", "/home/appuser"),
    }
    try:
        creds = boto3.Session().get_credentials()
        if creds:
            frozen = creds.get_frozen_credentials()
            env["AWS_ACCESS_KEY_ID"] = frozen.access_key
            env["AWS_SECRET_ACCESS_KEY"] = frozen.secret_key
            if frozen.token:
                env["AWS_SESSION_TOKEN"] = frozen.token
    except Exception as e:
        logger.warning("Could not resolve AWS credentials for CLI subprocess: %s", e)
    return env


# ── Configuration ────────────────────────────────────────────────────

MODEL = os.getenv("EAGLE_SDK_MODEL", "haiku")

# Tier-gated tool access for subagents
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

# Max prompt size per subagent to avoid context overflow
MAX_SKILL_PROMPT_CHARS = 4000


# ── Skill → AgentDefinition Registry (built from plugin metadata) ───

# Read plugin.json to determine which agents/skills are wired as subagents
_PLUGIN_JSON_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "eagle-plugin", "plugin.json"
)

def _load_plugin_config() -> dict:
    """Load plugin manifest — prefers DynamoDB PLUGIN#manifest, falls back to bundled file."""
    # Try DynamoDB first (hot-reloadable authoritative source)
    try:
        from .plugin_store import get_plugin_manifest
        manifest = get_plugin_manifest()
        if manifest:
            return manifest
    except Exception:
        pass  # DynamoDB unavailable — fall through to bundled file

    # Fallback: bundled eagle-plugin/plugin.json
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

    # Add active agents (excluding supervisor — it orchestrates, not a subagent)
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

    # Add active skills
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


def build_skill_agents(
    model: str = None,
    tier: str = "advanced",
    skill_names: list[str] | None = None,
    tenant_id: str = "demo-tenant",
    user_id: str = "demo-user",
    workspace_id: str | None = None,
) -> dict[str, AgentDefinition]:
    """Build AgentDefinition dict from skill registry.

    Each skill becomes a subagent with its own fresh context window.
    The skill markdown content becomes the subagent's system prompt.

    When workspace_id is provided, skill prompts are resolved via wspc_store
    using the 4-layer chain (workspace override → PLUGIN# canonical).

    Args:
        model: Model for subagents (defaults to MODULE-level MODEL)
        tier: Subscription tier for tool gating
        skill_names: Specific skills to include (None = all available)
        tenant_id: Tenant for workspace resolution
        user_id: User for workspace resolution
        workspace_id: Active workspace ID for per-user prompt overrides

    Returns:
        Dict of name -> AgentDefinition suitable for ClaudeAgentOptions.agents
    """
    agent_model = model or MODEL
    tier_tools = TIER_TOOLS.get(tier, TIER_TOOLS["basic"])
    agents = {}

    # Build base registry from bundled PLUGIN_CONTENTS + workspace overrides
    for name, meta in SKILL_AGENT_REGISTRY.items():
        if skill_names and name not in skill_names:
            continue

        # Resolve prompt through workspace chain when workspace_id is available
        if workspace_id:
            try:
                from .wspc_store import resolve_skill
                prompt_body, _source = resolve_skill(tenant_id, user_id, workspace_id, name)
            except Exception as exc:
                logger.warning("wspc_store.resolve_skill failed for %s: %s — using bundled", name, exc)
                prompt_body = ""
        else:
            prompt_body = ""

        # Fall back to bundled PLUGIN_CONTENTS when workspace resolution yields nothing
        if not prompt_body:
            entry = PLUGIN_CONTENTS.get(meta["skill_key"])
            if not entry:
                logger.warning("Plugin content not found for %s (key=%s)", name, meta["skill_key"])
                continue
            prompt_body = entry["body"]

        agents[name] = AgentDefinition(
            description=meta["description"],
            prompt=_truncate_skill(prompt_body),
            tools=meta["tools"] or tier_tools,
            model=meta.get("model") or agent_model,
        )

    # Merge active user-created SKILL# items (tenant-defined skills override bundled when same name)
    try:
        from .skill_store import list_active_skills
        user_skills = list_active_skills(tenant_id)
        for skill in user_skills:
            name = skill.get("name", "")
            if not name:
                continue
            if skill_names and name not in skill_names:
                continue
            prompt_body = skill.get("prompt_body", "")
            if not prompt_body:
                continue
            agents[name] = AgentDefinition(
                description=skill.get("description", f"{name} specialist"),
                prompt=_truncate_skill(prompt_body),
                tools=skill.get("tools") or tier_tools,
                model=skill.get("model") or agent_model,
            )
    except Exception as exc:
        logger.warning("skill_store.list_active_skills failed for %s: %s — skipping user skills", tenant_id, exc)

    return agents


# ── Supervisor Prompt ────────────────────────────────────────────────

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
            logger.warning("wspc_store.resolve_agent failed for supervisor: %s — using bundled", exc)

    # Fall back to bundled AGENTS content
    if not base_prompt:
        supervisor_entry = AGENTS.get("supervisor")
        base_prompt = supervisor_entry["body"].strip() if supervisor_entry else "You are the EAGLE Supervisor Agent for NCI Office of Acquisitions."

    return (
        f"Tenant: {tenant_id} | User: {user_id} | Tier: {tier}\n\n"
        f"{base_prompt}\n\n"
        f"--- ACTIVE SUBAGENTS ---\n"
        f"Available subagents for delegation via Task tool:\n{agent_list}\n\n"
        f"IMPORTANT: Use the Task tool to delegate to subagents. "
        f"Include relevant context in the prompt you pass to each subagent. "
        f"Do not try to answer specialized questions yourself — delegate to the expert."
    )


# ── SDK Query Wrappers ──────────────────────────────────────────────

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
    """Run a supervisor query with skill subagents.

    This is the main entry point for the SDK-based agentic service.
    Each skill runs in its own context window via AgentDefinition.

    Args:
        prompt: User's query/request
        tenant_id: Tenant identifier for multi-tenant isolation
        user_id: User identifier
        tier: Subscription tier (basic/advanced/premium)
        model: Model override (default: MODULE-level MODEL)
        skill_names: Subset of skills to make available
        session_id: Session ID for resume (if continuing conversation)
        workspace_id: Active workspace for per-user prompt resolution
        max_turns: Max tool-use iterations

    Yields:
        SDK message objects (SystemMessage, AssistantMessage, UserMessage, ResultMessage)
    """
    # Resolve active workspace when none provided (auto-provision Default workspace)
    resolved_workspace_id = workspace_id
    if not resolved_workspace_id:
        try:
            from .workspace_store import get_or_create_default
            ws = get_or_create_default(tenant_id, user_id)
            resolved_workspace_id = ws.get("workspace_id")
        except Exception as exc:
            logger.warning("workspace_store.get_or_create_default failed: %s — using bundled prompts", exc)

    agent_model = model or MODEL
    agents = build_skill_agents(
        model=agent_model,
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
        agent_names=list(agents.keys()),
        workspace_id=resolved_workspace_id,
    )

    options = ClaudeAgentOptions(
        model=agent_model,
        system_prompt=system_prompt,
        allowed_tools=["Task"],
        permission_mode="bypassPermissions",
        max_turns=max_turns,
        max_budget_usd=TIER_BUDGETS.get(tier, 0.25),
        cwd=os.path.dirname(os.path.abspath(__file__)),
        env=_get_bedrock_env(),
        agents=agents,
    )

    async for message in query(prompt=prompt, options=options):
        yield message


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

    This is the "shared context" pattern — skill content injected as system_prompt.
    Use for focused, single-skill queries where subagent overhead is unnecessary.

    Args:
        prompt: User's query
        skill_name: Skill key from SKILL_CONSTANTS
        tenant_id: Tenant identifier
        user_id: User identifier
        tier: Subscription tier
        model: Model override
        max_turns: Max tool-use iterations

    Yields:
        SDK message objects
    """
    skill_key = SKILL_AGENT_REGISTRY.get(skill_name, {}).get("skill_key", skill_name)
    entry = PLUGIN_CONTENTS.get(skill_key)
    if not entry:
        raise ValueError(f"Skill not found: {skill_name} (key={skill_key})")
    skill_content = entry["body"]

    agent_model = model or MODEL
    tenant_context = (
        f"Tenant: {tenant_id} | User: {user_id} | Tier: {tier}\n"
        f"You are operating as the {skill_name} specialist for this tenant.\n\n"
    )

    options = ClaudeAgentOptions(
        model=agent_model,
        system_prompt=tenant_context + skill_content,
        allowed_tools=TIER_TOOLS.get(tier, []),
        permission_mode="bypassPermissions",
        max_turns=max_turns,
        max_budget_usd=TIER_BUDGETS.get(tier, 0.25),
        cwd=os.path.dirname(os.path.abspath(__file__)),
        env=_get_bedrock_env(),
    )

    async for message in query(prompt=prompt, options=options):
        yield message
