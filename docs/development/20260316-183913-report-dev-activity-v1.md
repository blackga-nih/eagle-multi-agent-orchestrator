# EAGLE Development Activity Report
**Period:** 2026-03-12 through 2026-03-16
**Branch:** main
**Report Type:** Development Activity Summary

---

## Executive Summary

The past five days delivered a major maturation of EAGLE's observability, orchestration, and document generation capabilities. The supervisor agent was substantially hardened — prompt reduced by 78%, context enrichment added for all subagents, and Strands hook events wired to enforce state discipline and emit real-time telemetry. The Langfuse integration is now end-to-end: traces are linked across supervisor and subagents by session ID, surfaced inline in the chat UI via a trace viewer, and validated by an automated eval suite. A full LLM-driven document agent replaced the legacy fill-in-the-blank generators, and the route/store layer was extracted into clean, independently testable packages.

---

## 1. Observability and Tracing (Langfuse + CloudWatch)

### What changed

The Langfuse OTEL integration moved from a module-level side effect in `main.py` to a deliberate initialization inside `strands_agentic_service.py`, after Strands' own `TracerProvider` is registered. This ordering is mandatory — initializing before Strands loses all agent spans.

Session IDs are now propagated through `build_skill_tools()` into every subagent `Agent()` call. Langfuse groups all spans with the same `session.id` into a single Session view, making the full supervisor → specialist chain traceable without manual span stitching.

The `traces/story` API was extended to return `tool_details`, `output_preview`, `observation_id`, `response_full`, and `langfuse_url` per observation. A Next.js proxy route at `/api/traces/story` was added so the frontend can fetch these without CORS issues.

A `scripts/extract_trace_story.py` script was written to walk the `AGEN → SPAN → GENE/TOOL` Langfuse observation hierarchy and validate the expected structure programmatically. This became the basis for eval test 36.

### CloudWatch telemetry

`BeforeToolCallEvent` now emits `tool.started` to CloudWatch for every tool invocation (not just document gating). `AfterToolCallEvent` computes a state delta (current `AgentState` vs. last snapshot) and emits `tool.completed` with `state_changed` and `state_delta` fields. `AfterModelCallEvent` detects when the supervisor ends a turn without calling `update_state` and emits an `agent.warning` — giving CloudWatch Insights a signal for orchestration discipline violations.

### Architectural decision

Langfuse OTEL must be initialized after Strands `TracerProvider`. The ordering constraint is now enforced structurally (init inside the service module, not at import time) rather than by convention.

---

## 2. Supervisor Prompt and Orchestration Hardening

### What changed

The supervisor system prompt was reduced from 5,897 tokens to 1,296 tokens — a 78% reduction. Domain knowledge was moved to the tools that own it: FAR thresholds to `query_contract_matrix`, workflow templates to the `oa-intake` skill, and compliance reminders to `query_compliance_matrix`. The supervisor now carries only: role identity, routing logic, response style, and the `update_state` protocol.

A Turn 1 gate was added to the orchestration protocol: on the first user turn, only `oa_intake` is eligible to run. Specialists (`market_intelligence`, `legal_counsel`, etc.) are deferred to Turn 2 and beyond, once intake context is established. This prevents specialists from running blind.

Subagent context enrichment was added: every subagent query is prefixed with a ~100-token acquisition context header (tenant, tier, phase, package ID, required documents, prior analyses completed). Specialists no longer need to infer context from conversation history alone.

A `SummarizingConversationManager(summary_ratio=0.3, preserve_recent=10)` was added to both `sdk_query` and `sdk_query_streaming`. On context window overflow, Strands auto-summarizes the oldest 30% of messages while preserving the 10 most recent turns verbatim.

### Architectural decision

The supervisor is now a router and synthesizer only. It does not carry domain knowledge. The consultative brief format (key finding → why → 2–3 scenarios → next step) replaced inline dump of full specialist reports.

---

## 3. Document Generation — LLM-Driven Agent

### What changed

The fill-in-the-blank f-string document generators in `agentic_service.py` were replaced with an LLM-driven document agent in `server/app/document_agent.py`. The agent:

- Loads the appropriate NCI template as a structural guideline
- Builds a prompt incorporating the full conversation context
- Calls the model to write full prose (not slot-fill)
- Validates required fields against `eagle-plugin/data/templates/required_fields.yaml`
- Tracks omissions in Appendix A and AI decision rationale in Appendix B

`reasoning_store.py` was extended with `SectionEntry` and `JustificationEntry` dataclasses, and `to_omissions_appendix()` / `to_justification_appendix()` formatters.

A hook-driven document gating layer was added via `BeforeToolCallEvent`. Before any `create_document` or `generate_document` call executes, `hooks/document_gate.py` validates the request against the FAR-grounded contract requirements matrix. The result (`pass` / `warn` / `block`) is recorded in agent state and emitted to CloudWatch. Blocked calls fire `event.cancel_tool` — the document is never generated.

A 57-test suite covers template loading, required field validation, prompt construction, appendix parsing, full generation flow (all 10 document types), and `ReasoningStore` extensions.

### Architectural decision

Document gating is a pre-execution hook, not a post-hoc check. The `BeforeToolCallEvent` gives the system the ability to cancel execution before the model call, not after the document is already generated.

---

## 4. Route and Store Refactoring

### What changed

`app/main.py` was unbundled into dedicated packages:

- `server/app/routes/` — 13 FastAPI router modules: `chat`, `sessions`, `documents`, `admin`, `packages`, `workspaces`, `tenants`, `user`, `templates`, `skills`, `misc`, and a `_deps` shared dependency module
- `server/app/tool_dispatch.py` — centralized tool dispatch (2,819 lines), extracted from `strands_agentic_service.py`
- `server/app/stores/` — stores package with a clean `__init__.py`; `workspace_config_store.py` extracted for workspace config CRUD

The `AgentCore` service was refactored from scattered `agentcore_*.py` files into `server/app/agentcore/` with one module per service: `browser`, `code`, `gateway`, `identity`, `memory`, `observability`, `policy`, `runtime`. All modules fail open — if the `bedrock-agentcore` SDK is unavailable, they fall back to existing implementations. 52 unit tests cover the fallback mode.

Service tools were refactored from inline lambdas to native `@tool` factories with typed parameters. This enables Strands to generate correct tool schemas from the function signatures rather than relying on hand-authored JSON.

### Impact

Import paths across tests and routes were stabilized. The prior refactor had left stale imports pointing at deleted or moved modules (`app.main.*` → `app.routes.chat.*`, `app.agentic_service` → `app.tool_dispatch`, etc.). A pass of test repairs aligned all test imports with the new layout.

---

## 5. Eagle State and Session Persistence

### What changed

`server/app/eagle_state.py` became the single source of truth for supervisor agent state: `normalize()`, `apply_event()`, `to_trace_attrs()`, `to_cw_payload()`, and `stamp()`. The `update_state` tool now delegates to `apply_event()` rather than maintaining scattered `if/elif` blocks.

State is persisted to DynamoDB after every supervisor turn via `AfterInvocationEvent` in `EagleSSEHookProvider`, using a `STATE#` sort key pattern in the sessions table. The agent state snapshot is included in every `complete` SSE event so the frontend can synchronize without a separate fetch.

`package_context_service.py` was fixed: `set_active_package()` and `clear_active_package()` now copy the session metadata dict before mutating it, which was causing test isolation failures across sequential test runs.

---

## 6. Frontend — Trace Viewer, Source Chips, Package Tab

### What changed

**Trace viewer:** A `TraceStory` component was added. Each assistant message now shows a "Trace" button that opens a slide-over `TraceModal` displaying the full Langfuse observation hierarchy for that response. The Traces sidebar tab was removed — traces are now inline in chat.

**Source chips:** `_extract_citations()` surfaces knowledge base source references from subagent reports. Color-coded `SourceChips` appear below assistant responses and inside expanded tool-use cards.

**Package tab:** The activity panel gained a Package tab wired to live SSE `update_state` metadata events. It shows:

- Phase badge (intake / analysis / drafting / review / complete, color-coded)
- Progress bar (completed vs. required documents)
- Document checklist rows (green check or pending circle per required doc)
- Compliance alert cards (severity chip + FAR citation items)
- Alert badge count on the tab when compliance alerts are active

The Package tab is the default opening view of the activity panel.

`<thinking>` blocks are now stripped from streamed model output before display in the message list.

---

## 7. Extended Thinking

### What changed

Extended thinking support was added for both Haiku 4.5 and Sonnet 4.6. It is off by default and toggled via environment variable:

```
EAGLE_EXTENDED_THINKING=1
EAGLE_THINKING_BUDGET_TOKENS=8000
```

When enabled, Bedrock returns reasoning blocks in the conversation. Strands carries them through to OTEL spans, and Langfuse surfaces the full reasoning chain alongside tool inputs/outputs. Temperature is forced to 1 (Bedrock requirement for extended thinking).

The model factory was made lazy (`_get_model()`) so `EAGLE_BEDROCK_MODEL_ID` and `EAGLE_EXTENDED_THINKING` are read on first use rather than frozen at import time.

### Finding from observability

Haiku 4.5 ignores extended thinking on Bedrock (no reasoning blocks surface in Langfuse spans). Sonnet 4.x is required for reasoning block support.

---

## 8. Eval Suite Expansion

| Test | Coverage |
|------|----------|
| Test 1 | Routes through full production `sdk_query()` path, including workspace resolution and document gating hooks |
| Test 9 | `oa-intake` skill filter via `_eval_query()` helper |
| Test 15 | 3-skill multi-agent chain; token count 42k → 78k with extended thinking |
| Test 36 | Langfuse trace story validation — 4 supervisor turns, 3 subagents in order, synthesis turn present |
| Test 37 | `tool.completed` events in CloudWatch per-session stream, `state_changed` present, no `agent.warning` |

A shared `_eval_query()` helper was introduced to drive tests through the production stack (skill tools, document gating, state persistence, trace attributes) rather than instantiating bare `Agent()` objects.

---

## 9. Codebase Cleanup

Deprecated infrastructure was removed in a single checkpoint commit:

| Removed | Reason |
|---------|--------|
| `cdk/` (Python CDK), `cloud_formation/`, `terraform/` | Superseded by `infrastructure/cdk-eagle/` (TypeScript CDK) |
| `agentic_service.py`, `bedrock_service.py`, `gateway_client.py` | Superseded by `strands_agentic_service.py` + `tool_dispatch.py` |
| `agentcore_browser/`, `agentcore_code/`, `agentcore_memory/` | Consolidated into `server/app/agentcore/` package |
| `stores/approval_store.py`, `audit_store.py`, `config_store.py`, `document_store.py` | Removed legacy stores |
| Root-level `.docx` files, `.csv` files, `jira-tickets.md`, `image.png` | Artifact hygiene |
| `_archived_test_eagle_sdk_eval.py` | Stale test archive |

Expert expertise files for `frontend`, `backend`, `sse`, and `git` domains were updated via the self-improve pipeline to capture the new patterns introduced this sprint.

---

## What's Working End-to-End

| Capability | Status |
|------------|--------|
| Supervisor → specialist orchestration (Strands SDK + BedrockModel) | Fully operational |
| SSE streaming with 10 event types (`text`, `tool_use`, `tool_use_complete`, `update_state`, `document_ready`, `phase_change`, `checklist_update`, `compliance_alert`, `bedrock_trace`, `complete`) | Fully operational |
| Langfuse trace hierarchy: session-linked supervisor + subagent spans | Fully operational |
| Inline trace viewer in chat UI | Fully operational |
| Source chips / citation extraction from subagent reports | Fully operational |
| Package tab with live phase, checklist, and compliance alert state | Fully operational |
| LLM-driven document generation with required-field validation | Fully operational |
| FAR-grounded document gating via `BeforeToolCallEvent` | Fully operational |
| Agent state persistence to DynamoDB (STATE# pattern) | Fully operational |
| CloudWatch telemetry: `tool.started`, `tool.completed` (state delta), `agent.warning` | Fully operational |
| Extended thinking toggle (Sonnet 4.x; haiku ignored) | Available, off by default |

---

## What's Next

The following items are visible as open work based on commit bodies and spec files in `.claude/specs/`:

| Item | Signal |
|------|--------|
| `AgentCore` runtime policy integration | `agentcore/policy.py` fails open with `TIER_TOOLS` fallback; live AgentCore policy gating not yet wired |
| `AgentCore` memory (batch read/write) | Module present and tested in fallback mode; live AgentCore Memory not yet activated |
| NIH Login integration | `docs/development/20260304-000000-plan-nih-login-integration-v1.md` spec exists, no implementation commits |
| Branch protection on `main` | Expert git domain flagged `main` as unprotected in self-improve update |
| `agent.warning` CloudWatch alarm | Test 37 validates the event fires; no CloudWatch alarm or SNS notification wired yet |
| EagleBackupStack | Referenced in regenerated architecture diagrams; no CDK commit for this stack in the period |

---

## Key Architectural Decisions (Sprint Record)

| Decision | Rationale |
|----------|-----------|
| Langfuse OTEL init after Strands TracerProvider | Prevents Strands agent spans from being lost to a race condition at module import time |
| Supervisor carries routing + style only; no domain knowledge | Domain knowledge belongs in tools — reduces prompt token cost and keeps tool schemas as the authoritative source of truth |
| Document gating as a `BeforeToolCallEvent` hook | Hook can cancel execution; a post-hoc check cannot undo a document that was already generated and saved to S3 |
| `_get_model()` lazy factory for BedrockModel | Allows env var overrides (model ID, extended thinking) to take effect at runtime rather than being frozen at import time |
| `SummarizingConversationManager` at 30% / 10-turn preserve | Prevents context window overflow without losing recent conversational state; the 10-turn window keeps the immediate negotiation intact |
| `@tool` native factories instead of hand-authored JSON schemas | Strands generates correct schemas from typed Python signatures; reduces schema drift bugs |

---

*Scribe | 2026-03-16T18:39:13Z | Format: markdown | Type: report*
