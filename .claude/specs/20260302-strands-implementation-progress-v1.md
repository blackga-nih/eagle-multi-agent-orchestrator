# EAGLE Strands Migration Progress Plan

**Date:** 2026-03-02  
**Scope:** Progress checkpoint after initial Strands cutover work  
**Objective:** Document completed phases, next implementation steps, and validation required now

---

## 1. Completed So Far

### Phase 1 (Dependencies) — Partially Complete
- Added `strands-agents>=0.1.0` to `server/requirements.txt`.
- `claude-agent-sdk` is still present (expected during transition).

### Phase 2 (Streaming Fidelity Spike) — Scaffold Complete
- Added spike script: `server/scripts/strands_streaming_spike.py`.
- Script is ready to run to inspect raw `stream_async` event keys/payloads.
- Not yet executed in this environment.

### Phase 3 (Tool Factory) — Initial Implementation Complete
- Added `server/app/strands_tools.py`.
- Implemented registry construction from `AGENTS` + `SKILLS` + `plugin.json`.
- Preserved precedence rule:
  - metadata-defined tools first
  - tier defaults only when metadata tools are empty
- Added prompt truncation parity (`MAX_SKILL_PROMPT_CHARS`).

### Phase 4 (Strands Orchestration Service) — Initial Implementation Complete
- Added `server/app/strands_agentic_service.py`.
- Implemented:
  - Bedrock model factory via `BedrockModel` + `boto3.Session`
  - model alias resolution (`EAGLE_MODEL` with fallback to `EAGLE_SDK_MODEL`)
  - supervisor prompt builder from plugin supervisor prompt
  - normalized event contract (`text`, `tool_use`, `complete`, `error`)
  - tier normalization (`free`→`basic`, `enterprise`→`premium`)
  - budget checks using shared `calculate_cost()` path

### Phase 5 (Route Cutover) — Initial Cutover Complete
- Updated SSE route (`server/app/streaming_routes.py`) to use `strands_query()`.
- Updated REST endpoint (`POST /api/chat`) in `server/app/main.py` to use normalized Strands events.
- Updated WebSocket endpoint (`GET /ws/chat`) in `server/app/main.py` to use normalized Strands events.
- Added SSE usage/cost persistence (`record_request_cost`) on completion.
- Removed active runtime dependency on `agentic_service` constants in cutover paths:
  - model now from `get_active_model()`
  - tool docs now from `get_tools_for_api()`

### Phase 6 (Tests) — Started
- Added `server/tests/test_strands_service.py` with initial coverage for:
  - tier precedence
  - metadata discovery
  - event normalization
  - tier normalization
  - budget guard behavior

---

## 2. What Is Not Complete Yet

### Phase 2 Validation Pending
- Spike script has not been run to confirm inner-agent event propagation behavior.

### Phase 4 Hardening Pending
- Turn-limit enforcement currently keyed off `tool_use` count in normalized stream loop; needs runtime verification under real workloads.
- Usage extraction relies on best-effort event parsing; needs empirical validation against actual Strands payloads.

### Phase 6 Full Validation Pending
- New tests were added but not executed here (`pytest` unavailable in environment used during implementation).
- Lint/type/test suite has not yet been run end-to-end after cutover.

### Phase 7/8 Not Started
- SDK dependency removal and file deletion not done.
- Docs (`README.md`, `CLAUDE.md`) still contain SDK-primary language.

---

## 3. Immediate Next Steps

1. Install dependencies and run the new Strands test module.
2. Run the streaming spike and capture real event taxonomy.
3. Smoke-test all three endpoints (SSE/REST/WebSocket) with Strands backend.
4. Compare behavior vs baseline traces (event shape + delegation visibility + usage/cost recording).
5. Harden any gaps found in usage extraction, tool events, or limit enforcement.
6. Run full lint/test ladder.
7. Proceed to SDK removal (Phase 7) only after parity is confirmed.

---

## 4. Test Plan for Current Completed Phases

## A. Environment + Imports

1. Install backend deps:
   - `cd server && pip install -r requirements.txt`
2. Verify Strands imports:
   - `python3 -c "from strands import Agent, tool; from strands.models import BedrockModel; print('ok')"`

Expected:
- Imports succeed with no `ModuleNotFoundError`.

## B. Unit Tests (Current Phase Artifacts)

1. Run new test module:
   - `cd server && python3 -m pytest -q tests/test_strands_service.py`

Expected:
- All tests pass.

## C. Streaming Fidelity Spike (Phase 2)

1. Run spike:
   - `cd server && python3 scripts/strands_streaming_spike.py`

Validate:
- Which keys appear per stream event (`data`, `current_tool_use`, `result`, etc.).
- Whether nested/inner agent progress appears in-stream.
- Whether usage appears in `result` event payload.

Expected:
- Clear event taxonomy captured for final normalization adjustments.

## D. Endpoint Smoke Tests

Precondition:
- Backend running locally.

1. SSE:
   - `curl -X POST http://localhost:8000/api/chat/stream -H "Content-Type: application/json" -d '{"message":"I need to buy lab equipment for $85,000","tenant_context":{"tenant_id":"dev-tenant","user_id":"dev-user","session_id":"sse-test-1","subscription_tier":"advanced"}}' --no-buffer`
2. REST:
   - `curl -X POST http://localhost:8000/api/chat -H "Content-Type: application/json" -d '{"message":"I need to buy lab equipment for $85,000"}'`
3. WebSocket (example):
   - `printf '{"type":"chat.send","message":"I need to buy lab equipment for $85,000"}\n' | websocat ws://localhost:8000/ws/chat`

Validate:
- Responses complete successfully (no runtime exceptions).
- `tool_use` events are emitted when delegation occurs.
- `usage` appears in final REST/WS payloads.
- SSE stream emits `complete` and records cost.

## E. Cost Recording Checks

1. Submit one request via each endpoint.
2. Query cost records using existing admin/usage endpoints or DynamoDB inspection.

Validate:
- Cost records exist for SSE, REST, and WebSocket.
- `input_tokens`, `output_tokens`, `model`, `tools_used`, and response time are populated.

## F. Regression/Quality Checks

1. Run lint/tests:
   - `just lint`
   - `just test`
2. Compare current outputs to baseline traces from pre-migration capture.

Validate:
- No schema regressions in stream event envelope.
- No major loss in delegation quality or response completeness.

---

## 5. Exit Criteria for This Checkpoint

- Strands imports/install verified.
- New Strands unit tests pass.
- Spike event taxonomy documented with observed payloads.
- SSE/REST/WebSocket all run successfully on Strands path.
- Usage/cost recorded for all three endpoints.
- Any discovered event-mapping gaps logged and patched before SDK removal.

