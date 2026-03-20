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

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time as _time
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from strands import Agent

# Add server/ to path for eagle_skill_constants
_server_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)

from eagle_skill_constants import PLUGIN_CONTENTS

# Import from modular strands package
from .strands import (
    SKILL_AGENT_REGISTRY,
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    build_end_of_turn_state,
    build_service_tools,
    build_skill_tools,
    build_state_updates,
    build_supervisor_prompt,
    build_trace_attrs,
    ensure_langfuse_exporter,
    shared_model,
)
from .strands.fast_path import (
    ensure_create_document_for_direct_request,
    maybe_fast_path_document_generation,
)

# Re-export for backwards compatibility
from .strands.model import MODEL, TIER_BUDGETS, TIER_TOOLS
from .strands.tool_schemas import EAGLE_TOOLS

logger = logging.getLogger("eagle.strands_agent")


# -- SDK Query Wrappers (same signatures as sdk_agentic_service.py) --


def _to_strands_messages(anthropic_messages: list[dict]) -> list[dict]:
    """Convert Anthropic-format messages to Strands Message format.

    Anthropic: [{"role": "user", "content": "text"}, ...]
    Strands:   [{"role": "user", "content": [{"text": "text"}]}, ...]
    """
    strands_msgs = []
    for msg in anthropic_messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, str):
            strands_msgs.append({"role": role, "content": [{"text": content}]})
        elif isinstance(content, list):
            # Already in block format — pass through
            strands_msgs.append({"role": role, "content": content})
    return strands_msgs


async def sdk_query(
    prompt: str,
    tenant_id: str = "demo-tenant",
    user_id: str = "demo-user",
    tier: str = "advanced",
    model: str = None,
    skill_names: list[str] | None = None,
    session_id: str | None = None,
    workspace_id: str | None = None,
    package_context: Any = None,
    max_turns: int = 15,
    messages: list[dict] | None = None,
    username: str | None = None,
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
        session_id: Session ID for session persistence
        workspace_id: Active workspace for per-user prompt resolution
        max_turns: Max tool-use iterations (reserved for future use)
        messages: Conversation history in Anthropic format (excludes current prompt)

    Yields:
        AssistantMessage and ResultMessage adapter objects
    """
    fast_path = await maybe_fast_path_document_generation(
        prompt=prompt,
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        package_context=package_context,
    )
    if fast_path is not None:
        result = fast_path["result"]
        if "error" in result:
            yield AssistantMessage(
                content=[TextBlock(text=f"Document generation failed: {result['error']}")]
            )
            yield ResultMessage(result=f"Document generation failed: {result['error']}", usage={})
            return

        text = (
            f"Generated a draft {fast_path['doc_type'].replace('_', ' ')} document. "
            "You can open it from the document card."
        )
        yield AssistantMessage(
            content=[
                TextBlock(text=text),
                ToolUseBlock(name="create_document"),
            ]
        )
        yield ResultMessage(
            result=text,
            usage={"tools_called": 1, "tools": ["create_document"], "fast_path": True},
        )
        return

    # Resolve active workspace when none provided
    resolved_workspace_id = workspace_id
    if not resolved_workspace_id:
        try:
            from .workspace_store import get_or_create_default

            ws = get_or_create_default(tenant_id, user_id)
            resolved_workspace_id = ws.get("workspace_id")
        except Exception as exc:
            logger.warning(
                "workspace_store.get_or_create_default failed: %s -- using bundled prompts", exc
            )

    skill_tools = build_skill_tools(
        tier=tier,
        skill_names=skill_names,
        tenant_id=tenant_id,
        user_id=user_id,
        workspace_id=resolved_workspace_id,
        session_id=session_id or "",
    )

    # Build service tools (S3, DynamoDB, create_document, search_far, etc.)
    service_tools = build_service_tools(
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        prompt_context=prompt,
        package_context=package_context,
    )

    system_prompt = build_supervisor_prompt(
        tenant_id=tenant_id,
        user_id=user_id,
        tier=tier,
        agent_names=[t.__name__ for t in skill_tools],
        workspace_id=resolved_workspace_id,
    )

    # Convert conversation history to Strands format (excludes current prompt)
    strands_history = _to_strands_messages(messages) if messages else None

    ensure_langfuse_exporter()
    supervisor = Agent(
        model=shared_model,
        system_prompt=system_prompt,
        tools=skill_tools + service_tools,
        callback_handler=None,
        messages=strands_history,
        trace_attributes=build_trace_attrs(
            tenant_id=tenant_id,
            user_id=user_id,
            tier=tier,
            session_id=session_id or "",
            username=username or "",
        ),
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

    forced_doc = await ensure_create_document_for_direct_request(
        prompt=prompt,
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        package_context=package_context,
        tools_called=tools_called,
    )
    if forced_doc is not None:
        tools_called.append("create_document")
        result_text = (
            f"Generated a draft {forced_doc['doc_type'].replace('_', ' ')} document. "
            "Open the document card to review or edit it."
        )

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


async def sdk_query_streaming(
    prompt: str,
    tenant_id: str = "demo-tenant",
    user_id: str = "demo-user",
    tier: str = "advanced",
    skill_names: list[str] | None = None,
    session_id: str | None = None,
    workspace_id: str | None = None,
    package_context: Any = None,
    max_turns: int = 15,
    messages: list[dict] | None = None,
    username: str | None = None,
) -> AsyncGenerator[dict, None]:
    """Stream text deltas from the Strands supervisor agent.

    Unlike sdk_query() which waits for the full response, this yields
    {"type": "text", "data": "..."} chunks as they arrive from Bedrock
    ConverseStream, plus a final {"type": "complete", ...} event.

    Uses Agent.stream_async() which handles the sync→async bridge
    internally. Factory tools push results via an asyncio.Queue that
    is drained between stream events.
    """
    fast_path = await maybe_fast_path_document_generation(
        prompt=prompt,
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        package_context=package_context,
    )
    if fast_path is not None:
        result = fast_path["result"]
        if "error" in result:
            yield {"type": "error", "error": result["error"]}
            return
        yield {"type": "tool_use", "name": "create_document"}
        yield {"type": "tool_result", "name": "create_document", "result": result}
        # Emit package state update for fast-path document creation
        for state_evt in build_state_updates(result, "create_document", tenant_id):
            yield state_evt
        text = (
            f"Generated a draft {fast_path['doc_type'].replace('_', ' ')} document. "
            "Open the document card to review or edit it."
        )
        yield {"type": "text", "data": text}
        # End-of-turn state refresh for fast-path
        for state_evt in build_end_of_turn_state(package_context, tenant_id):
            yield state_evt
        yield {
            "type": "complete",
            "text": text,
            "tools_called": ["create_document"],
            "usage": {"tools_called": 1, "tools": ["create_document"], "fast_path": True},
        }
        return

    # Resolve workspace
    resolved_workspace_id = workspace_id
    if not resolved_workspace_id:
        try:
            from .workspace_store import get_or_create_default

            ws = get_or_create_default(tenant_id, user_id)
            resolved_workspace_id = ws.get("workspace_id")
        except Exception as exc:
            logger.warning("workspace_store.get_or_create_default failed: %s", exc)

    # --- stream_async() approach: SDK handles sync→async bridge ---
    # result_queue is still used by factory tools to push tool_result events.
    # These are drained between stream events in the main async for loop.

    result_queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    skill_tools = build_skill_tools(
        tier=tier,
        skill_names=skill_names,
        tenant_id=tenant_id,
        user_id=user_id,
        workspace_id=resolved_workspace_id,
        session_id=session_id or "",
        result_queue=result_queue,
        loop=loop,
    )

    # Build service tools (S3, DynamoDB, create_document, search_far, etc.)
    service_tools = build_service_tools(
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        prompt_context=prompt,
        package_context=package_context,
        result_queue=result_queue,
        loop=loop,
    )

    system_prompt = build_supervisor_prompt(
        tenant_id=tenant_id,
        user_id=user_id,
        tier=tier,
        agent_names=[t.__name__ for t in skill_tools],
        workspace_id=resolved_workspace_id,
    )

    strands_history = _to_strands_messages(messages) if messages else None

    # Let the frontend know tools are ready and agent is being constructed
    yield {"type": "agent_status", "status": "Preparing tools...", "detail": "setup"}

    ensure_langfuse_exporter()
    supervisor = Agent(
        model=shared_model,
        system_prompt=system_prompt,
        tools=skill_tools + service_tools,
        callback_handler=None,  # stream_async yields events directly
        messages=strands_history,
        trace_attributes=build_trace_attrs(
            tenant_id=tenant_id,
            user_id=user_id,
            tier=tier,
            session_id=session_id or "",
            username=username or "",
        ),
    )

    # Yield chunks via stream_async — SDK bridges sync→async internally
    _agent_start = _time.perf_counter()
    full_text_parts: list[str] = []
    tools_called: list[str] = []
    _current_tool_id: str | None = None
    error_holder: list[Exception] = []
    agent_result = None

    def _drain_tool_results() -> list[dict]:
        """Drain tool results that were pushed by factory tools via result_queue."""
        drained: list[dict] = []
        while True:
            try:
                item = result_queue.get_nowait()
                name = item.get("name")
                if not name:
                    continue
                tools_called.append(name)
                drained.append(item)
            except asyncio.QueueEmpty:
                break
        return drained

    # Signal that agent setup is done and we're waiting on Bedrock inference
    yield {"type": "agent_status", "status": "Waiting for model...", "detail": "inference"}

    try:
        async for event in supervisor.stream_async(prompt):
            # Drain tool results that may have been pushed by factory tools
            for tool_result_chunk in _drain_tool_results():
                yield tool_result_chunk

            # --- Text streaming ---
            data = event.get("data")
            if data and isinstance(data, str):
                full_text_parts.append(data)
                yield {"type": "text", "data": data}
                continue

            # --- Tool use start (ToolUseStreamEvent) ---
            current_tool = event.get("current_tool_use")
            if current_tool and isinstance(current_tool, dict):
                tool_id = current_tool.get("toolUseId", "")
                if tool_id and tool_id != _current_tool_id:
                    _current_tool_id = tool_id
                    tool_name = current_tool.get("name", "")
                    tool_input = current_tool.get("input", "")
                    tools_called.append(tool_name)
                    yield {
                        "type": "tool_use",
                        "name": tool_name,
                        "input": tool_input,
                        "tool_use_id": tool_id,
                    }
                    # Emit human-readable status for this tool
                    from .telemetry.status_messages import get_tool_status_message

                    input_dict = tool_input if isinstance(tool_input, dict) else {}
                    status_msg = get_tool_status_message(tool_name, input_dict)
                    yield {"type": "agent_status", "status": status_msg, "detail": tool_name}
                continue

            # --- Bedrock contentBlockStart fallback ---
            tool_use = event.get("event", {})
            if isinstance(tool_use, dict):
                tool_use = tool_use.get("contentBlockStart", {}).get("start", {}).get("toolUse")
                if tool_use:
                    tool_id = tool_use.get("toolUseId", "")
                    if tool_id != _current_tool_id:
                        _current_tool_id = tool_id
                        tool_name = tool_use.get("name", "")
                        tools_called.append(tool_name)
                        yield {
                            "type": "tool_use",
                            "name": tool_name,
                            "tool_use_id": tool_id,
                        }
                        from .telemetry.status_messages import get_tool_status_message

                        status_msg = get_tool_status_message(tool_name)
                        yield {"type": "agent_status", "status": status_msg, "detail": tool_name}
                    continue

            # --- Agent result (final event) ---
            if "result" in event and hasattr(event.get("result"), "metrics"):
                agent_result = event["result"]

    except Exception as exc:
        error_holder.append(exc)
        logger.error("stream_async error: %s", exc)
        # Classify and tag the Langfuse trace for filtering
        from .telemetry.langfuse_client import notify_trace_error

        notify_trace_error(session_id or "", str(exc))

    # Final drain of any remaining tool results
    for tool_result_chunk in _drain_tool_results():
        yield tool_result_chunk

    # Extract usage from result
    usage = {}
    if agent_result is not None:
        if not full_text_parts:
            try:
                final_text = str(agent_result)
                if final_text:
                    full_text_parts.append(final_text)
                    yield {"type": "text", "data": final_text}
            except Exception:
                pass
        try:
            metrics = getattr(agent_result, "metrics", None)
            if metrics:
                acc = getattr(metrics, "accumulated_usage", None)
                if acc and isinstance(acc, dict):
                    usage = acc
                else:
                    usage = {
                        "cycle_count": getattr(metrics, "cycle_count", 0),
                        "tools_called": len(tools_called),
                    }
                if hasattr(metrics, "tool_metrics"):
                    tools_called = list(metrics.tool_metrics.keys())
        except Exception:
            pass

    forced_doc = None
    if not error_holder:
        forced_doc = await ensure_create_document_for_direct_request(
            prompt=prompt,
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            package_context=package_context,
            tools_called=tools_called,
        )
        if forced_doc is not None:
            tools_called.append("create_document")
            yield {"type": "tool_use", "name": "create_document"}
            yield {"type": "tool_result", "name": "create_document", "result": forced_doc["result"]}
            # Emit package state update for forced document creation
            for state_evt in build_state_updates(forced_doc["result"], "create_document", tenant_id):
                yield state_evt
            if not full_text_parts:
                summary = (
                    f"Generated a draft {forced_doc['doc_type'].replace('_', ' ')} document. "
                    "Open the document card to review or edit it."
                )
                full_text_parts.append(summary)
                yield {"type": "text", "data": summary}

    # Emit agent.timing telemetry to CloudWatch
    _agent_duration_ms = int((_time.perf_counter() - _agent_start) * 1000)
    try:
        from .telemetry.cloudwatch_emitter import emit_telemetry_event

        emit_telemetry_event(
            event_type="agent.timing",
            tenant_id=tenant_id,
            data={
                "agent_name": "supervisor",
                "duration_ms": _agent_duration_ms,
                "tools_called": tools_called,
                "session_id": session_id or "",
            },
            session_id=session_id,
            user_id=user_id,
        )
    except Exception:
        logger.debug("Failed to emit agent.timing telemetry", exc_info=True)

    # End-of-turn state refresh — always emit latest package state
    for state_evt in build_end_of_turn_state(package_context, tenant_id):
        yield state_evt

    if error_holder:
        yield {"type": "error", "error": str(error_holder[0])}
    else:
        final_text = "".join(full_text_parts)
        if not final_text.strip():
            called = ", ".join(tools_called[:3]) if tools_called else "none"
            final_text = (
                "I completed the tool steps but did not receive a final answer text. "
                f"Tools called: {called}. Please retry your request."
            )
        yield {
            "type": "complete",
            "text": final_text,
            "tools_called": tools_called,
            "usage": usage,
        }


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

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S UTC")
    tenant_context = (
        f"Tenant: {tenant_id} | User: {user_id} | Tier: {tier} | Current datetime: {now_utc}\n"
        f"You are operating as the {skill_name} specialist for this tenant.\n\n"
    )

    ensure_langfuse_exporter()
    agent = Agent(
        model=shared_model,
        system_prompt=tenant_context + skill_content,
        callback_handler=None,
        trace_attributes=build_trace_attrs(
            tenant_id=tenant_id,
            user_id=user_id,
            tier=tier,
            subagent=skill_name,
        ),
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
