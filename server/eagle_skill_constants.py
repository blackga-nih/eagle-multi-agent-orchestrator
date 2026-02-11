"""Auto-discovery loader for EAGLE agents and skills.

Walks eagle-plugin/agents/*/agent.md and eagle-plugin/skills/*/SKILL.md,
parses YAML frontmatter, and exports unified dicts.

Exports:
    AGENTS          — dict keyed by directory name for agents
    SKILLS          — dict keyed by directory name for skills
    PLUGIN_CONTENTS — unified dict (agents + skills)
    SKILL_CONSTANTS — dict mapping name -> body content
"""
import os
import re

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_PLUGIN_DIR = os.path.join(_REPO_ROOT, "eagle-plugin")
_AGENTS_DIR = os.path.join(_PLUGIN_DIR, "agents")
_SKILLS_DIR = os.path.join(_PLUGIN_DIR, "skills")


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _parse_frontmatter(content: str) -> tuple:
    """Split YAML frontmatter from body using simple regex (no pyyaml).

    Returns:
        (metadata_dict, body_str)
    """
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
    if not match:
        return {}, content

    yaml_block = match.group(1)
    body = match.group(2)

    meta = {}
    current_key = None

    for line in yaml_block.split("\n"):
        # Handle list items under a key
        list_match = re.match(r"^\s+-\s+(.+)$", line)
        if list_match and current_key:
            if current_key not in meta:
                meta[current_key] = []
            if isinstance(meta[current_key], list):
                meta[current_key].append(list_match.group(1).strip().strip('"\''))
            continue

        # Handle key: value pairs
        kv_match = re.match(r"^(\w[\w-]*):\s*(.*)$", line)
        if kv_match:
            current_key = kv_match.group(1)
            raw_val = kv_match.group(2).strip()

            # Handle multi-line values starting with >
            if raw_val == ">":
                meta[current_key] = ""
                continue

            # Handle null/empty
            if raw_val in ("null", "~", ""):
                meta[current_key] = None
                continue

            # Handle lists on same line: []
            if raw_val == "[]":
                meta[current_key] = []
                continue

            # Handle booleans
            if raw_val.lower() in ("true", "yes"):
                meta[current_key] = True
                continue
            if raw_val.lower() in ("false", "no"):
                meta[current_key] = False
                continue

            # Strip quotes
            meta[current_key] = raw_val.strip('"\'')
            continue

        # Continuation of multi-line value (indented text after >)
        if current_key and current_key in meta and isinstance(meta[current_key], str):
            stripped = line.strip()
            if stripped:
                if meta[current_key]:
                    meta[current_key] += " " + stripped
                else:
                    meta[current_key] = stripped

    return meta, body


def _discover(base_dir: str, filename: str) -> dict:
    """Walk base_dir/*/filename and return dict keyed by directory name.

    Each value is a dict with keys: name, meta, body, content (full file).
    """
    results = {}
    if not os.path.isdir(base_dir):
        return results

    for entry in sorted(os.listdir(base_dir)):
        entry_path = os.path.join(base_dir, entry)
        if not os.path.isdir(entry_path):
            continue
        file_path = os.path.join(entry_path, filename)
        if not os.path.isfile(file_path):
            continue

        content = _read(file_path)
        meta, body = _parse_frontmatter(content)

        results[entry] = {
            "name": meta.get("name", entry),
            "type": meta.get("type", "skill"),
            "description": meta.get("description", ""),
            "triggers": meta.get("triggers", []),
            "tools": meta.get("tools", []),
            "model": meta.get("model"),
            "meta": meta,
            "body": body,
            "content": content,
        }

    return results


# ── Auto-discover agents and skills ─────────────────────────────────

AGENTS: dict = _discover(_AGENTS_DIR, "agent.md")
SKILLS: dict = _discover(_SKILLS_DIR, "SKILL.md")

# Unified dict keyed by directory name
PLUGIN_CONTENTS: dict = {**AGENTS, **SKILLS}

# ── SKILL_CONSTANTS ──────────────────────────────────────────────────
# Maps directory name -> body content for all agents and skills.

SKILL_CONSTANTS: dict = {}
for key, entry in PLUGIN_CONTENTS.items():
    SKILL_CONSTANTS[key] = entry["body"]

# ── Convenience exports (backward compat) ────────────────────────────

OA_INTAKE_SKILL = SKILL_CONSTANTS.get("oa-intake", "")
DOCUMENT_GENERATOR_SKILL = SKILL_CONSTANTS.get("document-generator", "")
LEGAL_COUNSEL_PROMPT = SKILL_CONSTANTS.get("legal-counsel", "")
TECH_TRANSLATOR_PROMPT = SKILL_CONSTANTS.get("tech-translator", "")
MARKET_INTELLIGENCE_PROMPT = SKILL_CONSTANTS.get("market-intelligence", "")
PUBLIC_INTEREST_PROMPT = SKILL_CONSTANTS.get("public-interest", "")
