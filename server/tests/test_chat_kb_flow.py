"""KB chat-flow contract tests for Strands supervisor wiring."""

from __future__ import annotations

import asyncio
import json

from app.strands_agentic_service import EAGLE_TOOLS, _build_all_service_tools, build_supervisor_prompt
from app.streaming_routes import stream_generator


def test_service_tools_have_named_params():
    """All service tools should expose named parameters, not generic 'params: str'."""
    tools = _build_all_service_tools("test-tenant", "test-user", "test-session")
    for t in tools:
        spec = t.tool_spec
        assert spec is not None, f"Tool {t} missing tool_spec"
        schema = spec.get("inputSchema", {}).get("json", {})
        props = schema.get("properties", {})
        assert "params" not in props, f"{t.tool_name} still uses generic 'params' field"


def test_tool_schema_list_includes_kb_tools():
    tool_names = {tool["name"] for tool in EAGLE_TOOLS}
    assert "knowledge_search" in tool_names
    assert "knowledge_fetch" in tool_names


def test_supervisor_prompt_includes_research_cascade_rules():
    prompt = build_supervisor_prompt(
        tenant_id="dev-tenant",
        user_id="dev-user",
        tier="advanced",
        agent_names=[],
    )
    assert "RESEARCH CASCADE" in prompt
    assert "STEP 1" in prompt
    assert "STEP 2" in prompt
    assert "STEP 3" in prompt
    assert "knowledge_search" in prompt
    assert "knowledge_fetch on the top 1-3 relevant s3_keys" in prompt
    assert "Sources section" in prompt


def test_supervisor_prompt_cascade_ordering():
    """STEP 1 (KB) must appear before STEP 2 (matrix) before STEP 3 (web)."""
    prompt = build_supervisor_prompt(
        tenant_id="dev-tenant",
        user_id="dev-user",
        tier="advanced",
        agent_names=[],
    )
    kb_pos = prompt.index("STEP 1")
    matrix_pos = prompt.index("STEP 2")
    web_pos = prompt.index("STEP 3")
    assert kb_pos < matrix_pos < web_pos


def test_supervisor_prompt_cascade_requires_kb_before_web():
    """Prompt must instruct agent not to skip to web_search."""
    prompt = build_supervisor_prompt(
        tenant_id="dev-tenant",
        user_id="dev-user",
        tier="advanced",
        agent_names=[],
    )
    assert "knowledge_search BEFORE web_search" in prompt


def test_supervisor_prompt_compliance_matrix_before_web():
    """query_compliance_matrix must be mentioned before web_search instructions."""
    prompt = build_supervisor_prompt(
        tenant_id="dev-tenant",
        user_id="dev-user",
        tier="advanced",
        agent_names=[],
    )
    matrix_pos = prompt.index("query_compliance_matrix")
    web_pos = prompt.index("STEP 3")
    assert matrix_pos < web_pos


def test_streaming_emits_text_when_complete_event_has_only_final_text(monkeypatch):
    async def _mock_sdk_query_streaming(**kwargs):
        yield {"type": "tool_use", "name": "knowledge_search"}
        yield {"type": "complete", "text": "Final answer from complete event only.", "tools_called": [], "usage": {}}

    monkeypatch.setattr("app.streaming_routes.sdk_query_streaming", _mock_sdk_query_streaming)

    async def _collect():
        events = []
        async for raw in stream_generator(
            message="test",
            tenant_id="dev-tenant",
            user_id="dev-user",
            tier="advanced",
            subscription_service=None,  # unused by stream_generator
            session_id=None,
            messages=None,
        ):
            if raw.startswith("data: "):
                events.append(json.loads(raw[6:]))
        return events

    events = asyncio.run(_collect())
    text_events = [e for e in events if e.get("type") == "text" and e.get("content")]
    complete_events = [e for e in events if e.get("type") == "complete"]

    assert any("Final answer from complete event only." in e.get("content", "") for e in text_events)
    assert complete_events
