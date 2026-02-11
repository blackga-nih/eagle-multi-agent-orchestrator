"""Skill and prompt loader for EAGLE eval suite.

Loads skills from eagle-plugin/skills/ and prompts from eagle-plugin/prompts/
at import time. Single source of truth — no embedded copies.
"""
import os

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_PLUGIN_DIR = os.path.join(_REPO_ROOT, "eagle-plugin")
_SKILLS_DIR = os.path.join(_PLUGIN_DIR, "skills")
_PROMPTS_DIR = os.path.join(_PLUGIN_DIR, "prompts")


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# Skills (from eagle-plugin/skills/<name>/SKILL.md)
OA_INTAKE_SKILL = _read(os.path.join(_SKILLS_DIR, "oa-intake", "SKILL.md"))
DOCUMENT_GENERATOR_SKILL = _read(os.path.join(_SKILLS_DIR, "document-generator", "SKILL.md"))

# Legacy agent prompts (from eagle-plugin/prompts/<file>.txt)
LEGAL_COUNSEL_PROMPT = _read(os.path.join(_PROMPTS_DIR, "02-legal.txt"))
TECH_TRANSLATOR_PROMPT = _read(os.path.join(_PROMPTS_DIR, "03-tech.txt"))
MARKET_INTELLIGENCE_PROMPT = _read(os.path.join(_PROMPTS_DIR, "04-market.txt"))
PUBLIC_INTEREST_PROMPT = _read(os.path.join(_PROMPTS_DIR, "05-public.txt"))

# Lookup dict used by test_eagle_sdk_eval.py
SKILL_CONSTANTS = {
    "oa-intake": OA_INTAKE_SKILL,
    "document-generator": DOCUMENT_GENERATOR_SKILL,
    "02-legal.txt": LEGAL_COUNSEL_PROMPT,
    "03-tech.txt": TECH_TRANSLATOR_PROMPT,
    "04-market.txt": MARKET_INTELLIGENCE_PROMPT,
    "05-public.txt": PUBLIC_INTEREST_PROMPT,
}
