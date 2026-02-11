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

from eagle_skill_constants import SKILL_CONSTANTS

logger = logging.getLogger("eagle.sdk_agent")

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


# ── Skill → AgentDefinition Registry ────────────────────────────────

# Map skill keys to AgentDefinition metadata.
# prompt content comes from SKILL_CONSTANTS at build time.
SKILL_AGENT_REGISTRY = {
    "oa-intake": {
        "description": (
            "Gathers acquisition requirements and determines type/threshold. "
            "Use for initial intake when a user has a new procurement need."
        ),
        "skill_key": "oa-intake",
        "tools": [],
        "model": None,  # inherit from supervisor
    },
    "legal-counsel": {
        "description": (
            "Assesses legal risks, protest vulnerabilities, FAR compliance, "
            "and appropriations law. Use for legal review of acquisitions."
        ),
        "skill_key": "02-legal.txt",
        "tools": [],
        "model": None,
    },
    "market-intelligence": {
        "description": (
            "Researches market conditions, vendors, pricing, GSA schedules, "
            "and small business opportunities. Use for market research."
        ),
        "skill_key": "04-market.txt",
        "tools": [],
        "model": None,
    },
    "tech-translator": {
        "description": (
            "Bridges technical requirements with contract language. "
            "Translates scientific/IT needs into measurable contract requirements."
        ),
        "skill_key": "03-tech.txt",
        "tools": [],
        "model": None,
    },
    "public-interest": {
        "description": (
            "Ensures fair competition, transparency, and public accountability. "
            "Evaluates taxpayer value and flags fairness issues."
        ),
        "skill_key": "05-public.txt",
        "tools": [],
        "model": None,
    },
    "document-generator": {
        "description": (
            "Generates acquisition documents: SOW, IGCE, Market Research, "
            "J&A, Acquisition Plan, Eval Criteria, and more."
        ),
        "skill_key": "document-generator",
        "tools": [],
        "model": None,
    },
}


def _truncate_skill(content: str, max_chars: int = MAX_SKILL_PROMPT_CHARS) -> str:
    """Truncate skill content to fit within subagent context budget."""
    if len(content) <= max_chars:
        return content
    return content[:max_chars] + "\n\n[... truncated for context budget]"


def build_skill_agents(
    model: str = None,
    tier: str = "advanced",
    skill_names: list[str] | None = None,
) -> dict[str, AgentDefinition]:
    """Build AgentDefinition dict from skill registry.

    Each skill becomes a subagent with its own fresh context window.
    The skill markdown content becomes the subagent's system prompt.

    Args:
        model: Model for subagents (defaults to MODULE-level MODEL)
        tier: Subscription tier for tool gating
        skill_names: Specific skills to include (None = all available)

    Returns:
        Dict of name -> AgentDefinition suitable for ClaudeAgentOptions.agents
    """
    agent_model = model or MODEL
    tier_tools = TIER_TOOLS.get(tier, TIER_TOOLS["basic"])
    agents = {}

    for name, meta in SKILL_AGENT_REGISTRY.items():
        if skill_names and name not in skill_names:
            continue

        skill_content = SKILL_CONSTANTS.get(meta["skill_key"])
        if not skill_content:
            logger.warning("Skill content not found for %s (key=%s)", name, meta["skill_key"])
            continue

        agents[name] = AgentDefinition(
            description=meta["description"],
            prompt=_truncate_skill(skill_content),
            tools=meta["tools"] or tier_tools,
            model=meta.get("model") or agent_model,
        )

    return agents


# ── Supervisor Prompt ────────────────────────────────────────────────

def build_supervisor_prompt(
    tenant_id: str = "demo-tenant",
    user_id: str = "demo-user",
    tier: str = "advanced",
    agent_names: list[str] | None = None,
) -> str:
    """Build the supervisor system prompt with available subagent descriptions.

    The supervisor only orchestrates — it delegates to skill subagents
    via the Task tool. It does NOT contain skill content itself.
    """
    names = agent_names or list(SKILL_AGENT_REGISTRY.keys())
    agent_list = "\n".join(
        f"- {name}: {SKILL_AGENT_REGISTRY[name]['description']}"
        for name in names
        if name in SKILL_AGENT_REGISTRY
    )

    return (
        f"You are the EAGLE Supervisor Agent for NCI Office of Acquisitions.\n"
        f"Tenant: {tenant_id} | User: {user_id} | Tier: {tier}\n\n"
        f"You orchestrate acquisition workflows by delegating to specialized skill subagents.\n"
        f"Each subagent has its own expertise and separate context — use them for focused analysis.\n\n"
        f"Available subagents:\n{agent_list}\n\n"
        f"WORKFLOW GUIDELINES:\n"
        f"1. For new acquisitions: start with oa-intake, then market-intelligence, then legal-counsel\n"
        f"2. For document generation: use document-generator after intake is complete\n"
        f"3. For specific reviews: use the appropriate specialist directly\n"
        f"4. Always synthesize subagent findings into a coherent summary for the user\n\n"
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
        max_turns: Max tool-use iterations

    Yields:
        SDK message objects (SystemMessage, AssistantMessage, UserMessage, ResultMessage)
    """
    agent_model = model or MODEL
    agents = build_skill_agents(
        model=agent_model,
        tier=tier,
        skill_names=skill_names,
    )

    system_prompt = build_supervisor_prompt(
        tenant_id=tenant_id,
        user_id=user_id,
        tier=tier,
        agent_names=list(agents.keys()),
    )

    options = ClaudeAgentOptions(
        model=agent_model,
        system_prompt=system_prompt,
        allowed_tools=["Task"],
        permission_mode="bypassPermissions",
        max_turns=max_turns,
        max_budget_usd=TIER_BUDGETS.get(tier, 0.25),
        cwd=os.path.dirname(os.path.abspath(__file__)),
        env={
            "CLAUDE_CODE_USE_BEDROCK": "1",
            "AWS_REGION": "us-east-1",
        },
        agents=agents,
        **({"resume": session_id} if session_id else {}),
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
    skill_content = SKILL_CONSTANTS.get(skill_key)
    if not skill_content:
        raise ValueError(f"Skill not found: {skill_name} (key={skill_key})")

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
        env={
            "CLAUDE_CODE_USE_BEDROCK": "1",
            "AWS_REGION": "us-east-1",
        },
    )

    async for message in query(prompt=prompt, options=options):
        yield message
