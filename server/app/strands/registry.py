"""
EAGLE Strands Plugin Registry

Dynamic skill/agent registry built from plugin metadata (AGENTS + SKILLS).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger("eagle.strands_agent")

# Max prompt size per subagent to avoid context overflow
MAX_SKILL_PROMPT_CHARS = 4000

_PLUGIN_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "eagle-plugin"
)
_PLUGIN_JSON_PATH = os.path.join(_PLUGIN_DIR, "plugin.json")


def load_plugin_config() -> dict[str, Any]:
    """Load plugin config, merging DynamoDB manifest with bundled plugin.json.

    The DynamoDB PLUGIN#manifest only stores version/agent_count/skill_count —
    it does NOT include the 'data' index needed by load_data(). Always load
    the bundled plugin.json as the base, then overlay any DynamoDB manifest
    fields on top.
    """
    config: dict[str, Any] = {}
    try:
        with open(_PLUGIN_JSON_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    # Overlay DynamoDB manifest fields (version, agent_count, skill_count)
    try:
        from ..plugin_store import get_plugin_manifest

        manifest = get_plugin_manifest()
        if manifest:
            config.update(manifest)
    except Exception:
        pass

    return config


def build_registry() -> dict[str, dict[str, Any]]:
    """Build SKILL_AGENT_REGISTRY dynamically from AGENTS + SKILLS metadata.

    Uses plugin.json to determine which agents/skills are wired as subagents.
    The supervisor agent is excluded (it's the orchestrator, not a subagent).
    """
    # Import here to avoid circular imports
    import sys

    _server_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
    if _server_dir not in sys.path:
        sys.path.insert(0, _server_dir)

    from eagle_skill_constants import AGENTS, SKILLS

    config = load_plugin_config()
    active_agents = set(config.get("agents", []))
    active_skills = set(config.get("skills", []))

    registry: dict[str, dict[str, Any]] = {}

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


def truncate_skill(content: str, max_chars: int = MAX_SKILL_PROMPT_CHARS) -> str:
    """Truncate skill content to fit within subagent context budget."""
    if len(content) <= max_chars:
        return content
    return content[:max_chars] + "\n\n[... truncated for context budget]"


# Build registry at module load
SKILL_AGENT_REGISTRY = build_registry()

# Re-export plugin directory path for load_data
PLUGIN_DIR = _PLUGIN_DIR
