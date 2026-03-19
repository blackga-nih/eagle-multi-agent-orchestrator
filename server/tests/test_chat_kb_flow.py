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


def test_supervisor_prompt_includes_kb_retrieval_and_sources_rules():
    prompt = build_supervisor_prompt(
        tenant_id="dev-tenant",
        user_id="dev-user",
        tier="advanced",
        agent_names=[],
    )
    assert "KB Retrieval Rules" in prompt
    assert "knowledge_search first" in prompt
    assert "knowledge_fetch on the top 1-3 relevant docs" in prompt
    assert "Sources section with title + s3_key" in prompt


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
