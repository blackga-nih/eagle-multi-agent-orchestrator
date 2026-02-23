# Eval Plan: SDK Migration Sign-Off Strategy

**Date**: 2026-02-22T22:40:42
**Type**: Eval plan — pre-flip validation for sdk_agentic_service migration
**Status**: Plan (not yet executed)
**Author**: experts:eval:plan
**Precursors**:
- `.claude/specs/20260222-223455-plan-claude-sdk-sdk-migration-v1.md`
- `.claude/specs/20260222-223657-plan-backend-sdk-wiring-v1.md`

---

## 1. Summary

The migration wires `sdk_agentic_service.sdk_query()` as the default orchestration path,
replacing `agentic_service.stream_chat()` in `streaming_routes.py` and `main.py`. The
change is a pure wiring swap — both implementations already exist. This plan determines
whether test 28 alone is a sufficient acceptance gate, assesses which existing tests remain
valid, identifies coverage gaps for the new SDK path (particularly SSE streaming), and
defines the pre-flip checklist and post-flip monitoring strategy.

---

## 2. Migration Impact Matrix

### Files Changed by the Wiring Flip

| File | Nature of Change | Eval Impact |
|------|-----------------|-------------|
| `server/app/streaming_routes.py` | Import swap + `stream_generator()` rewrite | **New SSE path — not yet tested by any eval test** |
| `server/app/main.py` | Import swap + 3 call site adapters (REST + WebSocket + `/api/tools`) | WebSocket path change — not directly tested by eval |
| `server/app/agentic_service.py` | 1-line deprecation comment above `stream_chat` | Zero impact — `execute_tool` untouched, import at line 32 unaffected |
| `server/app/sdk_agentic_service.py` | No changes — already implemented | Test 28 already covers this module |

### Files NOT Changed (eval suite safety)

| File | Status |
|------|--------|
| `server/tests/test_eagle_sdk_eval.py` line 32: `from agentic_service import execute_tool` | **Still valid** — `execute_tool` preserved |
| `server/tests/test_eagle_sdk_eval.py` line 2910: `from sdk_agentic_service import ...` | **Still valid** — module unchanged |

---

## 3. Test-by-Test Analysis

### 3.1 Is Test 28 Sufficient as the Sole SDK Path Acceptance Gate?

**Short answer: No — test 28 is necessary but not sufficient.**

Test 28 validates the `sdk_agentic_service` module in isolation (direct Python invocation).
It does NOT touch the SSE streaming layer (`streaming_routes.py`) or the REST/WebSocket
adapters in `main.py`. After the wiring flip, `sdk_query()` will be invoked via these
web-layer wrappers, not directly. The following gaps exist:

| What Test 28 Validates | What It Does NOT Validate |
|------------------------|--------------------------|
| `build_skill_agents()` builds AgentDefinitions correctly | SSE event contract from `stream_generator()` |
| `build_supervisor_prompt()` generates valid routing prompt | `MultiAgentStreamWriter` queue-drain loop behavior |
| `sdk_query()` supervisor delegates to subagents via Task tool | `AssistantMessage.content` walk in `stream_generator()` |
| `parent_tool_use_id` chain in subagent calls | `ResultMessage` → COMPLETE event emission |
| Cost accumulation and message collector output | REST adapter (`api_chat()` → `result` dict shape) |
| MCP cleanup race condition on Windows (ExceptionGroup) | WebSocket adapter (`websocket_chat()` callback firing) |

**Verdict**: Test 28 is the primary SDK acceptance gate for the orchestration layer. It
must pass. The Playwright smoke tests (`just smoke`) serve as the SSE streaming acceptance
gate — they exercise the full HTTP stack including the `stream_generator()` path.

---

### 3.2 Do Tests 1–6 (SDK Patterns) Cover the `sdk_query()` Session/Resume Flow?

**Yes for session primitives; No for the `sdk_query()` wrapper itself.**

| Test | Validates | Covers sdk_query()? |
|------|-----------|---------------------|
| 1 — Session Creation | `query()` + `SystemMessage.data.session_id` capture | Indirectly — same `query()` primitive used inside `sdk_query()` |
| 2 — Session Resume | `query(resume=session_id)` | Indirectly — `sdk_query()` accepts `session_id` param |
| 3 — Trace Observation | `ThinkingBlock`, `TextBlock`, `ResultMessage` shapes | Confirms SDK message types `sdk_query()` yields |
| 4 — Subagent Orchestration | `AgentDefinition` + `Task` tool + `parent_tool_use_id` | Same pattern as `sdk_query()` uses internally |
| 5 — Cost Tracking | `ResultMessage.usage` accumulation | `sdk_query()` streams the same `ResultMessage` |
| 6 — Tier-Gated MCP | MCP server + `ClaudeAgentOptions` tool gating | Different entrypoint; not directly exercising `sdk_query()` |

**Assessment**: Tests 1–6 provide strong SDK primitive coverage that confirms the building
blocks `sdk_query()` relies on are functional. They do NOT call `sdk_query()` itself, so
they cannot catch regressions in the `sdk_query()` wrapper signature or its `skill_names`
parameter handling. Test 28 owns that coverage.

The session/resume flow in `sdk_query()` (the `session_id` parameter passed through to
`query()`) is not independently tested. If a regression were introduced in how `sdk_query()`
threads `session_id` into the underlying `query()` call, tests 1–6 would still pass and
test 28 does not validate session resumption (it only calls `sdk_query()` once without a
prior `session_id`). **This is a gap** — see Section 4.

---

### 3.3 Do Tests 16–20 Remain Valid After the Wiring Change?

**Yes — tests 16–20 are completely unaffected.**

| Test | What It Calls | Import Source | Impacted by Wiring Change? |
|------|--------------|---------------|---------------------------|
| 16 — S3 Document Ops | `execute_tool("s3_document_ops", ...)` | `from agentic_service import execute_tool` (line 32) | No — `execute_tool` untouched |
| 17 — DynamoDB Intake | `execute_tool("dynamodb_intake", ...)` | Same | No |
| 18 — CloudWatch Logs | `execute_tool("cloudwatch_logs", ...)` | Same | No |
| 19 — Document Generation | `execute_tool("create_document", ...)` | Same | No |
| 20 — CloudWatch E2E | `execute_tool("cloudwatch_logs", ...)` + boto3 describe | Same | No |

**Reasoning**: The wiring change touches `streaming_routes.py` and `main.py` only.
`agentic_service.execute_tool` is a direct tool dispatcher with no dependency on
`stream_chat` or any web-layer concern. Its import at `test_eagle_sdk_eval.py:32` is a
module-level import — it will resolve identically before and after the migration.
Tests 16–20 are deterministic, fast, and free (no Bedrock calls). They should be run as
a canary to confirm no accidental `agentic_service.py` corruption during the wiring change.

---

### 3.4 Is There a Test That Validates SSE Streaming from `sdk_query()`?

**No dedicated eval test exists for the SSE streaming path. This is the most significant gap.**

The eval suite (`test_eagle_sdk_eval.py`) invokes `sdk_query()` directly (Python-to-Python).
It does NOT:
- Start a FastAPI server
- Send an HTTP request to `/api/stream`
- Verify that `stream_generator()` emits properly formed `data: {...}\n\n` SSE events
- Verify that `MultiAgentStreamWriter.write_text()` / `write_complete()` / `write_error()`
  are called in the correct order when consuming `sdk_query()` output

The Playwright smoke tests (`just smoke` / `just smoke mid`) DO exercise the SSE endpoint
through the browser. They cover:
- Page load with chat UI
- Chat message submission
- Response display (confirms the frontend received a non-empty response stream)

The smoke tests are therefore the effective SSE streaming acceptance gate. They are run
against the full Docker stack (`just dev-up && just smoke`).

**If the smoke tests are not run pre-flip, the SSE streaming path is untested.**

---

## 4. Gap Analysis

| Gap | Tier | Recommendation | Effort |
|-----|------|----------------|--------|
| **G1: No SSE streaming test for `sdk_query()` path** | Critical | Run `just smoke mid` as mandatory pre-flip gate. Covers `stream_generator()` end-to-end via browser. Accept this gap in the eval suite itself (Playwright covers it). | Low — already exists, just run it |
| **G2: No `sdk_query()` session-resume test** | Medium | Accept risk for v1. The `sdk_query()` session_id passthrough is a thin wrapper over `query(resume=session_id)` which is proven by test 2. Add a test 29 (`29_sdk_query_session_resume`) post-flip if production session issues are observed. | Medium — new test needed |
| **G3: No `main.py` REST adapter test** | Medium | Accept risk. The `api_chat()` adapter collects `full_text`, `usage`, `tools_called` from the async generator. The shape is trivially verified by the existing chat E2E in smoke `full` level. No dedicated unit test needed for v1. | Low — smoke `full` covers it |
| **G4: No WebSocket adapter test** | Low | Accept risk. `websocket_chat()` is not exercised by current smoke tests. The WebSocket path is secondary to SSE for the EAGLE frontend. Mark as known gap; test in a future eval test 29+ targeting WebSocket. | Medium — deferred |
| **G5: `TOOL_RESULT` SSE events no longer emitted** | Low | Accept by design. The SDK handles tool execution internally in subagents; tool results surface as `AssistantMessage` text blocks. The frontend must not depend on `TOOL_RESULT` events for correctness. Verify in smoke tests that the frontend renders properly without `TOOL_RESULT` events. | Low — verify in smoke |
| **G6: `sdk_query()` ExceptionGroup on prod Windows** | Informational | Non-blocking. Test 28 already handles this with the `ExceptionGroup` guard. On Linux/ECS this does not occur. Documented in existing test. | None |
| **G7: Test 28 uses only 2 of 6 skill subagents for cost control** | Low | Accept. The delegation pattern is validated with 2 subagents; adding all 6 would multiply Bedrock cost without finding new failure modes. The `build_skill_agents()` step validates all 12 agent definitions deterministically (no LLM call). | None |

### Summary: 1 critical gap (G1), 2 medium gaps (G2, G3), rest informational.

**G1 resolution**: `just smoke mid` is already in the acceptance criteria in both upstream
plans. This plan formalises it as a required pre-flip step, not optional.

---

## 5. Pre-Flip Test Matrix

Run all checks in this order. Each step is a gate — do not proceed if any step fails.

| Step | Command | What It Validates | Expected Result | Level |
|------|---------|------------------|-----------------|-------|
| 1 | `just lint` | ruff (Python) + tsc (TypeScript) — no syntax errors | Exit 0 | L1 |
| 2 | `python -c "import sys; sys.path.insert(0,'server'); sys.path.insert(0,'server/app'); from agentic_service import execute_tool; print('OK')"` | `execute_tool` import still resolves after wiring change | Prints "OK" | L1 |
| 3 | `python -c "import sys; sys.path.insert(0,'server'); sys.path.insert(0,'server/app'); from app.sdk_agentic_service import sdk_query; print('OK')"` | `sdk_query` import resolves from new import location | Prints "OK" | L1 |
| 4 | `grep -n "stream_chat" server/app/main.py server/app/streaming_routes.py` | No remaining `stream_chat` references in active web imports | Empty output | L1 |
| 5 | `just test -k "not test_28"` | All backend unit tests pass; `execute_tool` path (tests 16–20) not broken | All green | L2 |
| 6 | `just eval-aws` | Tests 16–20: S3, DynamoDB, CloudWatch, document generation, E2E | All 5 PASS | L2 |
| 7 | `just eval-quick 1,2,3` | SDK session create, resume, trace observation — confirms SDK primitives intact | All 3 PASS | L2 |
| 8 | `just eval-quick 28` | Skill→subagent orchestration via `sdk_query()` — primary SDK acceptance gate | PASS (3+/5 indicators) | L2 |
| 9 | `just dev-up` | Full Docker stack starts cleanly with new imports in `main.py` and `streaming_routes.py` | Backend health endpoint returns 200 | L5 |
| 10 | `just smoke mid` | SSE streaming path through `stream_generator()` — 5 specs, headless | All tests pass | L3 |

**Minimum bar for flip**: Steps 1–8 (offline validation). Steps 9–10 are the full-stack
confirmation gate (requires Docker).

**Blocking on step 8**: If test 28 fails, diagnose before flipping. Common failure modes:
- `sdk_query()` yields 0 messages → check Bedrock credentials and `EAGLE_SDK_MODEL` env var
- `agents_built` indicator false → `plugin.json` parse failure; check `_PLUGIN_JSON_PATH` resolution in ECS
- `subagent_delegation` false → supervisor model chose to answer directly; check `allowed_tools=["Task"]` guard

---

## 6. Recommended `just` Command Sequence

```bash
# ── Step 1: Pre-implementation lint baseline ────────────────
just lint
# Expected: 0 errors

# ── Step 2: Implement the wiring changes ──────────────────
# (Follow plan-backend-sdk-wiring-v1.md, in order:
#  1. agentic_service.py deprecation comment
#  2. streaming_routes.py import + stream_generator rewrite
#  3. main.py import + 3 call site adapters)

# ── Step 3: Post-change lint + import checks ───────────────
just lint
python -c "import sys; sys.path.insert(0,'server'); sys.path.insert(0,'server/app'); from agentic_service import execute_tool; print('execute_tool OK')"
python -c "import sys; sys.path.insert(0,'server'); sys.path.insert(0,'server/app'); from app.sdk_agentic_service import sdk_query; print('sdk_query OK')"
grep -n "stream_chat" server/app/main.py server/app/streaming_routes.py
# Expected last command: empty (no matches)

# ── Step 4: Unit tests + AWS tool eval ────────────────────
just test -k "not test_28"
just eval-aws
# Expected: all pass

# ── Step 5: SDK eval targeted run ─────────────────────────
just eval-quick 1,2,3
just eval-quick 28
# Expected: all PASS; test 28 must show subagent_delegation=True

# ── Step 6: Full-stack confirmation ───────────────────────
just dev-up
just smoke mid
# Expected: all Playwright tests pass with new stream_generator()

# ── Step 7 (optional): Full eval suite ────────────────────
just eval
# Expected: 28/28 pass (or consistent with pre-migration baseline)
```

---

## 7. Post-Flip Monitoring (First 24h)

After deploying to dev/staging, watch the following CloudWatch metrics and log patterns.
All are in the existing telemetry infrastructure — no new instrumentation is needed.

### 7.1 CloudWatch Log Insights Queries

**Log group**: `/eagle/test-runs`

```
# Check eval pass rate post-flip
filter type = "run_summary"
| sort @timestamp desc
| limit 5
| display run_timestamp, total_tests, passed, pass_rate
```

```
# Find any test 28 failures post-flip
filter type = "test_result" and test_id = 28 and status = "fail"
| sort @timestamp desc
| display run_timestamp, test_name, status, log_lines
```

**Log group**: `/eagle/app` (FastAPI application logs)

```
# Watch for SDK streaming errors in stream_generator()
filter level = "ERROR" and message like /Streaming chat error/
| sort @timestamp desc
| limit 20
```

```
# Watch for missing ResultMessage (stream hangs)
filter message like /sdk_query exhausts without ResultMessage/
| sort @timestamp desc
| limit 10
```

```
# Subagent delegation — confirm Task tool is being invoked (hooks telemetry)
filter message like /subagent_start/ or message like /Task/
| sort @timestamp desc
| limit 20
```

### 7.2 Custom Metrics to Watch (EAGLE/Eval Namespace)

| Metric | Alarm Threshold | Interpretation |
|--------|----------------|----------------|
| `PassRate` | < 90% | Eval suite regression — investigate |
| `TestStatus[28_sdk_skill_subagent_orchestration]` | 0.0 (fail) | SDK path broken — rollback |
| `TestStatus[16_s3_document_ops]` through `[20_cloudwatch_e2e]` | Any 0.0 | `execute_tool` regression — investigate |
| `TotalCost` | Spike > 2x baseline | SDK subagent recursion or runaway tool calls |

### 7.3 Application-Level Metrics to Watch

| Signal | Where to Check | Expected Behavior |
|--------|---------------|-------------------|
| `/api/stream` 200 rate | ALB access logs or `EAGLE/App` namespace | Stays at pre-migration baseline |
| `/api/stream` P95 latency | ALB `TargetResponseTime` | May increase slightly (subagent delegation adds turns) — monitor for spikes > 2x |
| `/api/chat` 200 rate | Same | Stays at baseline |
| SSE `COMPLETE` events in browser | Network tab in browser DevTools | Every request must terminate with `COMPLETE` event |
| DynamoDB `USAGE#` / `COST#` writes | `eagle` table in console | Should see new entries per request confirming hooks are firing |
| CloudWatch `SubagentStart` hook events | SDK hook telemetry in app logs | Should appear once per subagent invocation |

### 7.4 Rollback Trigger Conditions

Initiate rollback if any of the following are observed in the first 24h:

- `/api/stream` endpoint returns HTTP 500 on > 5% of requests
- SSE `COMPLETE` event is missing (stream hangs) on > 2 requests
- Test 28 fails in a post-deploy eval run (`just eval-quick 28`)
- `sdk_query()` raises unhandled `ExceptionGroup` outside Windows (should not occur on ECS Linux)
- DynamoDB `COST#` writes absent for > 10 consecutive requests (hooks not firing)

**Rollback procedure**: Revert the 3-file wiring change in `streaming_routes.py`, `main.py`,
and remove the deprecation comment in `agentic_service.py`. No data migration is required.

---

## 8. New Tests Recommended

### Pre-Flip (recommended before flip, not blocking)

None are strictly required before the flip given the smoke test coverage. The pre-flip
checklist in Section 5 is sufficient.

### Post-Flip (add within one sprint after successful flip)

| Proposed Test | ID | Tier | What It Validates |
|--------------|-----|------|-------------------|
| `sdk_query()` session resume passthrough | 29 | SDK Patterns | Calls `sdk_query()` twice with the `session_id` from the first call; verifies the second call resumes the session (not just raw `query()`) |
| `stream_generator()` SSE event sequence | 30 | Integration | Spins up FastAPI test client, POSTs to `/api/stream`, collects raw SSE events, validates `TEXT` → `COMPLETE` sequence — no `TOOL_RESULT` events expected on SDK path |

**Test 29 registration checklist** (follow expertise.md Part 7):
- Add `async def test_29_sdk_query_session_resume()` before the `# ── Main` section
- Register in `TEST_REGISTRY`, `test_names`, `result_key`, summary printout
- Update `selected_tests = list(range(1, 30))`
- Register in all 3 frontend files

**Test 30 note**: This is an integration test requiring a live FastAPI instance. Consider
adding to `server/tests/test_integration.py` (new file) rather than `test_eagle_sdk_eval.py`
to keep eval suite concerns separate from web-layer integration tests.

---

## 9. Pre-Flip Checklist (Copy-Paste for PR Description)

```
Pre-flip validation:
- [ ] just lint → 0 errors (Python ruff + TypeScript tsc)
- [ ] execute_tool import check → prints "OK"
- [ ] sdk_query import check → prints "OK"
- [ ] grep stream_chat in main.py + streaming_routes.py → empty
- [ ] just test -k "not test_28" → all green
- [ ] just eval-aws → tests 16, 17, 18, 19, 20 all PASS
- [ ] just eval-quick 1,2,3 → all PASS
- [ ] just eval-quick 28 → PASS (subagent_delegation=True, 3+/5 indicators)
- [ ] just dev-up → stack starts clean, health check returns 200
- [ ] just smoke mid → all Playwright specs pass

Post-flip (first 24h):
- [ ] /eagle/test-runs CloudWatch pass_rate >= 90%
- [ ] test_28 status = pass in CloudWatch
- [ ] /api/stream P95 latency within 2x pre-migration baseline
- [ ] No SSE stream hangs (COMPLETE event present in all responses)
- [ ] DynamoDB COST# writes present (hooks firing)
```

---

## 10. Open Questions / Decisions Deferred

| Question | Decision |
|----------|----------|
| Should `just eval` (all 28 tests) be run pre-flip? | Optional. The targeted sequence (steps 5–8) covers the critical path faster. Run `just eval` on staging post-flip. |
| Should test 29 (sdk_query session resume) block the flip? | No. The session passthrough is thin and risk is low. Add post-flip. |
| Should `TOOL_RESULT` events be emitted by wrapping subagent tool calls in the SSE adapter? | Design decision deferred. Current plan (no TOOL_RESULT on SDK path) is documented in `plan-backend-sdk-wiring-v1.md` and smoke tests validate the frontend renders correctly without them. |
| Should `eval-quick 28` use `--model sonnet` instead of `--model haiku` for production confidence? | Recommendation: run with `haiku` for the pre-flip gate (cost control). Run once with `sonnet` on staging to confirm production model behavior. |

---

*Scribe | 2026-02-22T22:40:42 | plan v1 | Format: markdown | Source: experts:eval:plan*
