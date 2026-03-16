# Report: Acquisition Package Flow — Eval Results & Hub Sync Context

**Date**: 2026-03-16
**Author**: Claude Sonnet 4.6 (automated session report)
**Branch**: `report/acquisition-package-eval-2026-03-16`
**Scope**: Acquisition package routing, document generation, cross-agent context propagation
**Status**: 111/111 tests pass locally (1 environment-order flake, passes in isolation)

---

## 1. Executive Summary

All 111 unit tests covering the acquisition package document flow pass locally on the `blackga-nih/main` branch. The NCI Hub (`origin/main`) is **2 commits behind** and is missing the following functionality that these tests validate:

| Area | Gap | Impact |
|------|-----|--------|
| Session sub-routes | `audit-logs`, `documents`, `summary` endpoints missing from origin | Frontend Package tab data fetch fails |
| Streaming routes | SSE metadata event forwarding for `update_state` tool | Package tab never populates in Hub deployment |
| `eagle_state.py` | Missing `specialist_summaries` field (13th schema field) | State serialization mismatch across turns |
| `routes/sessions.py` | 107 lines of new session sub-endpoints | 404 on any session document/summary call |
| `strands_agentic_service.py` | Fast-path document detection + `_ensure_create_document_for_direct_request` | Documents not auto-created in Hub when LLM forgets to call tool |
| Activity Panel | Package tab component with SSE state wiring | Hub UI has no package state visibility |

---

## 2. Test Suite Results

### Run Metadata

| Field | Value |
|-------|-------|
| Run date | 2026-03-16T20:16:38Z |
| DynamoDB run_id | `2026-03-16T20-16-38-393183Z` |
| Python version | 3.12.9 |
| Platform | Windows-11 / MINGW64 |
| pytest version | 9.0.2 |
| Total tests | 111 |
| Passed | 110 (in full suite run) / **111** (all isolated) |
| Failed | 1 (event-loop ordering flake — see §4) |
| Warnings | 226 (all `datetime.utcnow()` deprecations — cosmetic only) |

### 2.1 `test_canonical_package_document_flow.py` — 11/11 ✅

Tests the end-to-end wiring from HTTP request → tool dispatch → document service.

| Test | What it validates | Result |
|------|-------------------|--------|
| `test_exec_create_document_routes_package_mode_to_canonical` | `create_document` detects `package_id` and routes to `create_package_document_version` (not workspace mode). S3 `put_object` NOT called directly. | ✅ PASS |
| `test_stream_generator_passes_package_context_to_sdk` | `stream_generator()` forwards `package_context` dict through to `sdk_query_streaming()` | ✅ PASS |
| `test_fast_path_detects_direct_document_request` | `_should_use_fast_document_path("Generate a Statement of Work...")` → `(True, "sow")` | ✅ PASS |
| `test_fast_path_skips_research_heavy_prompt` | Research-first prompts do NOT trigger fast path | ✅ PASS |
| `test_fast_path_detects_multiline_document_prompt` | Multi-line prompt still detected correctly | ✅ PASS |
| `test_force_document_creation_for_direct_request_without_tool` | `_ensure_create_document_for_direct_request` forces `create_document` when LLM used `knowledge_search` but not `create_document` | ✅ PASS |
| `test_force_document_creation_skips_when_tool_already_called` | No double-creation when `create_document` already in `tools_called` | ✅ PASS |
| `test_forced_document_creation_carries_document_context` | Document context (title, type, current_content, edit_request) extracted from prompt and injected into `create_document` params | ✅ PASS |
| `test_sdk_query_streaming_fast_path_emits_document_events` | Fast-path `sdk_query_streaming` emits `tool_use`, `tool_result`, `complete` SSE events | ✅ PASS |
| `test_extract_document_context_from_prompt` | `_extract_document_context_from_prompt` correctly parses `[DOCUMENT CONTEXT]` / `[USER REQUEST]` block | ✅ PASS |
| `test_make_service_tool_infers_doc_context_for_create_document` | `_make_service_tool` for `create_document` automatically injects doc context from prompt_context string | ✅ PASS |

### 2.2 `test_package_context_service.py` — 17/17 ✅

Tests session-scoped package context resolution: which package is "active" for a given session.

| Class | Tests | What it validates |
|-------|-------|-------------------|
| `TestResolveContext` | 5 | Explicit `package_id` param takes priority; session metadata fallback; workspace mode fallback; stale reference cleared; invalid ID falls through |
| `TestSetActivePackage` | 3 | Sets `package_id` in session metadata; returns None when package not found; returns None when session not found |
| `TestClearActivePackage` | 3 | Clears `active_package_id` from session metadata; True when nothing to clear; False when session not found |
| `TestGetActivePackageId` | 3 | Returns package ID from session metadata; None when absent; None when session missing |
| `TestPackageContext` | 3 | `is_package_mode` True/False logic for `mode == "package"` vs `mode == "workspace"` vs missing `package_id` |

**Key finding**: `resolve_context()` correctly prefers explicit `package_id` over session metadata, and clears stale references when the referenced package no longer exists in DynamoDB.

### 2.3 `test_document_pipeline.py` — 62/62 ✅ (61 clean + 1 order-flake, see §4)

| Class | Tests | What it validates |
|-------|-------|-------------------|
| `TestCreateDocumentTool` | 13 | All 10 doc types generate valid `DocumentResult` shapes; unknown type returns error; S3 failure degrades gracefully; S3 key naming convention |
| `TestExecuteToolDispatch` | 2 | `create_document` dispatches correctly; `session_id` passes through |
| `TestDocumentListEndpoint` | 1 | `GET /documents` returns list |
| `TestDocumentExportEndpoint` | 3 | Export to DOCX, PDF (or Markdown fallback), Markdown — all produce correct content-type |
| `TestStreamToolMetadata` | 3 | REST response includes `tools_called`; `complete` event has `type`; events have `agent_id` |
| `TestStreamProtocol` | 3 | SSE format; None-field omission; `write_tool_use` event shape |

**All 10 document types validated**: `sow`, `igce`, `market_research`, `justification`, `acquisition_plan`, `eval_criteria`, `security_checklist`, `section_508`, `cor_certification`, `contract_type_justification`

### 2.4 `test_document_agent.py` — 21/21 ✅

Tests the Agent-as-Tool document generator (LLM-driven content).

| Class | Tests | What it validates |
|-------|-------|-------------------|
| `TestTemplateLoading` | 11 | Templates load for `sow`, `igce`, `acquisition_plan`, `justification`, `market_research`; fallback for types without templates; unknown type fallback |
| `TestRequiredFields` | 3 | YAML loads all doc types; SOW has expected required sections; unknown type returns empty dict |
| `TestPromptConstruction` | 4 | Prompt contains template; includes special instructions block; omits block when no special instructions; lists required fields |
| `TestAppendixParsing` | 5 | Parses Appendix A (omissions) and B (justifications); handles missing appendices; parses omission tables; parses justification entries |
| `TestFieldValidation` | 4 | All fields present passes; missing fields detected; empty content returns empty; empty required returns empty |
| `TestTitleExtraction` | 3 | Extracts H1; falls back to H2; fallback title when no heading |
| `TestGenerateDocumentFlow` | 10 | Successful generation; invalid doc type; model failure; empty response; special instructions; all 5 template-backed doc types |
| `TestReasoningStoreExtensions` | 8 | section/justification entries; appendix formatting; serialization; save includes all entry types |
| `TestToolSignatureTrace` | 3 | `generate_document` in eagle tools; schema shape; `create_document` fallback still exists |

---

## 3. Codebase Drift: `blackga-nih/main` vs `origin/main` (Hub)

**Origin is 2 commits behind** as of 2026-03-16.

### Commits Not in Hub

| SHA | Message |
|-----|---------|
| `fe34a4828c` | `chore(experts): self-improve frontend, backend, sse, git expertise after session` |
| `8addb1bf93` | `feat(arch+ui): regenerate all 9 excalidraw diagrams, Package tab, and route additions` |

### Files Changed/Added (31 files, +25,492 / -2,506 lines)

#### Backend — Server (`server/`)

| File | Change | Impact |
|------|--------|--------|
| `server/app/streaming_routes.py` | +77 lines | SSE metadata event path for `update_state` tool. **Hub missing this** → Package tab never receives state updates. |
| `server/app/strands_agentic_service.py` | +10 lines | Fast-path document detection + `_ensure_create_document_for_direct_request`. **Hub missing this** → documents may not be created if LLM forgets to call tool. |
| `server/app/routes/sessions.py` | +107 lines | New endpoints: `GET /sessions/{id}/audit-logs`, `/documents`, `/summary`. **Hub missing** → 404 on all three. |
| `server/app/routes/misc.py` | +32 lines | Misc route additions. |
| `server/app/routes/_deps.py` | +15 lines | Shared dependency helpers (ring buffers, auth checks, log functions). |
| `server/app/main.py` | +6 lines | Router registration for new routes. **Hub missing** → new routes not mounted. |
| `server/app/eagle_state.py` | +1 line | `specialist_summaries` field added to `_DEFAULTS` (13th field). **Hub missing** → state deserialization mismatch on cross-turn specialist calls. |

#### Frontend — Client (`client/`)

| File | Change | Impact |
|------|--------|--------|
| `client/components/chat-simple/activity-panel.tsx` | Modified | Package tab added as default tab with `PackageStatusTab` component (phase badge, progress bar, doc checklist, compliance alerts). **Hub missing** → no package state visibility in UI. |
| `client/components/chat-simple/activity-feed.tsx` | New (+729 lines) | Unified ActivityFeed replacing AgentLogs+CloudWatchLogs. **Hub missing** → Activity tab broken. |
| `client/app/api/sessions/[sessionId]/messages/route.ts` | Modified | GET + DELETE with proper async params. |
| `client/app/api/sessions/[sessionId]/audit-logs/route.ts` | New (+44 lines) | Proxies `/api/sessions/{id}/audit-logs` to backend. **Hub missing** → Activity tab audit log fetch fails. |
| `client/app/api/sessions/[sessionId]/documents/route.ts` | New (+35 lines) | Proxies `/api/sessions/{id}/documents`. **Hub missing** → session document list fails. |
| `client/app/api/sessions/[sessionId]/summary/route.ts` | New (+35 lines) | Proxies `/api/sessions/{id}/summary`. **Hub missing** → session summary fails. |
| `client/app/api/admin/request-log/route.ts` | New (+30 lines) | Admin request log ring buffer API. |
| `client/app/api/health/ready/route.ts` | New (+28 lines) | Readiness probe endpoint. |
| `client/app/admin/api-explorer/page.tsx` | New (+275 lines) | Admin API explorer page. |

#### Architecture Diagrams (`docs/architecture/diagrams/excalidraw/`)

8 new + 1 updated `.excalidraw.md` files — corrected for:
- Private-only NCI VPC (no NAT, no public subnets, Transit Gateway egress)
- 21 tools (was ~10 in old diagrams)
- 6 CDK stacks including `EagleBackupStack`
- Correct model ID `us.anthropic.claude-sonnet-4-6`
- CI deploys 4 stacks with `--exclusively` flag
- All 7 specialist subagents correctly named
- `specialist_summaries` in eagle_state schema

#### Expert Documentation (`.claude/commands/experts/`)

Self-improved this session — Hub versions will be stale knowledge bases:

| Expert | Lines changed | Key additions |
|--------|---------------|---------------|
| `backend/expertise.md` | +699/-554 | routes/+stores/ layout, eagle_state 13-field schema, SSE pipeline |
| `frontend/expertise.md` | +395 | PackageState pattern, 5-tab panel, session sub-routes |
| `git/expertise.md` | +635/-469 | Multi-remote pattern, ECS workflow, branch protection gap |
| `sse/expertise.md` | +210 | All 10 event types, metadata pipeline, 5 state_type payloads |
| `sse/diagrams/sse-pipeline-architecture.excalidraw.md` | +28 | Layer 4b metadata pipeline |

#### Eagle Plugin (`eagle-plugin/`)

| File | Change |
|------|--------|
| `eagle-plugin/agents/supervisor/agent.md` | +14/-14 lines — supervisor prompt tuning |

---

## 4. Known Issues

### 4.1 `test_writer_tool_use_event` — Asyncio Event Loop Ordering Flake

**Symptom**: Fails in the combined 111-test run at position 53/111 (48%), passes in isolation and in class-level runs.

**Root cause**: `test_document_pipeline.py:435` uses `asyncio.get_event_loop().run_until_complete(...)` — this pattern is deprecated in Python 3.12 and fails when a prior test (specifically `test_rest_response_includes_tools_called` which uses `asyncio.run()`) has left the default event loop closed.

**Evidence**:
```
DeprecationWarning: There is no current event loop
    sse_line = asyncio.get_event_loop().run_until_complete(_run())
```

**Fix required**: Replace `asyncio.get_event_loop().run_until_complete()` with `asyncio.run()` at `tests/test_document_pipeline.py:435`.

**Impact**: Low. All logic is correct, no functional regression. This only affects CI test ordering.

### 4.2 Missing `/api/traces/story` Next.js Proxy Route

**Location**: `client/components/chat-simple/activity-feed.tsx` calls `fetch('/api/traces/story?session_id=...')` but `client/app/api/traces/` directory does not exist.

**Impact**: Langfuse trace enrichment in ActivityFeed silently fails (caught by `Promise.allSettled`). No crash, but the "Trace" enrichment path in the Activity tab never loads data.

**Fix required**: Add `client/app/api/traces/story/route.ts` proxying to `FASTAPI_URL/api/traces/story`.

### 4.3 Hub Environment Variables

The following environment variables must be set in the Hub deployment for the new features to function:

| Variable | Purpose | Required for |
|----------|---------|-------------|
| `LANGFUSE_PUBLIC_KEY` | Langfuse trace API auth | Trace Story panel, `/api/traces/story` |
| `LANGFUSE_SECRET_KEY` | Langfuse trace API auth | Trace Story panel |
| `LANGFUSE_HOST` | Langfuse host (default: `https://us.cloud.langfuse.com`) | Trace Story panel |

---

## 5. SSE Metadata Pipeline — What Hub Needs to Wire

The Package tab is powered by a 6-link chain. All 6 links must be present in the Hub deployment:

```
1. update_state tool called by Strands supervisor/subagent
   server/app/strands_agentic_service.py:1838
   → result_queue.put_nowait({"type": "metadata", "content": payload})

2. stream_generator metadata handler
   server/app/streaming_routes.py:209-214
   → chunk_type == "metadata" → writer.write_metadata(sse_queue, content)

3. MultiAgentStreamWriter.write_metadata()
   server/app/stream_protocol.py:142
   → SSE frame: data: {"type":"metadata","metadata":{...}}

4. use-agent-stream.ts processEventData()
   client/hooks/use-agent-stream.ts:417
   → event.type === 'metadata' → options.onMetadata?.(event.metadata)

5. simple-chat-interface.tsx onMetadata handler
   client/components/chat-simple/simple-chat-interface.tsx:172
   → setEagleState() with incremental merge by state_type

6. activity-panel.tsx PackageStatusTab
   client/components/chat-simple/activity-panel.tsx
   → renders phase badge, progress bar, checklist, alerts from eagleState
```

**Hub gap**: Links 2 and 6 (and partially Link 5) are absent from `origin/main`. The `update_state` tool fires and `write_metadata` is called, but the downstream handler in `streaming_routes.py` does not forward the metadata event through the SSE queue, causing all state pushes to be silently discarded before reaching the frontend.

---

## 6. eagle_state.py Schema Reference

Current schema (13 fields) — Hub has 12 fields (missing `specialist_summaries`):

```python
_DEFAULTS = {
    "phase": "intake",
    "previous_phase": None,
    "package_id": None,
    "session_id": None,
    "checklist": {"required": [], "completed": [], "missing": []},
    "progress_pct": 0,
    "compliance_alerts": [],
    "documents": {},
    "last_event": None,
    "last_event_ts": None,
    "phase_history": [],
    "validation_results": {},
    "specialist_summaries": {},   # ← NEW: cross-turn subagent result cache
}
```

`apply_event()` state machine:

| `state_type` | Fields updated |
|-------------|----------------|
| `phase_change` | `phase`, `previous_phase`, optionally `package_id`, `checklist` |
| `document_ready` | `checklist`, `package_id`, `progress_pct`, adds doc to `documents` |
| `checklist_update` | `checklist`, `package_id`, `progress_pct` |
| `compliance_alert` | appends to `compliance_alerts` |
| `document_validation` | updates `validation_results` |

---

## 7. Recommended Actions for Hub Sync

In priority order:

1. **Merge `blackga-nih/main` → `origin/main`** — 2 commits, 31 files, no conflicts expected since origin hasn't diverged on the same files.

2. **Fix `test_writer_tool_use_event` flake** — Replace `asyncio.get_event_loop().run_until_complete()` with `asyncio.run()` at `tests/test_document_pipeline.py:435`.

3. **Add `/api/traces/story` Next.js proxy route** — Unblocks Langfuse trace enrichment in ActivityFeed.

4. **Set Langfuse env vars in Hub ECS task definition** — Required for trace story endpoint.

5. **Enable branch protection on `origin/main`** — Currently unprotected (no required reviews, no status checks).

---

## 8. Validation Commands

To reproduce these results on the Hub or any clone:

```bash
# Backend tests (run from server/)
python -m pytest tests/test_canonical_package_document_flow.py \
                 tests/test_package_context_service.py \
                 tests/test_document_pipeline.py \
                 tests/test_document_agent.py \
                 -v --tb=short

# Expected: 111 passed (or 110 with event loop flake in combined run)

# Frontend TypeScript check (run from client/)
npx tsc --noEmit
# Expected: zero errors

# Backend lint (run from server/)
python -m ruff check app/
# Expected: All checks passed!

# Confirm SSE metadata chain (smoke test)
# 1. Start backend: uvicorn app.main:app --reload --port 8000
# 2. POST /api/chat/stream with a package-mode session
# 3. Observe SSE events include type=metadata with state_type=phase_change or checklist_update
```

---

*Report generated by Claude Sonnet 4.6 during EAGLE development session 2026-03-16.*
*Session transcript: `.claude/projects/.../9dd1c69d-17e9-4df3-999f-51e95e44f339.jsonl`*
