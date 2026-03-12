"""Strands specialist tool factory for EAGLE plugin agents/skills.

Builds Strands @tool wrappers from plugin metadata while preserving existing
precedence rules: explicit skill tools override tier defaults.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable

from eagle_skill_constants import AGENTS, SKILLS, PLUGIN_CONTENTS

logger = logging.getLogger("eagle.strands_tools")

try:
    from strands import Agent, tool
except Exception:  # pragma: no cover - handled at runtime in environments without strands
    Agent = None
    tool = None

MAX_SKILL_PROMPT_CHARS = 4000

TIER_DEFAULT_TOOLS = {
    "basic": [],
    "advanced": ["Read", "Glob", "Grep"],
    "premium": ["Read", "Glob", "Grep", "Bash"],
}

_PLUGIN_JSON_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "eagle-plugin", "plugin.json"
)


def _load_plugin_config() -> dict[str, Any]:
    try:
        with open(_PLUGIN_JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def truncate_skill(content: str, max_chars: int = MAX_SKILL_PROMPT_CHARS) -> str:
    if len(content) <= max_chars:
        return content
    return content[:max_chars] + "\n\n[... truncated for context budget]"


def build_skill_registry() -> dict[str, dict[str, Any]]:
    """Build a unified specialist registry from plugin metadata.

    Excludes the configured supervisor. Includes only agents/skills listed in
    plugin.json when list constraints are present.
    """
    config = _load_plugin_config()
    active_agents = set(config.get("agents", []))
    active_skills = set(config.get("skills", []))
    supervisor_name = config.get("agent", "supervisor")

    registry: dict[str, dict[str, Any]] = {}

    for name, entry in AGENTS.items():
        if name == supervisor_name:
            continue
        if active_agents and name not in active_agents:
            continue
        registry[name] = {
            "name": name,
            "description": entry.get("description", ""),
            "skill_key": name,
            "tools": entry.get("tools") or [],
            "model": entry.get("model"),
            "type": "agent",
        }

    for name, entry in SKILLS.items():
        if active_skills and name not in active_skills:
            continue
        registry[name] = {
            "name": name,
            "description": entry.get("description", ""),
            "skill_key": name,
            "tools": entry.get("tools") or [],
            "model": entry.get("model"),
            "type": "skill",
        }

    return registry


def resolve_tools_for_specialist(meta: dict[str, Any], tier: str) -> list[str]:
    """Preserve existing precedence: metadata tools first, tier defaults otherwise."""
    metadata_tools = meta.get("tools") or []
    if metadata_tools:
        return metadata_tools
    return TIER_DEFAULT_TOOLS.get((tier or "basic").lower(), TIER_DEFAULT_TOOLS["basic"])


def list_specialist_metadata(tier: str = "advanced", skill_names: list[str] | None = None) -> list[dict[str, Any]]:
    registry = build_skill_registry()
    rows: list[dict[str, Any]] = []

    for name, meta in registry.items():
        if skill_names and name not in skill_names:
            continue
        entry = PLUGIN_CONTENTS.get(meta["skill_key"])
        if not entry:
            logger.warning("Plugin content not found for %s (key=%s)", name, meta["skill_key"])
            continue

        rows.append(
            {
                "name": name,
                "description": meta.get("description", ""),
                "skill_key": meta["skill_key"],
                "system_prompt": truncate_skill(entry.get("body", "")),
                "tools": resolve_tools_for_specialist(meta, tier),
                "model": meta.get("model"),
                "type": meta.get("type", "skill"),
            }
        )

    return rows


def _ensure_strands() -> None:
    if Agent is None or tool is None:
        raise RuntimeError(
            "strands package is not installed. Add 'strands-agents' to requirements and install dependencies."
        )


def make_specialist_tool(
    *,
    name: str,
    description: str,
    system_prompt: str,
    inner_tools: list[str],
    model_factory: Callable[[str | None], Any],
    model_override: str | None = None,
):
    """Create a Strands @tool wrapper for one specialist.

    The wrapped tool delegates execution to an inner specialist Agent with the
    skill/agent body as its system prompt.
    """
    _ensure_strands()

    @tool(name=name, description=description or f"Delegate to {name}")
    def specialist(query: str) -> str:
        inner_model = model_factory(model_override)
        inner_agent = Agent(
            system_prompt=system_prompt,
            tools=inner_tools,
            model=inner_model,
        )
        result = inner_agent(query)
        return str(result)

    return specialist


def build_specialist_tools(
    *,
    tier: str,
    model_factory: Callable[[str | None], Any],
    skill_names: list[str] | None = None,
) -> tuple[list[Any], list[dict[str, Any]]]:
    """Return (tool_functions, metadata_rows)."""
    metadata_rows = list_specialist_metadata(tier=tier, skill_names=skill_names)
    tool_fns: list[Any] = []

    for row in metadata_rows:
        tool_fns.append(
            make_specialist_tool(
                name=row["name"],
                description=row.get("description", ""),
                system_prompt=row["system_prompt"],
                inner_tools=row["tools"],
                model_factory=model_factory,
                model_override=row.get("model"),
            )
        )

    return tool_fns, metadata_rows


def to_public_tool_docs(tier: str = "advanced", skill_names: list[str] | None = None) -> list[dict[str, Any]]:
    """Docs-friendly tool list for health and /api/tools endpoints."""
    rows = list_specialist_metadata(tier=tier, skill_names=skill_names)
    return [
        {
            "name": row["name"],
            "description": row.get("description", ""),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "User request to delegate"},
                },
                "required": ["query"],
            },
        }
        for row in rows
    ]
