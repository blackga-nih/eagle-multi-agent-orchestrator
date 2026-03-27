# Agent & Skill Telemetry/Observability Plan

> **Status**: Proposed
> **Author**: Claude Code
> **Date**: 2026-02-19

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Problem Statement](#problem-statement)
3. [Solution Overview](#solution-overview)
4. [Technology Choice: Langfuse](#technology-choice-langfuse)
5. [Architecture](#architecture)
6. [User-Facing Status Updates](#user-facing-status-updates)
7. [Implementation Phases](#implementation-phases)
8. [File Changes Summary](#file-changes-summary)
9. [API Reference](#api-reference)
10. [Frontend Components](#frontend-components)
11. [Testing Strategy](#testing-strategy)
12. [Deployment & Configuration](#deployment--configuration)
13. [Estimated Effort](#estimated-effort)
14. [Open Questions](#open-questions)

---

## Executive Summary

This plan adds comprehensive observability to the EAGLE multi-tenant agent application:

- **For Users**: Real-time status updates in chat showing what agents are doing ("Document agent is generating SOW...")
- **For Developers/Admins**: Full trace visibility via Langfuse dashboard, in-app admin panel, and test harness
- **For Operations**: Cost tracking, latency metrics, and error monitoring per tenant

---

## Problem Statement

### Current State

The application has basic observability:
- Python's standard `logging` module (no structured logging)
- In-memory telemetry buffer (500 entries, lost on restart)
- CloudWatch Logs integration as an agent tool
- DynamoDB for cost/usage tracking per tenant

### What's Missing

| Gap | Impact |
|-----|--------|
| No distributed tracing | Can't trace a request through supervisor → subagent → tool |
| No agent execution visibility | Users don't know what's happening during long operations |
| No prompt/completion logging | Can't debug agent behavior or optimize prompts |
| No structured spans | Can't measure latency of individual operations |
| No test observability | Evals don't capture trace data for analysis |

---

## Solution Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                              COMPONENTS                                   │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  1. LANGFUSE INTEGRATION           2. USER STATUS EVENTS                 │
│     ├─ Trace per chat request         ├─ AGENT_STATUS SSE event type     │
│     ├─ Span per agent invocation      ├─ Real-time UI updates            │
│     ├─ Span per tool call             └─ Activity indicators             │
│     └─ Token/cost tracking                                               │
│                                                                          │
│  3. SDK HOOKS                      4. VIEWING OPTIONS                    │
│     ├─ PreToolUse                     ├─ Langfuse Dashboard              │
│     ├─ PostToolUse                    ├─ In-App Admin Panel              │
│     ├─ SubagentStart                  └─ Test Harness                    │
│     └─ SubagentStop                                                      │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Technology Choice: Langfuse

### Why Langfuse over OpenTelemetry?

| Criteria | Langfuse | OpenTelemetry |
|----------|----------|---------------|
| **Purpose** | Built for LLM/AI agents | General-purpose observability |
| **LLM Features** | Prompt/completion logging, token costs, model comparison | Requires custom semantic conventions |
| **Claude SDK** | Native integration via callbacks | Manual instrumentation |
| **Setup** | 1 dependency, 3 env vars | 5+ dependencies, collector infrastructure |
| **Cost** | Free tier (50K observations/month) | Free (but need backend like X-Ray) |
| **Dashboard** | AI-focused (prompts, generations, scores) | Generic trace viewer |

### Langfuse Features We'll Use

1. **Traces** - One per chat request, contains all operations
2. **Spans** - Nested operations (agent calls, tool executions)
3. **Generations** - LLM calls with prompt/completion/tokens
4. **Scores** - Optional quality metrics (can add later)
5. **Sessions** - Group traces by conversation
6. **Users** - Track per user for multi-tenant

### Alternative Considered: OpenTelemetry + AWS X-Ray

If you prefer staying fully in the AWS ecosystem:
- Use OpenTelemetry SDK with OTLP export to ADOT collector
- Routes to AWS X-Ray for visualization
- More infrastructure to manage
- Less LLM-specific features

---

## Architecture

### High-Level Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         User Chat Interface                              │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │ User: "Create a SOW document for the cloud migration project"     │  │
│  │                                                                   │  │
│  │ ⏳ Analyzing requirements...                                      │  │
│  │ ⏳ Legal Counsel is reviewing compliance...                       │  │
│  │ ⏳ Searching FAR/DFARS regulations...                             │  │
│  │ ⏳ Document Generator is creating SOW...                          │  │
│  │ ✓ Document created: SOW_CloudMigration_2026.docx                 │  │
│  │                                                                   │  │
│  │ Assistant: I've created the Statement of Work document...        │  │
│  └───────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
                │
                │ SSE Stream (includes AGENT_STATUS events)
                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       FastAPI Backend                                    │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    Request Handler                                │   │
│  │  POST /api/chat/stream                                           │   │
│  │  - Creates Langfuse trace                                        │   │
│  │  - Sets up SSE stream                                            │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                              │                                           │
│                              ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │              sdk_agentic_service.py                               │   │
│  │                                                                   │   │
│  │  SDK Hooks:                                                       │   │
│  │  ┌─────────────────────────────────────────────────────────────┐ │   │
│  │  │ SubagentStart → emit_status("Legal Counsel analyzing...")   │ │   │
│  │  │              → langfuse.span("agent.legal-counsel")         │ │   │
│  │  ├─────────────────────────────────────────────────────────────┤ │   │
│  │  │ PreToolUse   → emit_status("Searching FAR...")              │ │   │
│  │  │              → langfuse.span("tool.search_far")             │ │   │
│  │  ├─────────────────────────────────────────────────────────────┤ │   │
│  │  │ PostToolUse  → span.end(output=result)                      │ │   │
│  │  │              → emit_status("Search complete", "complete")   │ │   │
│  │  ├─────────────────────────────────────────────────────────────┤ │   │
│  │  │ SubagentStop → span.end(tokens, cost)                       │ │   │
│  │  │              → emit_status("Legal Counsel done", "complete")│ │   │
│  │  └─────────────────────────────────────────────────────────────┘ │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                              │                                           │
│                              ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │              agentic_service.py (fallback)                        │   │
│  │                                                                   │   │
│  │  Direct instrumentation:                                          │   │
│  │  - trace = langfuse.trace("chat")                                │   │
│  │  - span = trace.span("tool.{name}")                              │   │
│  │  - emit_status(...) on tool_use/tool_result                      │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
                │
                │ Async flush
                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         Langfuse                                         │
│                                                                          │
│  Trace: "chat" (session: user-123-session-abc)                          │
│  ├─ Span: "agent.supervisor" (2.3s)                                     │
│  │   ├─ Generation: claude-sonnet-4 (450 in, 120 out, $0.0012)         │
│  │   ├─ Span: "agent.legal-counsel" (1.1s)                              │
│  │   │   ├─ Generation: claude-sonnet-4 (380 in, 200 out)              │
│  │   │   └─ Span: "tool.search_far" (0.3s)                              │
│  │   └─ Span: "agent.document-generator" (0.8s)                         │
│  │       └─ Span: "tool.create_document" (0.5s)                         │
│  └─ Total: 2.3s, $0.0045, 1830 tokens                                   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Trace Structure

```
Trace: chat
├── user_id: "user-123"
├── session_id: "session-abc"
├── metadata: { tenant_id: "acme-corp" }
│
├── Span: agent.supervisor
│   ├── input: "Create a SOW document..."
│   ├── model: "claude-sonnet-4"
│   │
│   ├── Span: agent.legal-counsel
│   │   ├── input: "Analyze compliance for..."
│   │   ├── output: "The following FAR clauses apply..."
│   │   ├── tokens: { input: 380, output: 200 }
│   │   │
│   │   └── Span: tool.search_far
│   │       ├── input: { query: "cloud services FAR" }
│   │       ├── output: { results: [...] }
│   │       └── duration_ms: 312
│   │
│   └── Span: agent.document-generator
│       ├── input: "Generate SOW with..."
│       │
│       └── Span: tool.create_document
│           ├── input: { doc_type: "sow", ... }
│           ├── output: { s3_key: "eagle/acme/sow_123.docx" }
│           └── duration_ms: 523
│
└── output: "I've created the Statement of Work..."
```

---

## User-Facing Status Updates

### New SSE Event Type

```python
# server/app/stream_protocol.py

class StreamEventType(str, Enum):
    TEXT = "text"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    AGENT_STATUS = "agent_status"  # NEW
    COMPLETE = "complete"
    ERROR = "error"

@dataclass
class AgentStatusEvent:
    event_type: str = "agent_status"
    agent_name: str = ""           # e.g., "legal-counsel", "search_far"
    display_name: str = ""         # e.g., "Legal Counsel", "FAR Search"
    message: str = ""              # e.g., "Analyzing compliance requirements..."
    status: str = "in_progress"    # "in_progress" | "complete" | "error"
    timestamp: str = ""            # ISO timestamp
```

### Status Message Mapping

```python
# server/app/telemetry/status_messages.py

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
    },
    "dynamodb_intake": {
        "get": "Loading intake data...",
        "put": "Saving intake data...",
        "query": "Querying records...",
    },
    "search_far": "Searching FAR/DFARS regulations...",
    "create_document": {
        "sow": "Generating Statement of Work...",
        "igce": "Generating Cost Estimate...",
        "market_research": "Generating Market Research...",
        "ja": "Generating Justification & Approval...",
        "default": "Generating document...",
    },
    "cloudwatch_logs": "Querying logs...",
    "intake_workflow": {
        "start": "Starting intake workflow...",
        "advance": "Advancing to next phase...",
        "complete": "Completing intake...",
    },
}
```

### Frontend Rendering

```tsx
// client/components/chat/AgentStatus.tsx

interface AgentStatusProps {
  agentName: string;
  displayName: string;
  message: string;
  status: "in_progress" | "complete" | "error";
}

export function AgentStatus({ displayName, message, status }: AgentStatusProps) {
  return (
    <div className="flex items-center gap-2 text-sm text-muted-foreground py-1">
      {status === "in_progress" && <Spinner className="h-3 w-3" />}
      {status === "complete" && <CheckIcon className="h-3 w-3 text-green-500" />}
      {status === "error" && <XIcon className="h-3 w-3 text-red-500" />}
      <span className="font-medium">{displayName}:</span>
      <span>{message}</span>
    </div>
  );
}
```

### Example User Experience

```
User: Create a SOW for the cloud migration project

┌─────────────────────────────────────────────────────────────┐
│ ⏳ EAGLE Assistant: Analyzing your request...               │
│ ⏳ Legal Counsel: Reviewing compliance requirements...      │
│ ⏳ Knowledge Search: Searching FAR/DFARS regulations...     │
│ ✓ Knowledge Search: Found 12 relevant clauses              │
│ ✓ Legal Counsel: Compliance analysis complete              │
│ ⏳ Document Generator: Creating Statement of Work...        │
│ ✓ Document Generator: SOW_CloudMigration_2026.docx created │
│ ✓ EAGLE Assistant: Response ready                          │
└─────────────────────────────────────────────────────────────┘

---

## Implementation Phases

### Phase 1: Langfuse Setup (1-2 hours)

**Goal**: Get basic tracing working with Langfuse

**New Files:**
```
server/app/telemetry/
├── __init__.py              # Module exports
├── langfuse_client.py       # Langfuse initialization
└── status_messages.py       # Human-readable status mappings
```

**Dependencies** (`server/requirements.txt`):
```
langfuse>=2.0.0
```

**Environment Variables** (`.env`):
```bash
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com  # or self-hosted
```

**Code**: `server/app/telemetry/langfuse_client.py`
```python
import os
from langfuse import Langfuse
from functools import lru_cache

@lru_cache(maxsize=1)
def get_langfuse_client() -> Langfuse:
    """Singleton Langfuse client."""
    return Langfuse(
        public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
        secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
        host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
    )

def create_trace(
    name: str,
    user_id: str,
    session_id: str,
    tenant_id: str,
    **kwargs
):
    """Create a new trace for a chat request."""
    client = get_langfuse_client()
    return client.trace(
        name=name,
        user_id=user_id,
        session_id=session_id,
        metadata={"tenant_id": tenant_id, **kwargs},
    )
```

---

### Phase 2: User Status Events (2-3 hours)

**Goal**: Add AGENT_STATUS SSE events for real-time user feedback

**Modify**: `server/app/stream_protocol.py`
- Add `AGENT_STATUS` to `StreamEventType` enum
- Add `AgentStatusEvent` dataclass
- Add `emit_agent_status()` helper

**Modify**: `client/components/chat/`
- Create `AgentStatus.tsx` component
- Update SSE handler to process `agent_status` events
- Add status list to chat message display

---

### Phase 3: Instrument agentic_service.py (2-3 hours)

**Goal**: Add tracing and status events to the main chat service

**Modify**: `server/app/agentic_service.py`

Key changes to `stream_chat()`:

```python
from app.telemetry import create_trace, get_langfuse_client
from app.telemetry.status_messages import get_tool_status_message

async def stream_chat(
    messages: List[dict],
    on_text=None,
    on_tool_use=None,
    on_tool_result=None,
    on_status=None,  # NEW: callback for status events
    session_id: str = None,
    tenant_id: str = "default",
    user_id: str = "anonymous",
):
    # Create Langfuse trace
    trace = create_trace(
        name="chat",
        user_id=user_id,
        session_id=session_id,
        tenant_id=tenant_id,
    )

    try:
        # ... existing iteration loop ...

        for tu in tool_uses:
            tool_name = tu["name"]
            tool_input = tu["input"]

            # Emit status to user
            if on_status:
                await on_status(
                    agent_name=tool_name,
                    message=get_tool_status_message(tool_name, tool_input),
                    status="in_progress"
                )

            # Create Langfuse span
            span = trace.span(
                name=f"tool.{tool_name}",
                input=tool_input,
            )

            start_time = time.time()
            output = execute_tool(tool_name, tool_input, session_id=session_id)
            duration_ms = int((time.time() - start_time) * 1000)

            # End span with output
            span.end(
                output=output[:2000] if output else None,  # Truncate large outputs
                metadata={"duration_ms": duration_ms},
            )

            # Emit completion status
            if on_status:
                await on_status(
                    agent_name=tool_name,
                    message=f"Completed in {duration_ms}ms",
                    status="complete"
                )

    finally:
        # Ensure trace is flushed
        trace.update(
            output=final_response,
            metadata={
                "total_input_tokens": total_input_tokens,
                "total_output_tokens": total_output_tokens,
                "tools_called": tools_called,
            },
        )
        get_langfuse_client().flush()
```

---

### Phase 4: SDK Hooks for Subagent Tracing (3-4 hours)

**Goal**: Trace subagent execution in sdk_agentic_service.py

**New File**: `server/app/telemetry/sdk_hooks.py`

```python
from claude_agent_sdk import (
    HookMatcher,
    PreToolUseHookInput,
    PostToolUseHookInput,
    SubagentStartHookInput,
    SubagentStopHookInput,
    HookContext,
)
from .langfuse_client import get_langfuse_client
from .status_messages import AGENT_DISPLAY_NAMES, get_tool_status_message
import time

# Track active spans
_active_spans: dict[str, tuple] = {}

class ObservabilityHooks:
    """SDK hooks for Langfuse tracing and user status events."""

    def __init__(self, trace, on_status=None):
        self.trace = trace
        self.on_status = on_status

    async def on_subagent_start(
        self, input: SubagentStartHookInput, tool_use_id: str, ctx: HookContext
    ):
        """Called when a subagent starts execution."""
        agent_name = input.agent_name
        display_name = AGENT_DISPLAY_NAMES.get(agent_name, agent_name)

        # Emit user status
        if self.on_status:
            await self.on_status(
                agent_name=agent_name,
                display_name=display_name,
                message=f"Analyzing...",
                status="in_progress",
            )

        # Create Langfuse span
        span = self.trace.span(
            name=f"agent.{agent_name}",
            input=str(input.messages[-1] if input.messages else ""),
        )
        _active_spans[tool_use_id] = (span, time.time(), agent_name)

        return {"continue_": True}

    async def on_subagent_stop(
        self, input: SubagentStopHookInput, tool_use_id: str, ctx: HookContext
    ):
        """Called when a subagent completes."""
        if tool_use_id not in _active_spans:
            return {"continue_": True}

        span, start_time, agent_name = _active_spans.pop(tool_use_id)
        duration_ms = int((time.time() - start_time) * 1000)
        display_name = AGENT_DISPLAY_NAMES.get(agent_name, agent_name)

        # End span with metrics
        span.end(
            output=str(input.result)[:2000] if input.result else None,
            metadata={
                "duration_ms": duration_ms,
                "input_tokens": getattr(input, "input_tokens", 0),
                "output_tokens": getattr(input, "output_tokens", 0),
            },
        )

        # Emit completion status
        if self.on_status:
            await self.on_status(
                agent_name=agent_name,
                display_name=display_name,
                message=f"Complete ({duration_ms}ms)",
                status="complete",
            )

        return {"continue_": True}

    async def on_pre_tool_use(
        self, input: PreToolUseHookInput, tool_use_id: str, ctx: HookContext
    ):
        """Called before a tool is executed."""
        tool_name = input.tool_name
        message = get_tool_status_message(tool_name, input.tool_input)

        if self.on_status:
            await self.on_status(
                agent_name=tool_name,
                message=message,
                status="in_progress",
            )

        span = self.trace.span(
            name=f"tool.{tool_name}",
            input=input.tool_input,
        )
        _active_spans[tool_use_id] = (span, time.time(), tool_name)

        return {"continue_": True, "decision": None, "hookSpecificOutput": None}

    async def on_post_tool_use(
        self, input: PostToolUseHookInput, tool_use_id: str, ctx: HookContext
    ):
        """Called after a tool completes."""
        if tool_use_id not in _active_spans:
            return {"continue_": True, "hookSpecificOutput": None}

        span, start_time, tool_name = _active_spans.pop(tool_use_id)
        duration_ms = int((time.time() - start_time) * 1000)

        span.end(
            output=str(input.tool_result)[:2000] if input.tool_result else None,
            metadata={"duration_ms": duration_ms},
        )

        if self.on_status:
            await self.on_status(
                agent_name=tool_name,
                message=f"Complete ({duration_ms}ms)",
                status="complete",
            )

        return {"continue_": True, "hookSpecificOutput": None}

    def get_hook_matchers(self) -> list[HookMatcher]:
        """Return hook matchers for the SDK."""
        return [
            HookMatcher(matcher="SubagentStart", hooks=[self.on_subagent_start], timeout=5000),
            HookMatcher(matcher="SubagentStop", hooks=[self.on_subagent_stop], timeout=5000),
            HookMatcher(matcher="PreToolUse", hooks=[self.on_pre_tool_use], timeout=5000),
            HookMatcher(matcher="PostToolUse", hooks=[self.on_post_tool_use], timeout=5000),
        ]
```

**Modify**: `server/app/sdk_agentic_service.py`

```python
from app.telemetry import create_trace
from app.telemetry.sdk_hooks import ObservabilityHooks

async def sdk_query(
    prompt: str,
    session_id: str,
    tenant_id: str,
    user_id: str,
    on_status=None,  # NEW
    **kwargs
):
    # Create trace
    trace = create_trace(
        name="sdk_chat",
        user_id=user_id,
        session_id=session_id,
        tenant_id=tenant_id,
    )

    # Create hooks
    hooks = ObservabilityHooks(trace=trace, on_status=on_status)

    options = ClaudeAgentOptions(
        model=agent_model,
        system_prompt=system_prompt,
        # ... other options ...
        hooks=hooks.get_hook_matchers(),  # ADD HOOKS
    )

    # ... rest of implementation ...
```

---

### Phase 5: Admin Trace Viewer (3-4 hours)

**Goal**: Build in-app trace viewer at `/admin/traces`

**New API Endpoint** (`server/app/main.py`):

```python
@app.get("/api/admin/traces")
async def get_traces(
    user: UserContext = Depends(require_admin),
    limit: int = Query(default=50, le=200),
    session_id: Optional[str] = None,
    user_filter: Optional[str] = None,
    from_timestamp: Optional[str] = None,
):
    """Fetch traces from Langfuse for admin viewing."""
    from app.telemetry import get_langfuse_client

    client = get_langfuse_client()

    # Build filter
    filters = []
    if session_id:
        filters.append({"field": "session_id", "operator": "=", "value": session_id})
    if user_filter:
        filters.append({"field": "user_id", "operator": "=", "value": user_filter})

    # Fetch traces
    traces = client.fetch_traces(
        limit=limit,
        from_timestamp=from_timestamp,
    )

    return {
        "traces": [
            {
                "id": t.id,
                "name": t.name,
                "session_id": t.session_id,
                "user_id": t.user_id,
                "timestamp": t.timestamp.isoformat(),
                "duration_ms": t.duration_ms,
                "input_tokens": t.metadata.get("total_input_tokens", 0),
                "output_tokens": t.metadata.get("total_output_tokens", 0),
                "status": "success" if not t.error else "error",
            }
            for t in traces.data
        ],
        "total": len(traces.data),
    }

@app.get("/api/admin/traces/{trace_id}")
async def get_trace_detail(
    trace_id: str,
    user: UserContext = Depends(require_admin),
):
    """Get full trace details including all spans."""
    from app.telemetry import get_langfuse_client

    client = get_langfuse_client()
    trace = client.fetch_trace(trace_id)

    return {
        "trace": {
            "id": trace.id,
            "name": trace.name,
            "input": trace.input,
            "output": trace.output,
            "metadata": trace.metadata,
            "timestamp": trace.timestamp.isoformat(),
        },
        "observations": [
            {
                "id": o.id,
                "name": o.name,
                "type": o.type,
                "start_time": o.start_time.isoformat(),
                "end_time": o.end_time.isoformat() if o.end_time else None,
                "input": o.input,
                "output": o.output,
                "metadata": o.metadata,
                "parent_id": o.parent_observation_id,
            }
            for o in trace.observations
        ],
    }
```

**New Frontend Page** (`client/app/admin/traces/page.tsx`):

```tsx
"use client";

import { useState, useEffect } from "react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatDistanceToNow } from "date-fns";

interface Trace {
  id: string;
  name: string;
  session_id: string;
  user_id: string;
  timestamp: string;
  duration_ms: number;
  input_tokens: number;
  output_tokens: number;
  status: "success" | "error";
}

export default function TracesPage() {
  const [traces, setTraces] = useState<Trace[]>([]);
  const [selectedTrace, setSelectedTrace] = useState<string | null>(null);

  useEffect(() => {
    fetchTraces();
  }, []);

  const fetchTraces = async () => {
    const res = await fetch("/api/admin/traces?limit=50");
    const data = await res.json();
    setTraces(data.traces);
  };

  return (
    <div className="container mx-auto py-8">
      <h1 className="text-2xl font-bold mb-6">Agent Traces</h1>

      <div className="grid gap-4">
        {traces.map((trace) => (
          <Card
            key={trace.id}
            className="cursor-pointer hover:bg-accent"
            onClick={() => setSelectedTrace(trace.id)}
          >
            <CardHeader className="py-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-medium">
                  {trace.name}
                </CardTitle>
                <Badge variant={trace.status === "success" ? "default" : "destructive"}>
                  {trace.status}
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="py-2">
              <div className="flex gap-4 text-sm text-muted-foreground">
                <span>{trace.duration_ms}ms</span>
                <span>{trace.input_tokens + trace.output_tokens} tokens</span>
                <span>{formatDistanceToNow(new Date(trace.timestamp))} ago</span>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
```

---

### Phase 6: Test Harness Integration (2-3 hours)

**Goal**: Capture traces during eval runs for debugging

**Modify**: `server/tests/test_eagle_sdk_eval.py`

```python
import pytest
from app.telemetry import get_langfuse_client, create_trace

@pytest.fixture
def langfuse_trace(request):
    """Create a Langfuse trace for the test."""
    trace = create_trace(
        name=f"test_{request.node.name}",
        user_id="test-runner",
        session_id=f"eval-{request.node.name}",
        tenant_id="test",
    )
    yield trace

    # Flush on teardown
    get_langfuse_client().flush()

async def test_document_generation(langfuse_trace):
    """Test that document generation creates proper traces."""
    # Run agent
    result = await sdk_query(
        prompt="Create a SOW for cloud migration",
        session_id="test-session",
        tenant_id="test",
        user_id="test-user",
    )

    # Update trace with result
    langfuse_trace.update(output=result)

    # Assertions
    assert "SOW" in result or "Statement of Work" in result

    # After test, can view trace in Langfuse dashboard
    print(f"Trace URL: https://cloud.langfuse.com/trace/{langfuse_trace.id}")
```

---

## File Changes Summary

| File | Action | Description |
|------|--------|-------------|
| `server/requirements.txt` | Modify | Add `langfuse>=2.0.0` |
| `server/.env` | Modify | Add Langfuse keys |
| `server/app/telemetry/__init__.py` | Create | Module exports |
| `server/app/telemetry/langfuse_client.py` | Create | Langfuse client singleton |
| `server/app/telemetry/status_messages.py` | Create | Human-readable status mappings |
| `server/app/telemetry/sdk_hooks.py` | Create | Claude SDK observability hooks |
| `server/app/stream_protocol.py` | Modify | Add AGENT_STATUS event type |
| `server/app/agentic_service.py` | Modify | Add tracing + status events |
| `server/app/sdk_agentic_service.py` | Modify | Add SDK hooks |
| `server/app/main.py` | Modify | Add /api/admin/traces endpoints |
| `client/components/chat/AgentStatus.tsx` | Create | Status display component |
| `client/app/admin/traces/page.tsx` | Create | Admin trace viewer |
| `server/tests/test_eagle_sdk_eval.py` | Modify | Add Langfuse integration |

---

## API Reference

### SSE Events

#### AGENT_STATUS Event

```json
{
  "event": "agent_status",
  "data": {
    "agent_name": "legal-counsel",
    "display_name": "Legal Counsel",
    "message": "Analyzing compliance requirements...",
    "status": "in_progress",
    "timestamp": "2026-02-19T10:30:45.123Z"
  }
}
```

**Status Values:**
- `in_progress` - Operation is running (show spinner)
- `complete` - Operation finished successfully (show checkmark)
- `error` - Operation failed (show error icon)

### Admin API

#### GET /api/admin/traces

**Query Parameters:**
- `limit` (int, default=50, max=200) - Number of traces to return
- `session_id` (string, optional) - Filter by session
- `user_filter` (string, optional) - Filter by user ID
- `from_timestamp` (ISO string, optional) - Only traces after this time

**Response:**
```json
{
  "traces": [
    {
      "id": "trace-abc123",
      "name": "chat",
      "session_id": "session-xyz",
      "user_id": "user-123",
      "timestamp": "2026-02-19T10:30:45.123Z",
      "duration_ms": 2340,
      "input_tokens": 450,
      "output_tokens": 380,
      "status": "success"
    }
  ],
  "total": 1
}
```

#### GET /api/admin/traces/{trace_id}

**Response:**
```json
{
  "trace": {
    "id": "trace-abc123",
    "name": "chat",
    "input": "Create a SOW...",
    "output": "I've created the Statement of Work...",
    "metadata": { "tenant_id": "acme-corp" },
    "timestamp": "2026-02-19T10:30:45.123Z"
  },
  "observations": [
    {
      "id": "span-1",
      "name": "agent.legal-counsel",
      "type": "span",
      "start_time": "2026-02-19T10:30:45.200Z",
      "end_time": "2026-02-19T10:30:46.300Z",
      "input": "Analyze compliance...",
      "output": "The following FAR clauses...",
      "parent_id": null
    }
  ]
}
```

---

## Frontend Components

### AgentStatus Component

```tsx
// client/components/chat/AgentStatus.tsx

import { Loader2, Check, X } from "lucide-react";

interface AgentStatusProps {
  agentName: string;
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

### SSE Handler Update

```tsx
// client/hooks/useStreamChat.ts (update)

// Add to existing SSE handler
case "agent_status":
  const statusData = JSON.parse(event.data);
  setAgentStatuses((prev) => {
    const updated = [...prev];
    const existingIndex = updated.findIndex(
      (s) => s.agent_name === statusData.agent_name && s.status === "in_progress"
    );
    if (existingIndex >= 0 && statusData.status !== "in_progress") {
      // Update existing status
      updated[existingIndex] = statusData;
    } else if (statusData.status === "in_progress") {
      // Add new in-progress status
      updated.push(statusData);
    }
    return updated;
  });
  break;
```

---

## Testing Strategy

### Unit Tests

```python
# server/tests/test_telemetry.py

def test_langfuse_client_singleton():
    """Client should be reused."""
    from app.telemetry import get_langfuse_client
    client1 = get_langfuse_client()
    client2 = get_langfuse_client()
    assert client1 is client2

def test_status_message_mapping():
    """Status messages should be human-readable."""
    from app.telemetry.status_messages import get_tool_status_message
    msg = get_tool_status_message("search_far", {})
    assert "FAR" in msg or "regulation" in msg.lower()
```

### Integration Tests

```python
# server/tests/test_observability_integration.py

@pytest.mark.asyncio
async def test_status_events_emitted():
    """Chat should emit status events during tool execution."""
    statuses = []

    async def capture_status(**kwargs):
        statuses.append(kwargs)

    await stream_chat(
        messages=[{"role": "user", "content": "Search FAR for cloud"}],
        on_status=capture_status,
    )

    # Should have at least one status event
    assert len(statuses) > 0
    assert any(s["status"] == "in_progress" for s in statuses)
    assert any(s["status"] == "complete" for s in statuses)
```

### E2E Tests

```typescript
// client/e2e/observability.spec.ts

test("agent status updates appear in chat", async ({ page }) => {
  await page.goto("/chat");

  // Send message that triggers tool use
  await page.fill('[data-testid="chat-input"]', "Create a SOW document");
  await page.click('[data-testid="send-button"]');

  // Wait for status updates
  await expect(page.locator('[data-testid="agent-status"]')).toBeVisible();

  // Should show progress then completion
  await expect(page.locator('text=in_progress')).toBeVisible();
  await expect(page.locator('text=complete')).toBeVisible({ timeout: 30000 });
});
```

---

## Deployment & Configuration

### Environment Variables

```bash
# Required for Langfuse
LANGFUSE_PUBLIC_KEY=pk-lf-xxxxxxxx
LANGFUSE_SECRET_KEY=sk-lf-xxxxxxxx
LANGFUSE_HOST=https://cloud.langfuse.com

# Optional
LANGFUSE_ENABLED=true  # Set to false to disable
```

### Self-Hosted Langfuse (Optional)

If you prefer self-hosting:

```yaml
# docker-compose.langfuse.yml
services:
  langfuse:
    image: ghcr.io/langfuse/langfuse:latest
    ports:
      - "3001:3000"
    environment:
      DATABASE_URL: postgresql://user:pass@db:5432/langfuse
      NEXTAUTH_SECRET: your-secret
      NEXTAUTH_URL: http://localhost:3001
```

Then set:
```bash
LANGFUSE_HOST=http://localhost:3001
```

---

## Estimated Effort

| Phase | Description | Hours | Dependencies |
|-------|-------------|-------|--------------|
| 1 | Langfuse Setup | 1-2 | None |
| 2 | User Status Events | 2-3 | None |
| 3 | Instrument agentic_service.py | 2-3 | Phase 1 |
| 4 | SDK Hooks | 3-4 | Phase 1, 2 |
| 5 | Admin Trace Viewer | 3-4 | Phase 1 |
| 6 | Test Integration | 2-3 | Phase 1 |
| **Total** | | **13-19** | |

---

## Open Questions

1. **Langfuse Hosting**: Use cloud (cloud.langfuse.com) or self-host?
   - Cloud: Easier setup, managed, free tier available
   - Self-host: Full control, no data leaves your infrastructure

2. **Status Event Granularity**: How detailed should status updates be?
   - Option A: Major operations only (agent start/stop, document created)
   - Option B: All tool calls (may be noisy for users)

3. **Trace Retention**: How long to keep traces in Langfuse?
   - Default: 30 days on free tier
   - Consider: Compliance requirements for your domain

4. **Admin Access Control**: Who can view traces?
   - Current plan: Admin role only
   - Consider: Tenant admins see only their tenant's traces?

5. **Cost Tracking Integration**: Should we link Langfuse traces to existing DynamoDB cost records?
   - Pro: Unified view
   - Con: Additional complexity

---

## References

- [Langfuse Documentation](https://langfuse.com/docs)
- [Claude Agent SDK Hooks](https://docs.anthropic.com/en/docs/agents/agent-sdk)
- [Langfuse + Claude SDK Integration](https://langfuse.com/integrations/frameworks/claude-agent-sdk)
- [OpenTelemetry for LLMs](https://opentelemetry.io/docs/specs/semconv/gen-ai/)