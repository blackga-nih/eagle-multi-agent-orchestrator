# Telemetry Implementation Plan — Claude SDK Native

> **Status**: Proposed
> **Author**: Claude Code
> **Date**: 2026-02-20
> **Supersedes**: `docs/OBSERVABILITY_PLAN.md` (Langfuse-based approach)

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Design Principle: SDK-Native, Zero New Dependencies](#design-principle)
3. [What the SDK Already Provides](#what-the-sdk-already-provides)
4. [Architecture](#architecture)
5. [Implementation Phases](#implementation-phases)
6. [Phase 1: Promote TraceCollector to Production](#phase-1-promote-tracecollector-to-production)
7. [Phase 2: SDK Hooks for Real-Time Telemetry](#phase-2-sdk-hooks-for-real-time-telemetry)
8. [Phase 3: User-Facing Status Events (SSE)](#phase-3-user-facing-status-events-sse)
9. [Phase 4: DynamoDB Trace Persistence](#phase-4-dynamodb-trace-persistence)
10. [Phase 5: Admin Trace Viewer](#phase-5-admin-trace-viewer)
11. [Phase 6: CloudWatch Structured Logging](#phase-6-cloudwatch-structured-logging)
12. [Phase 7: Test Harness Integration](#phase-7-test-harness-integration)
13. [File Changes Summary](#file-changes-summary)
14. [Data Model](#data-model)
15. [Testing Strategy](#testing-strategy)
16. [Estimated Effort](#estimated-effort)
17. [Open Questions](#open-questions)

---

## Executive Summary

This plan adds comprehensive observability to the EAGLE multi-tenant agent application using **only Claude Agent SDK built-in primitives** and **existing AWS infrastructure** (DynamoDB, CloudWatch). No new external dependencies are introduced.

- **For Users**: Real-time status updates in chat showing what agents are doing
- **For Developers/Admins**: Full trace visibility via in-app admin panel and CloudWatch
- **For Operations**: Cost tracking, latency metrics, and error monitoring per tenant
- **Zero new dependencies**: No Langfuse, no OpenTelemetry, no new pip packages

---

## Design Principle

### SDK-Native, Zero New Dependencies

The previous plan proposed Langfuse as the telemetry backend. After evaluating the Claude Agent SDK's built-in capabilities, **~60% of what Langfuse provides is already available natively**:

| Capability | SDK Built-In | Previous Plan (Langfuse) |
|---|---|---|
| Token usage | `ResultMessage.usage` dict | Langfuse generation tracking |
| Cost tracking | `ResultMessage.total_cost_usd` | Langfuse cost calculation |
| Tool call lifecycle | `PreToolUse` / `PostToolUse` hooks | Langfuse spans |
| Subagent lifecycle | `SubagentStart` / `SubagentStop` hooks | Langfuse nested spans |
| Subagent nesting | `parent_tool_use_id` on messages | Langfuse parent observation |
| Session grouping | `session_id` from System/ResultMessage | Langfuse sessions |
| Trace serialization | `TraceCollector.to_trace_json()` | Langfuse trace API |
| Persistent storage | DynamoDB (already deployed) | Langfuse cloud/self-hosted |
| Log querying | CloudWatch (already integrated) | Langfuse dashboard |
| Dashboard | Build in-app (Phase 5) | Langfuse web UI |

### What we give up vs Langfuse

| Feature | Mitigation |
|---|---|
| Pre-built dashboard | Build a focused admin page (Phase 5) |
| Prompt/completion viewer | Store in DynamoDB, view in admin page |
| Cross-session analytics | CloudWatch Insights queries |
| Model comparison | DynamoDB queries by model field |

### What we gain

- No external service dependency
- No data leaving AWS infrastructure
- No new credentials/env vars to manage
- No additional pip dependency (`langfuse>=2.0.0`)
- Consistent with existing DynamoDB + CloudWatch patterns

---

## What the SDK Already Provides

### 1. Message-Level Telemetry

Every `query()` call yields structured messages with full telemetry:

```python
# ResultMessage (final message per query)
message.usage        # dict: input_tokens, output_tokens, cache_*_tokens
message.total_cost_usd  # float: computed cost
message.session_id   # str: session identifier
message.result       # str: final text output
```

### 2. Hook System (7 Event Types)

| Hook Event | When Fired | Telemetry Use |
|---|---|---|
| `PreToolUse` | Before tool execution | Start tool span, emit user status |
| `PostToolUse` | After tool execution | End tool span, record duration |
| `SubagentStart` | When subagent begins | Start agent span, emit user status |
| `SubagentStop` | When subagent finishes | End agent span, record tokens |
| `Stop` | When agent decides to stop | Record completion |
| `UserPromptSubmit` | When user prompt received | Input validation |
| `PreCompact` | Before context compaction | Pre-compaction metrics |

### 3. TraceCollector (Already Built)

`server/tests/test_eagle_sdk_eval.py:144-330` contains a production-quality `TraceCollector` that:
- Categorizes all SDK message types
- Extracts `session_id` from both `SystemMessage` and `ResultMessage`
- Accumulates token usage across multiple `ResultMessage` yields
- Tracks `tool_use_blocks` with name, ID, and input
- Detects subagent context via `parent_tool_use_id`
- Serializes full conversation traces to JSON via `to_trace_json()`
- Produces summary dicts via `summary()`

---

## Architecture

### High-Level Flow

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         User Chat Interface                              │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │ User: "Create a SOW document for the cloud migration project"     │  │
│  │                                                                   │  │
│  │ ⏳ Analyzing requirements...                                      │  │
│  │ ⏳ Legal Counsel is reviewing compliance...                       │  │
│  │ ⏳ Searching FAR/DFARS regulations...                             │  │
│  │ ✓ Knowledge Search complete (312ms)                               │  │
│  │ ✓ Legal Counsel complete (1.1s)                                   │  │
│  │ ⏳ Document Generator is creating SOW...                          │  │
│  │ ✓ Document Generator complete (523ms)                             │  │
│  │                                                                   │  │
│  │ Assistant: I've created the Statement of Work document...        │  │
│  └───────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘
                │
                │ SSE Stream (includes AGENT_STATUS events)
                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                       FastAPI Backend                                    │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │              sdk_agentic_service.py                               │   │
│  │                                                                   │   │
│  │  SDK Hooks (TelemetryHooks class):                                │   │
│  │  ┌─────────────────────────────────────────────────────────────┐ │   │
│  │  │ SubagentStart → trace.start_span("agent.legal-counsel")    │ │   │
│  │  │              → emit_status("Legal Counsel analyzing...")    │ │   │
│  │  ├─────────────────────────────────────────────────────────────┤ │   │
│  │  │ PreToolUse   → trace.start_span("tool.search_far")         │ │   │
│  │  │              → emit_status("Searching FAR...")              │ │   │
│  │  ├─────────────────────────────────────────────────────────────┤ │   │
│  │  │ PostToolUse  → trace.end_span(output, duration)            │ │   │
│  │  │              → emit_status("Search complete", "complete")   │ │   │
│  │  ├─────────────────────────────────────────────────────────────┤ │   │
│  │  │ SubagentStop → trace.end_span(tokens, cost)                │ │   │
│  │  │              → emit_status("Legal Counsel done", "complete")│ │   │
│  │  └─────────────────────────────────────────────────────────────┘ │   │
│  │                                                                   │   │
│  │  TraceCollector: accumulates all messages → trace JSON            │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                │                          │                              │
│                ▼                          ▼                              │
│  ┌────────────────────┐    ┌────────────────────────┐                  │
│  │   DynamoDB (eagle)  │    │   CloudWatch Logs       │                  │
│  │                     │    │   /eagle/telemetry       │                  │
│  │ TRACE#<trace_id>    │    │                          │                  │
│  │ ├─ metadata         │    │ Structured JSON events:  │                  │
│  │ ├─ spans[]          │    │ ├─ trace.started         │                  │
│  │ ├─ usage            │    │ ├─ tool.completed        │                  │
│  │ └─ cost             │    │ ├─ agent.delegated       │                  │
│  └────────────────────┘    │ └─ trace.completed       │                  │
│                             └────────────────────────┘                  │
└──────────────────────────────────────────────────────────────────────────┘
```

### Trace Structure (SDK-Native)

```
TraceCollector output for a single chat request:

trace_id: "t-1708420245-a1b2c3d4"
session_id: "s-1708420200-xyz"
tenant_id: "acme-corp"
user_id: "user-123"

messages: [
  { type: "SystemMessage", session_id: "s-..." }

  { type: "AssistantMessage", blocks: [
      { type: "TextBlock", text: "I'll help you create..." },
      { type: "ToolUseBlock", name: "Task", input: { subagent: "legal-counsel" } }
  ]}

  { type: "AssistantMessage", parent_tool_use_id: "toolu_bdrk_...", blocks: [
      { type: "ToolUseBlock", name: "search_far", input: { query: "cloud" } }
  ]}

  { type: "UserMessage", blocks: [
      { type: "ToolResultBlock", tool_use_id: "toolu_bdrk_...", content: "..." }
  ]}

  { type: "ResultMessage",
    usage: { input_tokens: 1234, output_tokens: 567 },
    total_cost_usd: 0.0045
  }
]

spans: [
  { name: "agent.legal-counsel", start_ms: 0, end_ms: 1100, parent: null }
  { name: "tool.search_far", start_ms: 200, end_ms: 512, parent: "agent.legal-counsel" }
  { name: "agent.document-generator", start_ms: 1100, end_ms: 1623, parent: null }
  { name: "tool.create_document", start_ms: 1100, end_ms: 1623, parent: "agent.document-generator" }
]

summary: {
  total_input_tokens: 1830,
  total_output_tokens: 567,
  total_cost_usd: 0.0045,
  duration_ms: 2340,
  tools_called: ["search_far", "create_document"],
  agents_delegated: ["legal-counsel", "document-generator"]
}
```

---

## Implementation Phases

### Overview

| Phase | Description | Hours | Dependencies |
|---|---|---|---|
| 1 | Promote TraceCollector to production | 1-2 | None |
| 2 | SDK hooks for real-time telemetry | 2-3 | Phase 1 |
| 3 | User-facing status events (SSE) | 2-3 | Phase 2 |
| 4 | DynamoDB trace persistence | 2-3 | Phase 1 |
| 5 | Admin trace viewer | 3-4 | Phase 4 |
| 6 | CloudWatch structured logging | 1-2 | Phase 1 |
| 7 | Test harness integration | 1-2 | Phase 1 |
| **Total** | | **12-19** | |

---

## Phase 1: Promote TraceCollector to Production

**Goal**: Move `TraceCollector` from test code to a shared production module.

**Source**: `server/tests/test_eagle_sdk_eval.py:144-330`

**New File**: `server/app/telemetry/__init__.py`

```python
"""
SDK-Native Telemetry Module

Zero external dependencies. Uses Claude Agent SDK message types,
hooks, and existing AWS infrastructure (DynamoDB, CloudWatch).
"""
from .trace_collector import TraceCollector
from .span_tracker import SpanTracker
from .status_messages import (
    AGENT_DISPLAY_NAMES,
    SKILL_DISPLAY_NAMES,
    TOOL_STATUS_MESSAGES,
    get_tool_status_message,
    get_agent_display_name,
)

__all__ = [
    "TraceCollector",
    "SpanTracker",
    "AGENT_DISPLAY_NAMES",
    "SKILL_DISPLAY_NAMES",
    "TOOL_STATUS_MESSAGES",
    "get_tool_status_message",
    "get_agent_display_name",
]
```

**New File**: `server/app/telemetry/trace_collector.py`

Extracted and refined from `test_eagle_sdk_eval.py:144-330`:

```python
"""
TraceCollector — SDK-native trace accumulation.

Processes all Claude Agent SDK message types, extracts telemetry,
and serializes to JSON for persistence and display.
"""
import json
import time
import logging
from typing import Any, Optional

logger = logging.getLogger("eagle.telemetry")


class TraceCollector:
    """Collects and categorizes SDK message traces.

    Usage:
        collector = TraceCollector(tenant_id="acme", user_id="user-1")
        async for message in query(prompt="...", options=options):
            collector.process(message)

        # After query completes:
        summary = collector.summary()
        trace_json = collector.to_trace_json()
    """

    def __init__(self, tenant_id: str = "default", user_id: str = "anonymous"):
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.trace_id = f"t-{int(time.time() * 1000)}"
        self.start_time = time.time()

        # Message accumulation
        self.messages = []
        self.text_blocks = []
        self.thinking_blocks = []
        self.tool_use_blocks = []
        self.result_messages = []
        self.system_messages = []

        # Telemetry counters
        self.session_id: Optional[str] = None
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cost_usd = 0.0

        # Agent/tool tracking
        self.agents_delegated: list[str] = []
        self.tools_called: list[str] = []

    def process(self, message, indent: int = 0):
        """Process a single SDK message, extracting telemetry data."""
        msg_type = type(message).__name__
        self.messages.append({"type": msg_type, "message": message})

        if msg_type == "SystemMessage":
            self._process_system(message)
        elif msg_type == "ResultMessage":
            self._process_result(message)
        else:
            self._process_content(message, msg_type)

    def _process_system(self, message):
        if hasattr(message, "data") and isinstance(message.data, dict):
            sid = message.data.get("session_id")
            if sid:
                self.session_id = sid
        self.system_messages.append(message)

    def _process_result(self, message):
        if hasattr(message, "session_id") and message.session_id:
            self.session_id = message.session_id

        if hasattr(message, "usage") and message.usage is not None:
            usage = message.usage
            if isinstance(usage, dict):
                input_t = usage.get("input_tokens", 0) or 0
                output_t = usage.get("output_tokens", 0) or 0
                cache_create = usage.get("cache_creation_input_tokens", 0) or 0
                cache_read = usage.get("cache_read_input_tokens", 0) or 0
            else:
                input_t = getattr(usage, "input_tokens", 0) or 0
                output_t = getattr(usage, "output_tokens", 0) or 0
                cache_create = getattr(usage, "cache_creation_input_tokens", 0) or 0
                cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0

            self.total_input_tokens += input_t + cache_create + cache_read
            self.total_output_tokens += output_t
            self.result_messages.append({
                "input_tokens": input_t,
                "output_tokens": output_t,
                "cache_creation_input_tokens": cache_create,
                "cache_read_input_tokens": cache_read,
            })

        cost = getattr(message, "total_cost_usd", None)
        if cost is not None:
            self.total_cost_usd += cost

    def _process_content(self, message, msg_type):
        if not hasattr(message, "content") or message.content is None:
            return
        for block in message.content:
            block_class = type(block).__name__
            if block_class == "TextBlock":
                text = getattr(block, "text", "")
                if text.strip():
                    self.text_blocks.append(text)
            elif block_class == "ThinkingBlock":
                thinking = getattr(block, "thinking", getattr(block, "text", ""))
                self.thinking_blocks.append(thinking)
            elif block_class == "ToolUseBlock":
                name = getattr(block, "name", "?")
                tool_id = getattr(block, "id", "?")
                inp = getattr(block, "input", {})
                self.tool_use_blocks.append({"tool": name, "id": tool_id, "input": inp})
                if name == "Task":
                    subagent = inp.get("subagent_type", inp.get("description", "?"))
                    if subagent not in self.agents_delegated:
                        self.agents_delegated.append(subagent)
                else:
                    if name not in self.tools_called:
                        self.tools_called.append(name)

        # Track subagent context
        if hasattr(message, "parent_tool_use_id") and message.parent_tool_use_id:
            pass  # Nesting info preserved in to_trace_json()

    def summary(self) -> dict:
        """Return a summary dict suitable for DynamoDB or logging."""
        elapsed_ms = int((time.time() - self.start_time) * 1000)
        return {
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "total_messages": len(self.messages),
            "text_blocks": len(self.text_blocks),
            "tool_use_blocks": len(self.tool_use_blocks),
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cost_usd": self.total_cost_usd,
            "duration_ms": elapsed_ms,
            "tools_called": self.tools_called,
            "agents_delegated": self.agents_delegated,
        }

    def to_trace_json(self) -> list:
        """Serialize the full conversation trace to a JSON-safe list."""
        trace = []
        for entry in self.messages:
            msg_type = entry["type"]
            message = entry["message"]
            item: dict[str, Any] = {"type": msg_type}

            if msg_type == "SystemMessage":
                if hasattr(message, "data") and isinstance(message.data, dict):
                    item["session_id"] = message.data.get("session_id")
            elif msg_type == "ResultMessage":
                item["result"] = getattr(message, "result", None)
                item["session_id"] = getattr(message, "session_id", None)
                cost = getattr(message, "total_cost_usd", None)
                if cost is not None:
                    item["cost_usd"] = cost
                usage = getattr(message, "usage", None)
                if usage is not None:
                    item["usage"] = usage if isinstance(usage, dict) else {
                        "input_tokens": getattr(usage, "input_tokens", 0) or 0,
                        "output_tokens": getattr(usage, "output_tokens", 0) or 0,
                    }
            else:
                blocks = []
                if hasattr(message, "content") and message.content:
                    for block in message.content:
                        bc = type(block).__name__
                        if bc == "TextBlock":
                            blocks.append({"type": "text", "text": getattr(block, "text", "")[:500]})
                        elif bc == "ToolUseBlock":
                            blocks.append({
                                "type": "tool_use",
                                "name": getattr(block, "name", ""),
                                "id": getattr(block, "id", ""),
                                "input": getattr(block, "input", {}),
                            })
                        elif bc == "ToolResultBlock":
                            content = getattr(block, "content", "")
                            blocks.append({
                                "type": "tool_result",
                                "tool_use_id": getattr(block, "tool_use_id", ""),
                                "content": str(content)[:500],
                            })
                item["blocks"] = blocks

                if hasattr(message, "parent_tool_use_id") and message.parent_tool_use_id:
                    item["parent_tool_use_id"] = message.parent_tool_use_id

            trace.append(item)
        return trace
```

**Changes to existing test file**: Update `server/tests/test_eagle_sdk_eval.py` to import from `app.telemetry` instead of defining `TraceCollector` inline:

```python
# Replace the inline TraceCollector class (lines 144-330) with:
from app.telemetry import TraceCollector
```

---

## Phase 2: SDK Hooks for Real-Time Telemetry

**Goal**: Use SDK hook system to capture tool/agent lifecycle events with timing.

**New File**: `server/app/telemetry/span_tracker.py`

```python
"""
SpanTracker — Lightweight span tracking using SDK hooks.

No external dependencies. Uses SDK PreToolUse/PostToolUse/SubagentStart/SubagentStop
hooks to build a span tree with timing data.
"""
import time
import logging
from typing import Optional, Callable, Awaitable
from dataclasses import dataclass, field, asdict

logger = logging.getLogger("eagle.telemetry.spans")


@dataclass
class Span:
    """A single timed operation span."""
    name: str
    span_type: str  # "tool" | "agent"
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    duration_ms: Optional[int] = None
    input_data: Optional[dict] = None
    output_data: Optional[str] = None
    parent_id: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def end(self, output: Optional[str] = None, **meta):
        self.end_time = time.time()
        self.duration_ms = int((self.end_time - self.start_time) * 1000)
        if output:
            self.output_data = output[:2000]
        self.metadata.update(meta)

    def to_dict(self) -> dict:
        d = asdict(self)
        # Remove raw timestamps, keep duration
        d.pop("start_time", None)
        d.pop("end_time", None)
        return {k: v for k, v in d.items() if v is not None}


# Callback type for status emission
StatusCallback = Callable[..., Awaitable[None]]


class SpanTracker:
    """Tracks active spans from SDK hook events.

    Usage:
        tracker = SpanTracker(on_status=emit_status_callback)

        # Register hooks with SDK:
        options = ClaudeAgentOptions(
            hooks=tracker.get_hook_matchers(),
            ...
        )

        # After query, retrieve spans:
        spans = tracker.get_completed_spans()
    """

    def __init__(self, on_status: Optional[StatusCallback] = None):
        self.on_status = on_status
        self._active_spans: dict[str, Span] = {}
        self._completed_spans: list[Span] = []

    async def on_subagent_start(self, input, tool_use_id: str, ctx):
        """SDK SubagentStart hook callback."""
        agent_name = getattr(input, "agent_name", "unknown")

        span = Span(
            name=f"agent.{agent_name}",
            span_type="agent",
            input_data={"agent": agent_name},
        )
        self._active_spans[tool_use_id] = span

        if self.on_status:
            await self.on_status(
                agent_name=agent_name,
                message="Analyzing...",
                status="in_progress",
            )

        return {"continue_": True}

    async def on_subagent_stop(self, input, tool_use_id: str, ctx):
        """SDK SubagentStop hook callback."""
        span = self._active_spans.pop(tool_use_id, None)
        if not span:
            return {"continue_": True}

        result = getattr(input, "result", None)
        span.end(
            output=str(result)[:2000] if result else None,
            input_tokens=getattr(input, "input_tokens", 0),
            output_tokens=getattr(input, "output_tokens", 0),
        )
        self._completed_spans.append(span)

        agent_name = span.input_data.get("agent", "unknown") if span.input_data else "unknown"
        if self.on_status:
            await self.on_status(
                agent_name=agent_name,
                message=f"Complete ({span.duration_ms}ms)",
                status="complete",
            )

        return {"continue_": True}

    async def on_pre_tool_use(self, input, tool_use_id: str, ctx):
        """SDK PreToolUse hook callback."""
        tool_name = getattr(input, "tool_name", "unknown")
        tool_input = getattr(input, "tool_input", {})

        span = Span(
            name=f"tool.{tool_name}",
            span_type="tool",
            input_data=tool_input if isinstance(tool_input, dict) else {"raw": str(tool_input)[:500]},
        )
        self._active_spans[tool_use_id] = span

        if self.on_status:
            from .status_messages import get_tool_status_message
            message = get_tool_status_message(tool_name, tool_input)
            await self.on_status(
                agent_name=tool_name,
                message=message,
                status="in_progress",
            )

        return {"continue_": True, "decision": None, "hookSpecificOutput": None}

    async def on_post_tool_use(self, input, tool_use_id: str, ctx):
        """SDK PostToolUse hook callback."""
        span = self._active_spans.pop(tool_use_id, None)
        if not span:
            return {"continue_": True, "hookSpecificOutput": None}

        result = getattr(input, "tool_result", None)
        span.end(output=str(result)[:2000] if result else None)
        self._completed_spans.append(span)

        tool_name = span.name.replace("tool.", "")
        if self.on_status:
            await self.on_status(
                agent_name=tool_name,
                message=f"Complete ({span.duration_ms}ms)",
                status="complete",
            )

        return {"continue_": True, "hookSpecificOutput": None}

    def get_hook_matchers(self) -> list:
        """Return HookMatcher list for ClaudeAgentOptions.hooks."""
        from claude_agent_sdk import HookMatcher

        return [
            HookMatcher(matcher="SubagentStart", hooks=[self.on_subagent_start], timeout=5000),
            HookMatcher(matcher="SubagentStop", hooks=[self.on_subagent_stop], timeout=5000),
            HookMatcher(matcher="PreToolUse", hooks=[self.on_pre_tool_use], timeout=5000),
            HookMatcher(matcher="PostToolUse", hooks=[self.on_post_tool_use], timeout=5000),
        ]

    def get_completed_spans(self) -> list[dict]:
        """Return all completed spans as dicts."""
        return [s.to_dict() for s in self._completed_spans]
```

**New File**: `server/app/telemetry/status_messages.py`

```python
"""
Human-readable status messages for agents and tools.

Maps internal agent/tool names to user-friendly display names
and contextual status messages.
"""

AGENT_DISPLAY_NAMES = {
    "supervisor": "EAGLE Assistant",
    "legal-counsel": "Legal Counsel",
    "market-intelligence": "Market Intelligence",
    "tech-translator": "Technical Translator",
    "public-interest": "Public Interest Advisor",
    "policy-supervisor": "Policy Supervisor",
    "policy-librarian": "Policy Librarian",
    "policy-analyst": "Policy Analyst",
}

SKILL_DISPLAY_NAMES = {
    "oa-intake": "Intake Workflow",
    "document-generator": "Document Generator",
    "compliance": "Compliance Checker",
    "knowledge-retrieval": "Knowledge Search",
    "tech-review": "Technical Review",
}

TOOL_STATUS_MESSAGES = {
    "s3_document_ops": {
        "list": "Listing documents...",
        "read": "Reading document...",
        "write": "Saving document...",
        "_default": "Accessing documents...",
    },
    "dynamodb_intake": {
        "get": "Loading intake data...",
        "put": "Saving intake data...",
        "query": "Querying records...",
        "_default": "Accessing intake data...",
    },
    "search_far": "Searching FAR/DFARS regulations...",
    "create_document": {
        "sow": "Generating Statement of Work...",
        "igce": "Generating Cost Estimate...",
        "market_research": "Generating Market Research...",
        "ja": "Generating Justification & Approval...",
        "_default": "Generating document...",
    },
    "cloudwatch_logs": "Querying logs...",
    "intake_workflow": {
        "start": "Starting intake workflow...",
        "advance": "Advancing to next phase...",
        "complete": "Completing intake...",
        "_default": "Processing intake...",
    },
}


def get_tool_status_message(tool_name: str, tool_input: dict = None) -> str:
    """Get a human-readable status message for a tool invocation."""
    entry = TOOL_STATUS_MESSAGES.get(tool_name)
    if entry is None:
        return f"Running {tool_name}..."
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict) and tool_input:
        # Try operation/doc_type/action keys
        for key in ("operation", "doc_type", "action", "type"):
            val = tool_input.get(key)
            if val and val in entry:
                return entry[val]
        return entry.get("_default", f"Running {tool_name}...")
    return f"Running {tool_name}..."


def get_agent_display_name(agent_name: str) -> str:
    """Get a human-readable display name for an agent."""
    return (
        AGENT_DISPLAY_NAMES.get(agent_name)
        or SKILL_DISPLAY_NAMES.get(agent_name)
        or agent_name.replace("-", " ").title()
    )
```

**Modify**: `server/app/sdk_agentic_service.py`

Wire hooks into `sdk_query()`:

```python
from app.telemetry import TraceCollector, SpanTracker

async def sdk_query(
    prompt: str,
    session_id: str = None,
    tenant_id: str = "demo-tenant",
    user_id: str = "demo-user",
    tier: str = "advanced",
    on_status=None,  # NEW: status callback for SSE
    **kwargs
) -> AsyncGenerator:
    # Create telemetry objects
    collector = TraceCollector(tenant_id=tenant_id, user_id=user_id)
    span_tracker = SpanTracker(on_status=on_status)

    agents = build_skill_agents(tier=tier)
    system_prompt = build_supervisor_prompt(tenant_id, user_id, tier)

    options = ClaudeAgentOptions(
        model=MODEL,
        system_prompt=system_prompt,
        allowed_tools=["Task"],
        agents=agents,
        permission_mode="bypassPermissions",
        max_turns=15,
        max_budget_usd=TIER_BUDGETS.get(tier, 0.25),
        hooks=span_tracker.get_hook_matchers(),  # ADD HOOKS
        cwd=os.path.dirname(os.path.abspath(__file__)),
        env={"CLAUDE_CODE_USE_BEDROCK": "1", "AWS_REGION": "us-east-1"},
    )

    async for message in query(prompt=prompt, options=options):
        collector.process(message)
        yield message

    # After query: persist telemetry
    summary = collector.summary()
    summary["spans"] = span_tracker.get_completed_spans()
    # Phase 4 will persist this to DynamoDB
    # Phase 6 will log this to CloudWatch
```

---

## Phase 3: User-Facing Status Events (SSE)

**Goal**: Add `AGENT_STATUS` event type to the existing SSE stream protocol.

**Modify**: `server/app/stream_protocol.py`

Add new event type to existing `StreamEventType` enum and a convenience method to `MultiAgentStreamWriter`:

```python
class StreamEventType(str, Enum):
    TEXT = "text"
    REASONING = "reasoning"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    ELICITATION = "elicitation"
    METADATA = "metadata"
    COMPLETE = "complete"
    ERROR = "error"
    HANDOFF = "handoff"
    AGENT_STATUS = "agent_status"  # NEW


# Add to MultiAgentStreamWriter:
async def write_agent_status(
    self,
    queue,
    agent_name: str,
    message: str,
    status: str = "in_progress",
):
    """Emit an AGENT_STATUS event for real-time user feedback."""
    from app.telemetry.status_messages import get_agent_display_name

    event = self._create_event(
        StreamEventType.AGENT_STATUS,
        metadata={
            "agent_name": agent_name,
            "display_name": get_agent_display_name(agent_name),
            "message": message,
            "status": status,  # "in_progress" | "complete" | "error"
        },
    )
    await queue.put(event.to_sse())
```

**Modify**: `client/types/stream.ts`

Add `agent_status` to the existing `StreamEventType` union:

```typescript
export type StreamEventType =
  | 'text'
  | 'reasoning'
  | 'tool_use'
  | 'tool_result'
  | 'elicitation'
  | 'metadata'
  | 'complete'
  | 'error'
  | 'handoff'
  | 'user_input'
  | 'form_submit'
  | 'agent_status';  // NEW
```

**New File**: `client/components/chat/AgentStatus.tsx`

```tsx
import { Loader2, Check, X } from "lucide-react";

interface AgentStatusProps {
  displayName: string;
  message: string;
  status: "in_progress" | "complete" | "error";
}

export function AgentStatus({ displayName, message, status }: AgentStatusProps) {
  const Icon = {
    in_progress: Loader2,
    complete: Check,
    error: X,
  }[status];

  const iconClass = {
    in_progress: "animate-spin text-muted-foreground",
    complete: "text-green-500",
    error: "text-red-500",
  }[status];

  return (
    <div className="flex items-center gap-2 text-sm text-muted-foreground py-1 px-2 bg-muted/50 rounded">
      <Icon className={`h-3 w-3 ${iconClass}`} />
      <span className="font-medium">{displayName}:</span>
      <span>{message}</span>
    </div>
  );
}
```

**Modify**: `client/hooks/use-agent-stream.ts`

Add `agent_status` handling to the existing SSE event switch:

```typescript
// In the SSE event handler, add case for agent_status:
case 'agent_status': {
  const statusData = event.metadata;
  if (statusData && onEvent) {
    onEvent(event);  // Forward to parent for rendering
  }
  break;
}
```

---

## Phase 4: DynamoDB Trace Persistence

**Goal**: Store trace summaries in the existing `eagle` DynamoDB table.

**New File**: `server/app/telemetry/trace_store.py`

```python
"""
DynamoDB persistence for trace summaries.

Uses the existing 'eagle' table with TRACE# partition key prefix.
No new tables required.
"""
import os
import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any

import boto3
from botocore.exceptions import ClientError, BotoCoreError

logger = logging.getLogger("eagle.telemetry.store")

TABLE_NAME = os.getenv("EAGLE_SESSIONS_TABLE", "eagle")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
TRACE_TTL_DAYS = int(os.getenv("TRACE_TTL_DAYS", "30"))

_dynamodb = None


def _get_table():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
    return _dynamodb.Table(TABLE_NAME)


def store_trace(summary: dict, spans: list, trace_json: list = None) -> bool:
    """Persist a trace summary + spans to DynamoDB.

    Key schema:
        PK: TRACE#{tenant_id}
        SK: TRACE#{date}#{trace_id}
    GSI1:
        GSI1PK: SESSION#{session_id}
        GSI1SK: TRACE#{trace_id}
    """
    trace_id = summary.get("trace_id", "unknown")
    tenant_id = summary.get("tenant_id", "default")
    session_id = summary.get("session_id", "unknown")
    now = datetime.utcnow()
    ttl = int((now + timedelta(days=TRACE_TTL_DAYS)).timestamp())

    item = {
        "PK": f"TRACE#{tenant_id}",
        "SK": f"TRACE#{now.strftime('%Y-%m-%d')}#{trace_id}",
        "trace_id": trace_id,
        "tenant_id": tenant_id,
        "user_id": summary.get("user_id", "anonymous"),
        "session_id": session_id,
        "created_at": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "duration_ms": summary.get("duration_ms", 0),
        "total_input_tokens": summary.get("total_input_tokens", 0),
        "total_output_tokens": summary.get("total_output_tokens", 0),
        "total_cost_usd": Decimal(str(summary.get("total_cost_usd", 0))),
        "tools_called": summary.get("tools_called", []),
        "agents_delegated": summary.get("agents_delegated", []),
        "span_count": len(spans),
        "spans": json.dumps(spans, default=str),
        "status": "success" if not summary.get("error") else "error",
        "ttl": ttl,
        # GSI for lookup by session
        "GSI1PK": f"SESSION#{session_id}",
        "GSI1SK": f"TRACE#{trace_id}",
    }

    # Optionally store full trace (truncated to stay under 400KB DynamoDB limit)
    if trace_json:
        trace_str = json.dumps(trace_json, default=str)
        if len(trace_str) < 350_000:  # Leave headroom
            item["trace_json"] = trace_str

    try:
        table = _get_table()
        table.put_item(Item=item)
        logger.info("Stored trace %s for tenant %s", trace_id, tenant_id)
        return True
    except (ClientError, BotoCoreError) as e:
        logger.error("Failed to store trace %s: %s", trace_id, e)
        return False


def get_traces(
    tenant_id: str,
    limit: int = 50,
    from_date: str = None,
) -> List[Dict[str, Any]]:
    """Fetch recent traces for a tenant."""
    try:
        table = _get_table()

        key_condition = "PK = :pk"
        expr_values = {":pk": f"TRACE#{tenant_id}"}

        if from_date:
            key_condition += " AND SK >= :from"
            expr_values[":from"] = f"TRACE#{from_date}"

        response = table.query(
            KeyConditionExpression=key_condition,
            ExpressionAttributeValues=expr_values,
            ScanIndexForward=False,
            Limit=limit,
            ProjectionExpression=(
                "trace_id, tenant_id, user_id, session_id, created_at, "
                "duration_ms, total_input_tokens, total_output_tokens, "
                "total_cost_usd, tools_called, agents_delegated, span_count, #s"
            ),
            ExpressionAttributeNames={"#s": "status"},
        )

        return [_serialize(item) for item in response.get("Items", [])]
    except (ClientError, BotoCoreError) as e:
        logger.error("Failed to fetch traces for %s: %s", tenant_id, e)
        return []


def get_trace_detail(tenant_id: str, trace_id: str, date: str) -> Optional[Dict]:
    """Fetch a single trace with full spans and trace_json."""
    try:
        table = _get_table()
        response = table.get_item(
            Key={
                "PK": f"TRACE#{tenant_id}",
                "SK": f"TRACE#{date}#{trace_id}",
            }
        )
        item = response.get("Item")
        if not item:
            return None

        result = _serialize(item)
        # Parse spans back from JSON
        if "spans" in result and isinstance(result["spans"], str):
            result["spans"] = json.loads(result["spans"])
        if "trace_json" in result and isinstance(result["trace_json"], str):
            result["trace_json"] = json.loads(result["trace_json"])
        return result
    except (ClientError, BotoCoreError) as e:
        logger.error("Failed to fetch trace %s: %s", trace_id, e)
        return None


def get_traces_by_session(session_id: str, limit: int = 20) -> List[Dict]:
    """Fetch traces for a specific session via GSI1."""
    try:
        table = _get_table()
        response = table.query(
            IndexName="GSI1",
            KeyConditionExpression="GSI1PK = :pk AND begins_with(GSI1SK, :prefix)",
            ExpressionAttributeValues={
                ":pk": f"SESSION#{session_id}",
                ":prefix": "TRACE#",
            },
            ScanIndexForward=False,
            Limit=limit,
        )
        return [_serialize(item) for item in response.get("Items", [])]
    except (ClientError, BotoCoreError) as e:
        logger.error("Failed to fetch traces for session %s: %s", session_id, e)
        return []


def _serialize(item: dict) -> dict:
    """Convert DynamoDB Decimal types to Python floats/ints."""
    result = {}
    for k, v in item.items():
        if isinstance(v, Decimal):
            result[k] = float(v) if v % 1 else int(v)
        else:
            result[k] = v
    return result
```

---

## Phase 5: Admin Trace Viewer

**Goal**: Build an in-app trace viewer at `/admin/traces` backed by DynamoDB.

**New API Endpoints** (add to `server/app/main.py`):

```python
# ── Trace Viewer Endpoints ────────────────────────────────────────────

@app.get("/api/admin/traces")
async def api_admin_traces(
    tenant_id: str = Query(default="default"),
    limit: int = Query(default=50, le=200),
    from_date: str = Query(default=None),
):
    """Fetch recent traces for admin viewing."""
    from app.telemetry.trace_store import get_traces
    traces = get_traces(tenant_id=tenant_id, limit=limit, from_date=from_date)
    return {"traces": traces, "total": len(traces)}


@app.get("/api/admin/traces/{trace_id}")
async def api_admin_trace_detail(
    trace_id: str,
    tenant_id: str = Query(default="default"),
    date: str = Query(...),
):
    """Get full trace details including spans."""
    from app.telemetry.trace_store import get_trace_detail
    trace = get_trace_detail(tenant_id=tenant_id, trace_id=trace_id, date=date)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")
    return trace


@app.get("/api/admin/traces/session/{session_id}")
async def api_admin_session_traces(
    session_id: str,
    limit: int = Query(default=20, le=100),
):
    """Get all traces for a specific session."""
    from app.telemetry.trace_store import get_traces_by_session
    traces = get_traces_by_session(session_id=session_id, limit=limit)
    return {"traces": traces, "total": len(traces)}
```

**New Frontend Page**: `client/app/admin/traces/page.tsx`

```tsx
"use client";

import { useState, useEffect } from "react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

interface TraceSummary {
  trace_id: string;
  session_id: string;
  user_id: string;
  created_at: string;
  duration_ms: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cost_usd: number;
  tools_called: string[];
  agents_delegated: string[];
  span_count: number;
  status: string;
}

export default function TracesPage() {
  const [traces, setTraces] = useState<TraceSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/admin/traces?limit=50")
      .then((res) => res.json())
      .then((data) => setTraces(data.traces))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="container mx-auto py-8">
      <h1 className="text-2xl font-bold mb-6">Agent Traces</h1>

      {loading ? (
        <p className="text-muted-foreground">Loading traces...</p>
      ) : (
        <div className="grid gap-3">
          {traces.map((trace) => (
            <Card key={trace.trace_id} className="cursor-pointer hover:bg-accent">
              <CardHeader className="py-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm font-mono">
                    {trace.trace_id}
                  </CardTitle>
                  <Badge variant={trace.status === "success" ? "default" : "destructive"}>
                    {trace.status}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="py-2">
                <div className="flex gap-4 text-sm text-muted-foreground">
                  <span>{trace.duration_ms}ms</span>
                  <span>
                    {trace.total_input_tokens + trace.total_output_tokens} tokens
                  </span>
                  <span>${trace.total_cost_usd.toFixed(4)}</span>
                  <span>{trace.span_count} spans</span>
                </div>
                {trace.agents_delegated.length > 0 && (
                  <div className="flex gap-1 mt-1">
                    {trace.agents_delegated.map((a) => (
                      <Badge key={a} variant="outline" className="text-xs">
                        {a}
                      </Badge>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
```

---

## Phase 6: CloudWatch Structured Logging

**Goal**: Emit structured JSON log events to CloudWatch for querying via Insights.

**New File**: `server/app/telemetry/cloudwatch_emitter.py`

```python
"""
CloudWatch structured log emitter for telemetry events.

Uses the existing CloudWatch Logs integration. Emits structured JSON
that can be queried with CloudWatch Insights.
"""
import json
import logging
import os
import time
from typing import Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger("eagle.telemetry.cloudwatch")

LOG_GROUP = os.getenv("EAGLE_TELEMETRY_LOG_GROUP", "/eagle/telemetry")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

_logs_client = None
_sequence_token = None


def _get_client():
    global _logs_client
    if _logs_client is None:
        _logs_client = boto3.client("logs", region_name=AWS_REGION)
    return _logs_client


def emit_telemetry_event(
    event_type: str,
    tenant_id: str,
    data: dict,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
):
    """Emit a structured telemetry event to CloudWatch Logs.

    Event types:
        - trace.started
        - trace.completed
        - tool.completed
        - agent.delegated
        - agent.completed
        - error.occurred
    """
    event = {
        "event_type": event_type,
        "tenant_id": tenant_id,
        "user_id": user_id or "anonymous",
        "session_id": session_id,
        "timestamp": int(time.time() * 1000),
        **data,
    }

    try:
        client = _get_client()
        stream_name = f"telemetry/{tenant_id}"

        # Ensure log group and stream exist
        try:
            client.create_log_group(logGroupName=LOG_GROUP)
        except ClientError as e:
            if e.response["Error"]["Code"] != "ResourceAlreadyExistsException":
                raise
        try:
            client.create_log_stream(logGroupName=LOG_GROUP, logStreamName=stream_name)
        except ClientError as e:
            if e.response["Error"]["Code"] != "ResourceAlreadyExistsException":
                raise

        client.put_log_events(
            logGroupName=LOG_GROUP,
            logStreamName=stream_name,
            logEvents=[{
                "timestamp": event["timestamp"],
                "message": json.dumps(event, default=str),
            }],
        )
    except Exception as e:
        # Telemetry should never break the main flow
        logger.warning("Failed to emit telemetry event: %s", e)


def emit_trace_completed(summary: dict):
    """Convenience: emit a trace.completed event from a TraceCollector summary."""
    emit_telemetry_event(
        event_type="trace.completed",
        tenant_id=summary.get("tenant_id", "default"),
        session_id=summary.get("session_id"),
        user_id=summary.get("user_id"),
        data={
            "trace_id": summary.get("trace_id"),
            "duration_ms": summary.get("duration_ms"),
            "total_input_tokens": summary.get("total_input_tokens"),
            "total_output_tokens": summary.get("total_output_tokens"),
            "total_cost_usd": summary.get("total_cost_usd"),
            "tools_called": summary.get("tools_called", []),
            "agents_delegated": summary.get("agents_delegated", []),
        },
    )
```

### CloudWatch Insights Queries

With structured JSON events, you can query telemetry using CloudWatch Insights:

```
# Average latency by tenant (last 24h)
fields @timestamp, tenant_id, duration_ms
| filter event_type = "trace.completed"
| stats avg(duration_ms), max(duration_ms), count() by tenant_id

# Cost by tenant (last 7 days)
fields tenant_id, total_cost_usd
| filter event_type = "trace.completed"
| stats sum(total_cost_usd) as total_cost by tenant_id
| sort total_cost desc

# Most used tools
fields tools_called
| filter event_type = "trace.completed"
| stats count() by tools_called

# Error rate by tenant
fields tenant_id, event_type
| filter event_type in ["trace.completed", "error.occurred"]
| stats count() as total,
        sum(event_type = "error.occurred") as errors
        by tenant_id
```

---

## Phase 7: Test Harness Integration

**Goal**: Use TraceCollector in eval tests and capture trace data for analysis.

**Modify**: `server/tests/test_eagle_sdk_eval.py`

Replace inline `TraceCollector` with the production module:

```python
# At top of file, replace the class definition with:
from app.telemetry import TraceCollector

# The rest of the test code stays the same — TraceCollector API is identical.
# The _test_traces and _test_summaries stores continue to work.
```

Add optional trace persistence in the test fixture:

```python
@pytest.fixture
def trace_collector(request):
    """Create a TraceCollector that auto-stores results."""
    collector = TraceCollector(
        tenant_id="test",
        user_id="test-runner",
    )
    yield collector

    # After test: store summary for analysis
    summary = collector.summary()
    _test_summaries[id(request)] = summary

    # Optionally persist to DynamoDB if EAGLE_PERSIST_TEST_TRACES=1
    if os.getenv("EAGLE_PERSIST_TEST_TRACES") == "1":
        from app.telemetry.trace_store import store_trace
        store_trace(
            summary=summary,
            spans=[],
            trace_json=collector.to_trace_json(),
        )
```

---

## File Changes Summary

| File | Action | Description |
|---|---|---|
| `server/app/telemetry/__init__.py` | **Create** | Module exports |
| `server/app/telemetry/trace_collector.py` | **Create** | Promoted from test code, SDK message processing |
| `server/app/telemetry/span_tracker.py` | **Create** | SDK hook-based span tracking |
| `server/app/telemetry/status_messages.py` | **Create** | Human-readable agent/tool name mappings |
| `server/app/telemetry/trace_store.py` | **Create** | DynamoDB persistence for traces |
| `server/app/telemetry/cloudwatch_emitter.py` | **Create** | CloudWatch structured log emission |
| `server/app/stream_protocol.py` | **Modify** | Add `AGENT_STATUS` event type + writer method |
| `server/app/sdk_agentic_service.py` | **Modify** | Wire TraceCollector + SpanTracker hooks |
| `server/app/main.py` | **Modify** | Add `/api/admin/traces` endpoints |
| `client/types/stream.ts` | **Modify** | Add `agent_status` to StreamEventType |
| `client/components/chat/AgentStatus.tsx` | **Create** | Status display component |
| `client/hooks/use-agent-stream.ts` | **Modify** | Handle `agent_status` SSE events |
| `client/app/admin/traces/page.tsx` | **Create** | Admin trace viewer page |
| `server/tests/test_eagle_sdk_eval.py` | **Modify** | Import TraceCollector from production module |

### Dependencies: NONE added

```
# No changes to server/requirements.txt
# No new pip packages
# No new environment variables required (optional: EAGLE_TELEMETRY_LOG_GROUP, TRACE_TTL_DAYS)
```

---

## Data Model

### DynamoDB Trace Items (existing `eagle` table)

```
PK: TRACE#{tenant_id}
SK: TRACE#{date}#{trace_id}

Attributes:
  trace_id          String    "t-1708420245-a1b2c3d4"
  tenant_id         String    "acme-corp"
  user_id           String    "user-123"
  session_id        String    "s-1708420200-xyz"
  created_at        String    ISO timestamp
  date              String    "2026-02-20"
  duration_ms       Number    2340
  total_input_tokens Number   1830
  total_output_tokens Number  567
  total_cost_usd    Number    0.0045
  tools_called      List      ["search_far", "create_document"]
  agents_delegated  List      ["legal-counsel", "document-generator"]
  span_count        Number    4
  spans             String    JSON-serialized span array
  trace_json        String    JSON-serialized full trace (optional, <350KB)
  status            String    "success" | "error"
  ttl               Number    Unix timestamp (30-day expiry)

GSI1 (for session lookup):
  GSI1PK: SESSION#{session_id}
  GSI1SK: TRACE#{trace_id}
```

### CloudWatch Log Events (`/eagle/telemetry`)

```json
{
  "event_type": "trace.completed",
  "tenant_id": "acme-corp",
  "user_id": "user-123",
  "session_id": "s-1708420200-xyz",
  "trace_id": "t-1708420245-a1b2c3d4",
  "duration_ms": 2340,
  "total_input_tokens": 1830,
  "total_output_tokens": 567,
  "total_cost_usd": 0.0045,
  "tools_called": ["search_far", "create_document"],
  "agents_delegated": ["legal-counsel", "document-generator"],
  "timestamp": 1708420247123
}
```

---

## Testing Strategy

### Unit Tests

```python
# server/tests/test_telemetry.py

def test_trace_collector_processes_result_message():
    """TraceCollector should accumulate usage from ResultMessage."""
    collector = TraceCollector(tenant_id="test")
    # ... mock ResultMessage with usage dict ...
    assert collector.total_input_tokens > 0
    assert collector.total_cost_usd > 0

def test_span_tracker_creates_spans():
    """SpanTracker should create spans from hook callbacks."""
    tracker = SpanTracker()
    # ... simulate PreToolUse / PostToolUse ...
    spans = tracker.get_completed_spans()
    assert len(spans) == 1
    assert spans[0]["duration_ms"] >= 0

def test_status_message_mapping():
    """Status messages should be human-readable."""
    from app.telemetry.status_messages import get_tool_status_message
    msg = get_tool_status_message("search_far", {})
    assert "FAR" in msg

def test_agent_display_name():
    """Agent names should map to display names."""
    from app.telemetry.status_messages import get_agent_display_name
    assert get_agent_display_name("legal-counsel") == "Legal Counsel"
    assert get_agent_display_name("unknown-agent") == "Unknown Agent"
```

### Integration Tests

```python
# server/tests/test_telemetry_integration.py

@pytest.mark.asyncio
async def test_trace_store_round_trip():
    """Store and retrieve a trace from DynamoDB."""
    from app.telemetry.trace_store import store_trace, get_traces
    summary = {"trace_id": "test-123", "tenant_id": "test", ...}
    store_trace(summary, spans=[])
    traces = get_traces(tenant_id="test", limit=1)
    assert len(traces) >= 1

@pytest.mark.asyncio
async def test_sdk_query_with_hooks():
    """SDK query should produce trace data via hooks."""
    collector = TraceCollector(tenant_id="test")
    tracker = SpanTracker()
    # ... run sdk_query with hooks ...
    summary = collector.summary()
    assert summary["total_input_tokens"] > 0
    spans = tracker.get_completed_spans()
    # Spans will be populated if tools/agents were invoked
```

---

## Estimated Effort

| Phase | Description | Hours | Dependencies |
|---|---|---|---|
| 1 | Promote TraceCollector | 1-2 | None |
| 2 | SDK hooks (SpanTracker) | 2-3 | Phase 1 |
| 3 | User status events (SSE) | 2-3 | Phase 2 |
| 4 | DynamoDB trace persistence | 2-3 | Phase 1 |
| 5 | Admin trace viewer | 3-4 | Phase 4 |
| 6 | CloudWatch structured logging | 1-2 | Phase 1 |
| 7 | Test harness integration | 1-2 | Phase 1 |
| **Total** | | **12-19** | |

### Parallel Execution

Phases 3, 4, 6, and 7 can all proceed in parallel after Phase 1 completes:

```
Phase 1 ─────┬──── Phase 2 ──── Phase 3
              ├──── Phase 4 ──── Phase 5
              ├──── Phase 6
              └──── Phase 7
```

Minimum calendar time: ~8-12 hours (with parallelization).

---

## Open Questions

1. **Trace TTL**: 30-day default — adjust for compliance requirements?

2. **Full trace storage**: Should we always store `trace_json` (full message log) or only on error/flag?
   - Pro: Full debugging capability
   - Con: Can be large, DynamoDB 400KB item limit

3. **Status event granularity**: Show all tool calls to users, or only major operations?
   - Option A: All tool calls (detailed but may be noisy)
   - Option B: Only agent-level + document creation (cleaner UX)

4. **CloudWatch log group**: Use `/eagle/telemetry` (new) or append to `/eagle/app` (existing)?
   - Separate: cleaner queries, independent retention
   - Shared: simpler setup, one log group

5. **Admin access control**: The admin trace endpoints currently have no auth. Should they require admin role?
   - Current: open (for development)
   - Production: gate behind admin role check
