# EAGLE: Strands-Only Migration Plan (Remove Claude SDK)

**Branch:** `dev/strands-conversion-alvee`
**Created:** 2026-03-02
**Updated:** 2026-03-02 (v2.1 — closes implementation gaps for SSE cost, pricing parity, and runtime decoupling)
**Status:** Ready for Implementation
**Goal:** Migrate backend orchestration from Claude Agent SDK to Strands Agents SDK and remove all `claude-agent-sdk` runtime usage.

---

## 1. Scope and Non-Goals

### In Scope

1. Replace `sdk_agentic_service.py` orchestration with Strands-only orchestration.
2. Keep `eagle-plugin/` prompts and `server/eagle_skill_constants.py` as source of truth.
3. Update all three consumption points: SSE streaming route, REST endpoint, and WebSocket endpoint.
4. Implement custom max_turns and budget enforcement (Strands has no built-in equivalents).
5. Remove `claude-agent-sdk` dependency and references.
6. Update tests and docs to Strands-only architecture.
7. Remove runtime orchestration coupling to `agentic_service.py` (shared model/tool metadata must come from Strands path or neutral shared module).

### Out of Scope

1. Redesigning domain prompts in `eagle-plugin/`.
2. UI redesign outside of stream protocol requirements.
3. New infrastructure stacks.
4. Custom DynamoDB session manager for Strands (keep existing `session_store.py`).

---

## 2. Migration Strategy

1. Build Strands service and tools first, in parallel with current SDK code.
2. **Spike on streaming fidelity** — verify inner-agent events surface via `stream_async` before committing.
3. Switch all consumption points (SSE, REST, WebSocket) to Strands once service parity is validated.
4. Update tests and docs.
5. Remove Claude SDK files and dependency only after parity checks pass.

This keeps risk low while still ending in an exclusive Strands runtime.

---

## 3. Target Architecture (Strands-Only)

1. `eagle-plugin/*` remains the source for supervisor and specialist prompts.
2. `eagle_skill_constants.py` continues to auto-discover AGENTS/SKILLS.
3. New `strands_tools.py` creates specialist `@tool` functions from AGENTS/SKILLS via a closure-based factory. Each tool wraps an inner `Agent` with the specialist's system prompt and tier-gated tool set. Supervisor is excluded from the tool registry.
4. New `strands_agentic_service.py` creates supervisor `Agent` with tier-filtered toolset, custom turn-limit hook, and token-based budget tracking.
5. `streaming_routes.py` uses `strands_query()` exclusively for SSE.
6. `main.py` REST (`POST /api/chat`) and WebSocket (`GET /ws/chat`) endpoints also use `strands_query()`.
7. SSE output stays in EAGLE format via `MultiAgentStreamWriter`.
8. Credential handling uses `boto3.Session()` directly — no subprocess env bridging needed (Strands runs in-process, not via CLI subprocess like Claude SDK).

### Key Architectural Differences from Claude SDK

| Concern | Claude SDK | Strands |
|---------|-----------|---------|
| Agent ↔ Subagent | `ClaudeAgentOptions.agents=dict[AgentDefinition]` + `Task` tool | Agents-as-tools pattern: each specialist is a `@tool` wrapping an inner `Agent` |
| Streaming | Yields `AssistantMessage` / `ResultMessage` objects | `stream_async` yields event dicts with keys: `data`, `current_tool_use`, `result`, etc. |
| Turn limit | `max_turns=15` constructor param | Custom hook: count tool calls, set `request_state["stop_event_loop"] = True` |
| Budget limit | `max_budget_usd=0.25` constructor param | Manual token tracking from stream events + enforcement in hook |
| Permissions | `permission_mode="bypassPermissions"` | Not needed — tools execute in-process, no CLI sandbox |
| Credentials | `_get_bedrock_env()` → subprocess env dict | `boto3.Session()` passed to `BedrockModel(boto_session=...)` |
| Usage extraction | `ResultMessage.usage.input_tokens` / `.output_tokens` | `result` event or `agent.token_usage` post-completion |

---

## 4. File Change Plan

### Create

1. `server/app/strands_tools.py` — closure-based tool factory + tier gating
2. `server/app/strands_agentic_service.py` — supervisor agent, streaming, turn/budget hooks, model config
3. `server/tests/test_strands_service.py`

### Modify

1. `server/app/streaming_routes.py` — SSE route cutover
2. `server/app/main.py` — REST endpoint (`POST /api/chat`) and WebSocket endpoint (`GET /ws/chat`) cutover + import wiring
3. `server/requirements.txt` — add `strands-agents`, remove `claude-agent-sdk` (final phase)
4. `README.md` and/or `CLAUDE.md` references to active orchestration backend

### Remove or Archive (final phase)

1. `server/app/sdk_agentic_service.py` (delete or archive)
2. Stale tests that assert Claude SDK message classes (`test_agent_sdk.py`, `test_eagle_sdk_eval.py`)

### Design Decision: No separate `strands_models.py`

`BedrockModel` instantiation is ~10 lines (alias map + factory). Inline it in `strands_agentic_service.py` to avoid unnecessary file proliferation.

---

## 5. Step-by-Step Implementation

## Phase 0: Preflight (No Behavior Change)

1. Create migration branch and checkpoint current passing state.
2. Run baseline checks:
   - `just lint`
   - `just test`
3. Capture reference stream traces from all three endpoints for comparison:
   - `POST /api/chat/stream` (SSE)
   - `POST /api/chat` (REST)
   - `GET /ws/chat` (WebSocket)
4. Document baseline behavior: event types emitted, tool delegation visibility, usage/cost values, timing.

Exit criteria:
- Baseline tests pass.
- Reference stream behavior captured for all three endpoints.

## Phase 1: Dependencies

1. Update `server/requirements.txt`:
   - Add `strands-agents>=0.1.0`.
   - Do NOT add `strands-agents-tools` (not needed — EAGLE uses custom tools only).
   - Keep `claude-agent-sdk` temporarily during transition.
   - Keep `anthropic>=0.40.0` (used by legacy `agentic_service.py` and potentially other code).
2. Install and verify imports in backend environment.

Exit criteria:
- `from strands import Agent, tool` and `from strands.models import BedrockModel` resolve.
- Existing app still runs unchanged.

## Phase 2: Streaming Fidelity Spike

**Purpose:** Validate that Strands `stream_async` surfaces inner-agent events during specialist delegation. This is a known gap (GitHub issues #543, #912) that could silently degrade UX.

1. Write a minimal spike script (`server/scripts/strands_streaming_spike.py`):
   - Create a simple inner agent (specialist) with one tool.
   - Wrap it as an outer agent's tool via the agents-as-tools pattern.
   - Call `outer_agent.stream_async(prompt)` and log ALL event keys.
2. Verify which events propagate:
   - Does `data` stream text from the inner agent in real-time?
   - Does `current_tool_use` fire when the outer agent delegates?
   - Does `result` contain usage metrics?
3. If inner-agent streaming does NOT propagate:
   - Design a workaround: custom `callback_handler` on the inner agent that pushes events to a shared `asyncio.Queue`, consumed by the SSE generator.
   - Document the workaround pattern for Phase 4.

Exit criteria:
- Streaming event taxonomy documented with real observed payloads.
- Inner-agent visibility confirmed OR workaround designed and validated.

## Phase 3: Tool Factory from Plugin Metadata

1. Implement `server/app/strands_tools.py` with a closure-based factory:
   ```python
   def make_specialist_tool(name, description, system_prompt, inner_tools, model):
       @tool(name=name, description=description)
       def specialist(query: str) -> str:
           """Delegate a query to this specialist agent."""
           inner_agent = Agent(
               system_prompt=system_prompt,
               tools=inner_tools,
               model=model,
               callback_handler=None,  # or queue-based handler from Phase 2
           )
           return str(inner_agent(query))
       return specialist
   ```
2. Build registry from `AGENTS` + `SKILLS` (excluding supervisor), using `eagle_skill_constants.py` data.
3. Implement tier gating helper (basic/advanced/premium) while preserving current precedence:
   - If a skill/agent declares explicit tools in plugin metadata, use those tools.
   - Otherwise fall back to tier-default tool lists.
4. Handle `MAX_SKILL_PROMPT_CHARS` truncation (carry over from current `_truncate_skill()`).

Exit criteria:
- Tool registry contains expected set and names matching current `SKILL_AGENT_REGISTRY`.
- Tier filters return expected counts (basic: N tools, advanced: N+M, premium: all).
- Each tool can be invoked standalone and returns a response.

## Phase 4: Strands Orchestration Service

1. Implement `server/app/strands_agentic_service.py`:

   **Model configuration:**
   - Model alias map: `{"haiku": "anthropic.claude-3-haiku-...", "sonnet": "anthropic.claude-sonnet-..."}`
   - `get_bedrock_model(alias, region)` factory using `BedrockModel(model_id=..., boto_session=boto3.Session())`
   - Honor `EAGLE_MODEL` and `AWS_REGION` env vars (optionally support `EAGLE_SDK_MODEL` as temporary backward-compatible fallback)

   **Supervisor construction:**
   - `build_supervisor_prompt(tenant_id, user_id, tier, available_tools)` — loads `agents/supervisor/agent.md`, appends tenant context and tool list
   - Supervisor `Agent` receives specialist tools from `strands_tools.py`, filtered by tier

   **Turn and budget enforcement (custom hooks):**
   - Implement a callback handler or hook that:
     - Counts tool invocations against `max_turns` (default 15, matching current SDK config)
     - Tracks cumulative `input_tokens` + `output_tokens` from stream events
     - Enforces `TIER_BUDGETS` (basic: $0.10, advanced: $0.25, premium: $0.75) using the same token-pricing calculator used for persisted cost records (single source of truth)
     - Sets `request_state["stop_event_loop"] = True` when either limit is hit
   - Emit an `error` event when budget/turn limit is reached (not silent truncation)

   **Query functions:**
   - `strands_query(prompt, tenant_id, user_id, tier, model, skill_names, session_id, max_turns=15)` — async generator yielding normalized events
   - `strands_query_single_skill(prompt, skill_name, tenant_id, user_id, tier, model, max_turns=5)` — direct skill invocation

   **Event normalization:**
   Strands `stream_async` events → internal contract:
   - `data` → `{"type": "text", "content": str}`
   - `current_tool_use` → `{"type": "tool_use", "name": str, "input": dict}`
   - `result` → `{"type": "complete", "usage": {"input_tokens": int, "output_tokens": int}}`
   - Exception/force_stop → `{"type": "error", "message": str}`
   - Inner-agent events (from Phase 2 workaround if needed) → `{"type": "tool_result", ...}` or `{"type": "text", ...}`

2. **Usage extraction:** Ensure every `complete` event includes `input_tokens` and `output_tokens` so downstream cost recording continues to work. Extract from `agent.token_usage` or `result` event payload.
3. **Shared runtime metadata decoupling:** Move/replace imports so `main.py` and `streaming_routes.py` do not depend on `agentic_service.py` for active runtime model/tool metadata when Strands is enabled.

Exit criteria:
- Local direct invocation of `strands_query()` yields normalized events matching the contract above.
- Turn limit halts execution after N tool calls.
- Budget limit halts execution when token cost exceeds tier threshold.
- Usage data is present in the `complete` event.

## Phase 5: Route Cutover (All Three Endpoints)

1. **SSE route** — Update `server/app/streaming_routes.py`:
   - Replace `sdk_query` import with `strands_query`.
   - Remove SDK message-class parsing logic (`AssistantMessage`, `ResultMessage`, `.content` block iteration).
   - Consume normalized events from `strands_query` (dict-based, no type introspection).
   - Persist usage/cost for SSE requests after completion using the same path as REST/WebSocket (`record_request_cost`), with a stable `session_id`.

2. **REST endpoint** — Update `server/app/main.py` `POST /api/chat` (lines 145-249):
   - Replace `sdk_query` with `strands_query`.
   - Remove `type(sdk_msg).__name__` introspection pattern.
   - Extract `text`, `tools_called`, `usage` from normalized events.
   - Preserve `EagleChatResponse` output format.

3. **WebSocket endpoint** — Update `server/app/main.py` `GET /ws/chat` (lines 674-846):
   - Same pattern as REST: replace SDK consumption with normalized event consumption.
   - Preserve WebSocket JSON message format.

4. Keep SSE output schema stable — `MultiAgentStreamWriter` and `StreamEvent` are SDK-agnostic and require no changes.

Exit criteria:
- All three endpoints (`/api/chat/stream`, `/api/chat`, `/ws/chat`) work with Strands backend.
- SSE events match baseline trace from Phase 0 (same event types, same structure).
- Specialist delegation events are visible in the stream (tool_use events fire when supervisor delegates).
- Token usage is captured for all three endpoints and cost is recorded to DynamoDB via the shared cost-recording path.
- Tier gating prevents unauthorized tool access at each tier level.

## Phase 6: Tests and Validation

1. Add `server/tests/test_strands_service.py`:
   - Tool factory: correct tools created from plugin metadata.
   - Tier gating: basic/advanced/premium return expected tool sets and preserve metadata-tools-over-tier-default precedence.
   - Prompt builder: supervisor prompt contains tenant context, user ID, tool list.
   - Event normalization: Strands events map to internal contract.
   - Turn limit: execution halts after max_turns tool calls.
   - Budget limit: execution halts when token cost exceeds tier budget.
   - Pricing parity: budget enforcement uses same calculator/rates as persisted request costs.
   - Usage extraction: `complete` event contains valid token counts.
   - SSE completion path: verifies token usage and cost record persistence, matching REST/WebSocket behavior.
2. Update/remove SDK-specific tests:
   - `test_agent_sdk.py` — remove or rewrite for Strands.
   - `test_eagle_sdk_eval.py` — remove or rewrite for Strands.
3. Run validation ladder:
   - `just lint`
   - `just test`
   - `just dev-up`
   - Streaming smoke via curl (SSE), REST call, and WebSocket connection
   - Compare outputs against Phase 0 baseline traces

Exit criteria:
- All tests pass without importing `claude_agent_sdk`.
- All three stream paths work end-to-end.
- Baseline comparison shows no regression in event types or response quality.

## Phase 7: Remove Claude SDK Completely

1. Remove from `server/requirements.txt`:
   - `claude-agent-sdk`
   - Verify `anthropic>=0.40.0` is still needed (check if legacy `agentic_service.py` or other code uses it). Remove if unused.
2. Delete `server/app/sdk_agentic_service.py`.
3. Delete spike script `server/scripts/strands_streaming_spike.py`.
4. Remove dead imports, comments, and docs referencing SDK as active path.
5. Remove `_get_bedrock_env()` helper if it exists only for SDK subprocess credential bridging.
6. Re-run full validation.

Exit criteria:
- `rg 'claude_agent_sdk|claude-agent-sdk|sdk_query|sdk_agentic_service' server README.md CLAUDE.md` returns no active runtime references.
- App functions with Strands-only backend.
- No orphaned credential-bridging code remains.

## Phase 8: Documentation and Operational Update

1. Update README architecture section to Strands-only.
2. Update CLAUDE.md Backend section: replace SDK references with Strands equivalents.
3. Update health endpoint metadata to indicate Strands backend.
4. Add troubleshooting notes:
   - Strands Bedrock config (model IDs, cross-region inference profiles, boto3 session).
   - Streaming event mapping (Strands events → EAGLE SSE protocol).
   - Turn/budget enforcement (how custom hooks work).

Exit criteria:
- Repo docs match real runtime behavior.
- New developer can understand Strands orchestration from docs alone.

---

## 6. Acceptance Criteria (Definition of Done)

1. All three endpoints (SSE, REST, WebSocket) use Strands-only orchestration.
2. All plugin-defined agents/skills are available via Strands tool registry (except supervisor, which orchestrates).
3. Tier gating works: basic/advanced/premium each get the correct tool set.
4. Turn limits and budget limits are enforced via custom hooks.
5. Token usage is extracted and request costs are recorded to DynamoDB for SSE, REST, and WebSocket using one shared pricing source.
6. No Claude SDK runtime dependency remains.
7. Lint/tests pass and streaming smoke test passes on all three endpoints.
8. Docs reflect Strands as sole orchestration backend.

---

## 7. Risk Register and Mitigations

1. **Risk: Inner-agent streaming events don't propagate through `stream_async`.**
   - Severity: HIGH. GitHub issues #543, #912 indicate tool results and inner-agent progress may not surface.
   - Mitigation: Phase 2 spike validates this before any production code is written. If events don't propagate, implement a queue-based `callback_handler` on inner agents that pushes events to a shared `asyncio.Queue` consumed by the SSE generator.

2. **Risk: No built-in `max_turns` or `max_budget_usd` in Strands.**
   - Severity: MEDIUM. Multi-tenant tier enforcement is a core feature.
   - Mitigation: Implement custom hook in Phase 4 with explicit turn counting and token-based cost tracking. Test all three tiers in Phase 6.

3. **Risk: Strands event payload differs from assumptions.**
   - Mitigation: Phase 2 spike documents real payloads. Lock normalization logic to observed payload keys.

4. **Risk: Behavior regression in tool delegation quality.**
   - Mitigation: Compare outputs on representative prompts before and after cutover using Phase 0 baseline traces.

5. **Risk: Budget/turn controls regress.**
   - Mitigation: Implement explicit guards in service layer and test tier limits. Emit error events (not silent truncation) when limits are hit.

6. **Risk: Hidden SDK coupling in tests/docs.**
   - Mitigation: Final grep gate and CI fail on remaining SDK imports.

7. **Risk: Usage/cost extraction breaks.**
   - Severity: MEDIUM. Multi-tenant billing depends on accurate token counts.
   - Mitigation: Validate `complete` event contains `input_tokens`/`output_tokens` in Phase 4. Cross-check against `agent.token_usage` as fallback.

8. **Risk: REST and WebSocket endpoints forgotten during cutover.**
   - Mitigation: Phase 5 explicitly covers all three endpoints. Phase 0 baseline includes all three.

9. **Risk: Budget enforcement pricing diverges from persisted cost records.**
   - Severity: HIGH. User-facing budget limits and recorded billing can disagree.
   - Mitigation: Centralize pricing calculation in one shared function/module and assert parity in tests.

10. **Risk: Hidden runtime dependency on `agentic_service.py` remains after Strands cutover.**
   - Severity: MEDIUM. “Strands-only” claim is weakened by lingering orchestration coupling.
   - Mitigation: Add explicit grep/import gate for `agentic_service` usage in Strands runtime paths and move shared metadata to neutral module if needed.

---

## 8. Rollback Plan

1. **Point of no return identification:**
   - Phase 5 (route cutover) is the critical commit boundary, NOT Phase 7.
   - Keep a clean commit before Phase 5 that can be reverted atomically.

2. If Strands cutover fails during or after Phase 5:
   - Revert `streaming_routes.py` AND `main.py` to `sdk_query` path (both REST and WebSocket endpoints).
   - Requires restoring the full SDK message-class parsing logic, not just the import.

3. Keep commit boundary before Phase 7 (SDK removal) as secondary checkpoint.

4. If failure after Phase 7 removal:
   - Reinstall `claude-agent-sdk` dependency.
   - Restore `sdk_agentic_service.py` from git history.
   - Revert route/endpoint changes.

---

## 9. Execution Checklist

- [ ] Phase 0 baseline complete (all three endpoints traced)
- [ ] Phase 1 dependencies installed
- [ ] Phase 2 streaming spike complete (inner-agent visibility confirmed or workaround ready)
- [ ] Phase 3 tool factory complete
- [ ] Phase 4 orchestration + turn/budget hooks complete
- [ ] Phase 5 all three endpoints cut over
- [ ] Phase 6 tests green + baseline comparison clean
- [ ] Phase 7 Claude SDK removed
- [ ] Phase 8 docs updated
- [ ] Final grep gate clean

---

## 10. Suggested Command Sequence

```bash
# Phase 0: Baseline
just lint
just test
# Capture SSE trace
curl -X POST http://localhost:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message":"I need to buy lab equipment for $85,000"}' \
  --no-buffer > baseline_sse.txt
# Capture REST trace
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"I need to buy lab equipment for $85,000"}' > baseline_rest.json
# Capture WebSocket trace (example with websocat)
printf '{"type":"chat.send","message":"I need to buy lab equipment for $85,000"}\n' | \
  websocat ws://localhost:8000/ws/chat > baseline_ws.jsonl

# Phase 2: Streaming spike
cd server && python scripts/strands_streaming_spike.py

# During migration
cd server
python -m ruff check app/
python -m pytest tests/ -v

# Phase 5-6: End-to-end smoke
just dev-up
curl -X POST http://localhost:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message":"I need to buy lab equipment for $85,000"}' \
  --no-buffer
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"I need to buy lab equipment for $85,000"}'
just dev-down

# Phase 7: Final gate — ensure Claude SDK is removed
rg 'claude_agent_sdk|claude-agent-sdk|sdk_query|sdk_agentic_service' server README.md CLAUDE.md
```
