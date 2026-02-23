# SDK Integration Plan: Migrate to sdk_agentic_service Subagent Delegation

**Date**: 2026-02-22
**Type**: Orchestration migration — prompt injection → Claude Agent SDK subagent delegation
**Status**: Plan (not yet implemented)

---

## Overview

| Field | Value |
|-------|-------|
| Integration Type | Subagent orchestration (AgentDefinition + query()) |
| Files Modified | `server/app/main.py`, `server/app/streaming_routes.py` |
| Files Preserved (no changes) | `server/app/agentic_service.py` (execute_tool kept for eval) |
| Files Activated (already written) | `server/app/sdk_agentic_service.py` |
| SDK Features Used | `query()`, `AgentDefinition`, `ClaudeAgentOptions`, hooks |
| Breaking Changes | No — streaming event contract unchanged; SSE protocol unchanged |
| Eval Impact | Tests 1–27 unaffected; test 28 must be validated end-to-end |

---

## Current State

```
main.py  ──imports──►  agentic_service.stream_chat()  [ACTIVE]
streaming_routes.py  ──imports──►  agentic_service.stream_chat()  [ACTIVE]

sdk_agentic_service.sdk_query()  [IMPLEMENTED, NOT WIRED]

test_eagle_sdk_eval.py
  line 32:  from agentic_service import execute_tool   ← tool impls for tests 16–20
  line 2910: from sdk_agentic_service import ...        ← test 28 only
```

**Gap**: `sdk_agentic_service.py` is completely disconnected from the web layer. The migration is a **wiring change only** — both implementations already exist.

---

## Target State

```
main.py  ──imports──►  sdk_agentic_service.sdk_query()  [DEFAULT]
streaming_routes.py  ──imports──►  sdk_agentic_service  [DEFAULT]

agentic_service.execute_tool()  [PRESERVED — eval suite dependency]
agentic_service.stream_chat()   [DEPRECATED — removed from web imports]
```

---

## Design

### ClaudeAgentOptions Configuration

The supervisor agent in `sdk_agentic_service.build_sdk_options()` should be configured as:

| Field | Value | Reason |
|-------|-------|--------|
| `model` | `claude-sonnet-4-20250514` | Matches `plugin.json` requirement |
| `system_prompt` | Built by `build_supervisor_prompt()` — loads `supervisor/agent.md` + injects tenant context | Tenant isolation per request |
| `allowed_tools` | `["Task"]` only | Forces supervisor to delegate — never act directly |
| `agents` | `build_skill_agents()` output — one `AgentDefinition` per skill | Each skill gets isolated context |
| `max_budget_usd` | Tier-gated: `{basic: 0.10, advanced: 0.25, premium: 0.75}` | Cost control |
| `hooks` | `PreToolUse`, `PostToolUse`, `SubagentStart`, `SubagentStop`, `Stop` | Audit trail + cost attribution |

### Subagent AgentDefinition Per Skill

Each skill in `eagle-plugin/skills/` becomes one `AgentDefinition`:

```python
# Already implemented in sdk_agentic_service.build_skill_agents()
AgentDefinition(
    name=skill_name,           # e.g. "oa-intake"
    prompt=skill_prompt_body,  # loaded from eagle-plugin/skills/{name}/SKILL.md (body only, no frontmatter)
    tools=tier_tools,          # gated by subscription tier
)
```

Key guard already in place: `MAX_SKILL_PROMPT_CHARS = 4000` truncates oversized skill prompts.

### Hook Wiring

Hooks to register in `sdk_query()`:

```python
hooks = [
    PreToolUseHook(handler=log_tool_start),       # log tool name + input
    PostToolUseHook(handler=capture_tool_result),  # cost attribution, audit
    SubagentStartHook(handler=log_skill_start),    # which skill is being invoked
    SubagentStopHook(handler=log_skill_result),    # skill result + latency
    StopHook(handler=record_session_end),          # session close
]
```

These emit to CloudWatch and write to DynamoDB `USAGE#` / `COST#` records — matching the existing `agentic_service.py` cost attribution model.

---

## Implementation Steps

### Step 1: Update `streaming_routes.py` import

**File**: `server/app/streaming_routes.py`

Replace:
```python
from .agentic_service import stream_chat, MODEL, EAGLE_TOOLS
```

With:
```python
from .sdk_agentic_service import sdk_query, EAGLE_TOOLS
from .agentic_service import MODEL  # keep MODEL constant if still referenced
```

Update `stream_generator()` to call `sdk_query()` instead of `stream_chat()`. The existing SSE event mapping (`on_text`, `on_tool_use`, `on_tool_result`, `on_complete`) adapts to the `AsyncGenerator` output from `sdk_query()`.

**Message processing from `sdk_query()` output**:

```python
async for message in sdk_query(request, tenant_context):
    if isinstance(message, SystemMessage):
        # session_id extraction
        session_id = message.data.get("session_id")
    elif isinstance(message, AssistantMessage):
        for block in message.content:
            if block.type == "text":
                yield sse_text_event(block.text)
            elif block.type == "tool_use":
                yield sse_tool_use_event(block.name, block.input)
    elif isinstance(message, ResultMessage):
        usage = message.usage
        # cost attribution write (if not handled by PostToolUse hook)
        yield sse_complete_event()
```

### Step 2: Update `main.py` import

**File**: `server/app/main.py`

Remove or comment out:
```python
from .agentic_service import stream_chat, get_client, MODEL, EAGLE_TOOLS
```

Add:
```python
from .sdk_agentic_service import sdk_query, EAGLE_TOOLS
```

Any route handlers calling `stream_chat()` directly (outside `streaming_routes.py`) must be updated to call `sdk_query()`.

### Step 3: Preserve `execute_tool` in `agentic_service.py`

**No changes to `agentic_service.py`.**

`execute_tool` at line 2181 is the direct tool dispatcher used by eval tests 16–20 (S3, DynamoDB, CloudWatch, document creation). It is not a web-layer concern — it's a test utility. Keep it intact.

The eval suite import at `test_eagle_sdk_eval.py:32` remains valid:
```python
from agentic_service import execute_tool  # unchanged
```

### Step 4: Validate test 28 end-to-end

Test 28 (`test_eagle_sdk_eval.py:2898`) exercises the full skill→subagent orchestration path in `sdk_agentic_service`. Once `sdk_query()` is the active default, this test validates the production path.

Run: `just eval-quick 28`

Expected: supervisor calls `Task(oa-intake, ...)`, subagent responds, result surfaces to caller.

---

## Registration Checklist

- [ ] `ClaudeAgentOptions` configured with tier-gated `max_budget_usd`
- [ ] Supervisor `allowed_tools=["Task"]` — no direct tool use
- [ ] All 5 skill `AgentDefinition` objects built from `eagle-plugin/skills/`
- [ ] Hooks registered: `PreToolUse`, `PostToolUse`, `SubagentStart`, `SubagentStop`, `Stop`
- [ ] `streaming_routes.py` import updated to `sdk_query`
- [ ] `main.py` import updated, no remaining references to `stream_chat`
- [ ] `agentic_service.execute_tool` untouched
- [ ] `test_eagle_sdk_eval.py` line 32 import still resolves
- [ ] Test 28 passing: `just eval-quick 28`
- [ ] Smoke test passing: `just smoke`

---

## Acceptance Criteria for Flipping the Default

The switch is complete when ALL of the following are true:

| Criterion | Validation |
|-----------|------------|
| `just lint` passes (ruff + tsc) | `just lint` → 0 errors |
| Backend unit tests pass | `just test` → all green |
| Test 28 (skill→subagent E2E) passes | `just eval-quick 28` → PASS |
| AWS tool tests 16–20 pass | `just eval-aws` → PASS |
| Smoke test passes (22 tests) | `just smoke` → 22 passed |
| No reference to `stream_chat` in active imports | `grep -r "stream_chat" server/app/main.py server/app/streaming_routes.py` → empty |
| CloudWatch shows SDK hook events in dev | Manual check post-deploy |

**Blocking items**: None identified. The implementation exists. This is a wiring change only.

**Non-goal**: Do not remove `agentic_service.py`. It contains `execute_tool` which the eval suite depends on. Mark `stream_chat` as deprecated with a comment, but do not delete.

---

## Validation Commands

```bash
# Level 1 — Lint
just lint

# Level 2 — Unit
just test

# Level 2 — Targeted eval (SDK pattern + AWS tools)
just eval-quick 1,2,3,28
just eval-aws

# Level 3 — E2E smoke
just smoke

# Verify no stream_chat in active web imports
grep -rn "stream_chat" server/app/main.py server/app/streaming_routes.py
```

---

## Risk Notes

| Risk | Mitigation |
|------|------------|
| SSE event contract changes | `sdk_query()` output maps to same `TEXT/TOOL_USE/TOOL_RESULT/COMPLETE` types — no frontend change |
| In-memory session cache stale in multi-instance | Pre-existing issue; not introduced by this migration |
| Supervisor prompt truncation | `MAX_SKILL_PROMPT_CHARS = 4000` already guards this |
| `execute_tool` still imported from old module | Intentional — `agentic_service.py` is kept as tool library |

---

*Scribe | 2026-02-22T22:34:55 | plan v1 | Format: markdown | Source: experts:claude-sdk:plan*
