# EAGLE: Strands-Only Migration Plan (Remove Claude SDK)

**Branch:** `dev/strands-conversion-alvee`  
**Created:** 2026-03-02  
**Status:** Ready for Implementation  
**Goal:** Migrate backend orchestration from Claude Agent SDK to Strands Agents SDK and remove all `claude-agent-sdk` runtime usage.

---

## 1. Scope and Non-Goals

### In Scope

1. Replace `sdk_agentic_service.py` orchestration with Strands-only orchestration.
2. Keep `eagle-plugin/` prompts and `server/eagle_skill_constants.py` as source of truth.
3. Update streaming flow to consume Strands events.
4. Remove `claude-agent-sdk` dependency and references.
5. Update tests and docs to Strands-only architecture.

### Out of Scope

1. Redesigning domain prompts in `eagle-plugin/`.
2. UI redesign outside of stream protocol requirements.
3. New infrastructure stacks.

---

## 2. Migration Strategy

1. Build Strands service and tools first, in parallel with current SDK code.
2. Switch streaming routes to Strands once service parity is validated.
3. Update tests and docs.
4. Remove Claude SDK files and dependency only after parity checks pass.

This keeps risk low while still ending in an exclusive Strands runtime.

---

## 3. Target Architecture (Strands-Only)

1. `eagle-plugin/*` remains the source for supervisor and specialist prompts.
2. `eagle_skill_constants.py` continues to auto-discover AGENTS/SKILLS.
3. New `strands_tools.py` creates specialist `@tool` functions from AGENTS/SKILLS (excluding supervisor).
4. New `strands_agentic_service.py` creates supervisor `Agent` with tier-filtered toolset.
5. `streaming_routes.py` uses `strands_query()` exclusively.
6. SSE output stays in EAGLE format via `MultiAgentStreamWriter`.

---

## 4. File Change Plan

### Create

1. `server/app/strands_models.py`
2. `server/app/strands_tools.py`
3. `server/app/strands_agentic_service.py`
4. `server/tests/test_strands_service.py`

### Modify

1. `server/app/streaming_routes.py`
2. `server/requirements.txt`
3. `server/app/main.py` (only if imports/wiring need update)
4. `README.md` and/or `CLAUDE.md` references to active orchestration backend

### Remove or Archive (final phase)

1. `server/app/sdk_agentic_service.py` (delete or archive as `_deprecated_...`)
2. Stale tests that assert Claude SDK message classes

---

## 5. Step-by-Step Implementation

## Phase 0: Preflight (No Behavior Change)

1. Create migration branch and checkpoint current passing state.
2. Run baseline checks:
   - `just lint`
   - `just test`
3. Capture one reference stream trace from current `/api/chat/stream` for comparison.

Exit criteria:
- Baseline tests pass.
- Reference stream behavior captured.

## Phase 1: Dependencies

1. Update `server/requirements.txt`:
   - Add `strands-agents` and `strands-agents-tools`.
   - Keep `claude-agent-sdk` temporarily during transition.
2. Install and verify imports in backend environment.

Exit criteria:
- Strands imports resolve in backend.
- Existing app still runs unchanged.

## Phase 2: Bedrock Model Layer

1. Implement `server/app/strands_models.py`:
   - Model alias map (`haiku`, `sonnet`).
   - `get_bedrock_model()` factory.
   - Cached model instance helper.
2. Use env defaults compatible with current system (`EAGLE_SDK_MODEL`, `AWS_REGION`).

Exit criteria:
- Can instantiate Strands `BedrockModel` successfully.

## Phase 3: Tool Factory from Plugin Metadata

1. Implement `server/app/strands_tools.py` with one strategy only:
   - Dynamic tool factory from `AGENTS` + `SKILLS`.
   - Exclude `supervisor` from tool registry.
2. Preserve all current specialists (agents + skills), including policy tools and `tech-review`.
3. Implement tier gating helper (basic/advanced/premium) using deterministic lists.

Exit criteria:
- Tool registry contains expected set and names.
- Tier filters return expected counts.

## Phase 4: Strands Orchestration Service

1. Implement `server/app/strands_agentic_service.py`:
   - `build_supervisor_prompt(tenant_id, user_id, tier, available_tools)`
   - `strands_query(...)` async generator
   - Optional `strands_query_single_skill(...)`
2. Add parity controls replacing SDK-only options:
   - Iteration/loop cap (replacement for `max_turns`).
   - Tier budget enforcement hooks (replacement for `max_budget_usd`) or explicit TODO gate if not yet implemented.
3. Normalize Strands stream events to internal event contract:
   - `text`, `tool_use`, `tool_result` (optional), `complete`, `error`.

Exit criteria:
- Local direct invocation of `strands_query()` yields normalized events.

## Phase 5: Streaming Route Cutover

1. Update `server/app/streaming_routes.py`:
   - Replace `sdk_query` import with `strands_query`.
   - Remove SDK message-class parsing logic.
   - Consume normalized events from `strands_query`.
2. Keep SSE output schema stable unless frontend is intentionally updated.

Exit criteria:
- `/api/chat/stream` emits valid SSE and completes cleanly.

## Phase 6: Tests and Validation

1. Add `server/tests/test_strands_service.py`:
   - Tool loading coverage.
   - Tier gating.
   - Prompt builder contains tenant context.
   - Event normalization contract.
2. Update/remove SDK-specific tests as needed.
3. Run validation ladder:
   - `just lint`
   - `just test`
   - `just dev-up`
   - Streaming smoke via curl or Playwright chat spec

Exit criteria:
- Tests pass without importing `claude_agent_sdk`.
- Stream path works end-to-end.

## Phase 7: Remove Claude SDK Completely

1. Remove from `server/requirements.txt`:
   - `claude-agent-sdk`
2. Delete or archive `server/app/sdk_agentic_service.py`.
3. Remove dead imports, comments, and docs referencing SDK as active path.
4. Re-run full validation.

Exit criteria:
- `rg 'claude_agent_sdk|claude-agent-sdk|sdk_query|sdk_agentic_service' server README.md CLAUDE.md` returns no active runtime references.
- App functions with Strands-only backend.

## Phase 8: Documentation and Operational Update

1. Update README architecture section to Strands-only.
2. Update health endpoint metadata to indicate Strands backend.
3. Add troubleshooting notes for Strands Bedrock config and streaming event mapping.

Exit criteria:
- Repo docs match real runtime behavior.

---

## 6. Acceptance Criteria (Definition of Done)

1. Backend chat streaming uses Strands only.
2. All plugin-defined agents/skills are available via Strands tool registry (except supervisor, which orchestrates).
3. Tier gating still works.
4. No Claude SDK runtime dependency remains.
5. Lint/tests pass and streaming smoke test passes.
6. Docs reflect Strands as sole orchestration backend.

---

## 7. Risk Register and Mitigations

1. Risk: Strands event payload differs from assumptions.
   - Mitigation: Add event logging in dev and lock normalization logic to observed payload keys.
2. Risk: Behavior regression in tool delegation quality.
   - Mitigation: Compare outputs on representative prompts before and after cutover.
3. Risk: Budget/turn controls regress.
   - Mitigation: Implement explicit guards in service layer and test tier limits.
4. Risk: Hidden SDK coupling in tests/docs.
   - Mitigation: Final grep gate and CI fail on remaining SDK imports.

---

## 8. Rollback Plan

1. Keep commit boundary before Phase 7 (SDK removal).
2. If Strands cutover fails before final removal:
   - Revert `streaming_routes.py` to `sdk_query` path.
3. If failure after removal:
   - Reinstall dependency and restore archived `sdk_agentic_service.py` from git.

---

## 9. Execution Checklist

- [ ] Phase 0 baseline complete
- [ ] Phase 1 dependencies complete
- [ ] Phase 2 model layer complete
- [ ] Phase 3 tool factory complete
- [ ] Phase 4 orchestration complete
- [ ] Phase 5 route cutover complete
- [ ] Phase 6 tests green
- [ ] Phase 7 Claude SDK removed
- [ ] Phase 8 docs updated
- [ ] Final grep gate clean

---

## 10. Suggested Command Sequence

```bash
# Baseline
just lint
just test

# During migration
cd server
python -m ruff check app/
python -m pytest tests/ -v

# End-to-end smoke
just dev-up
curl -X POST http://localhost:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message":"I need to buy lab equipment for $85,000"}' \
  --no-buffer
just dev-down

# Final gate: ensure Claude SDK is removed
rg 'claude_agent_sdk|claude-agent-sdk|sdk_query|sdk_agentic_service' server README.md CLAUDE.md
```
