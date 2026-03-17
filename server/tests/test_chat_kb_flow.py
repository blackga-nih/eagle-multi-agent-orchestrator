"""KB chat-flow contract tests for Strands supervisor wiring."""

from __future__ import annotations

import asyncio
import json

from app.strands_agentic_service import EAGLE_TOOLS, _build_service_tools, build_supervisor_prompt
from app.streaming_routes import stream_generator


def test_service_tool_registry_includes_kb_tools():
    """Verify knowledge tools are built by _build_service_tools factory."""
    tools = _build_service_tools(tenant_id="test", user_id="test", session_id=None)
    tool_names = {getattr(t, "tool_name", None) or t.__name__ for t in tools}
    assert "knowledge_search" in tool_names
    assert "knowledge_fetch" in tool_names


def test_tool_schema_list_includes_kb_tools():
    tool_names = {tool["name"] for tool in EAGLE_TOOLS}
    assert "knowledge_search" in tool_names
    assert "knowledge_fetch" in tool_names


def test_supervisor_prompt_includes_kb_retrieval_and_sources_rules():
    prompt = build_supervisor_prompt(
        tenant_id="dev-tenant",
        user_id="dev-user",
        tier="advanced",
        agent_names=[],
    )
    assert "KB Retrieval" in prompt
    assert "knowledge_search first" in prompt
    assert "knowledge_fetch on top 1-3" in prompt
    assert "Sources section" in prompt and "s3_key" in prompt


