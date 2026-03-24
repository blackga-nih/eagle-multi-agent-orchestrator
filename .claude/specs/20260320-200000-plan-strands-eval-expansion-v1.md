---
title: Strands Eval Suite Expansion — MVP1 Full Coverage
type: plan
date: 2026-03-20
status: draft
---

# Strands Eval Suite Expansion Plan

## Executive Summary

The current eval suite has **42 tests** in `test_strands_eval.py` but only **6 Tier 2 integration tests** actually hit live Bedrock (3 supervisor routing + 1 UC-02 POC + 2 adapter tests). The remaining 36 are deterministic unit tests or keyword-matching single-turn conversations with **no observability validation**.

This plan expands to a comprehensive **observability-driven eval** that validates:
- Tool call chains (not just keyword matches)
- Langfuse traces (token usage, cost, skill attribution)
- CloudWatch events (end-to-end from tool dispatch to CW log entry)
- Knowledge base integration (FAR search, compliance matrix, KB fetch)
- Real agent.md prompts with personality fidelity
- All MVP1 use cases from the Excel UC list

---

## Current State

### What We Have (Tier 2 — Live Bedrock)

| Test | File | What It Does | Gap |
|------|------|-------------|-----|
| `test_supervisor_routes_to_intake` | multi_agent | Routes to oa-intake | No tool chain validation |
| `test_supervisor_routes_to_legal` | multi_agent | Routes to legal-counsel | No Langfuse check |
| `test_supervisor_routes_to_market` | multi_agent | Routes to market-intelligence | No CW event check |
| `test_strands_uc02_micro_purchase` | poc | UC-02 end-to-end | Keyword-only, no doc gen |
| `test_sdk_query_adapter_messages` | integration | Message adapter shape | No tool dispatch |
| `test_sdk_query_single_skill_adapter` | integration | Single skill routing | No tool dispatch |

### What's Missing

1. **0 tests validate Langfuse traces** — no token/cost verification
2. **0 tests validate tool call chains** — can't prove tools were invoked
3. **0 tests generate documents** in Tier 2 — SOW/IGCE/AP never created
4. **0 tests exercise knowledge base** — no `knowledge_search`/`knowledge_fetch`/`search_far` calls
5. **0 tests validate CloudWatch events** from agent execution
6. **8+ MVP1 UCs untested** with live agents (only keyword matching exists)

---

## Agent Personality & Required Tool Calls

Each agent has **personality traits** and **must-call tools** from their `agent.md` definitions. Tests MUST validate these.

### Supervisor (Main Orchestrator)
- **Personality**: Professional colleague, action-biased ("DO THE WORK, don't explain"), risk-aware
- **Must-call tools**: Delegates to specialists, uses `search_far`, `create_document`, `compliance_matrix`
- **KB requirement**: Identify FAR Part from dollar threshold BEFORE asking questions
- **Test assertion**: Must route to correct specialist based on intent, must NOT lecture

### OA Intake (`oa-intake`)
- **Personality**: 5-phase workflow (intake → clarify → determine → document → handoff)
- **Must-call tools**: `knowledge_search`, `search_far` for regulation lookup
- **KB requirement**: Load acquisition pathway based on dollar value
- **Test assertion**: Must ask ≤3 focused questions, must identify FAR Part

### Legal Counsel (`legal-counsel`)
- **Personality**: Analytical, cautious, precedent-focused, risk-averse but practical
- **Must-call tools**: `search_far`, `knowledge_fetch` for case law, `knowledge_search`
- **KB requirement**: Cite specific FAR clauses, GAO decisions (B-4xxxxx format)
- **Test assertion**: Must cite FAR authority, must assess protest risk with severity

### Market Intelligence (`market-intelligence`)
- **Personality**: Data-driven, vendor-aware, small business advocate
- **Must-call tools**: `web_search`, `web_fetch`, `knowledge_search`, `create_document` (MRR)
- **KB requirement**: GSA schedule lookup, SAM.gov small business search
- **Test assertion**: Must provide real vendor names, pricing ranges, vehicle recommendations

### Tech Translator (`tech-translator`)
- **Personality**: Bilingual (technical + contracting), structured, measurable
- **Must-call tools**: `knowledge_search` for SOW templates, `search_far` for clauses
- **KB requirement**: SOW section structure, evaluation criteria framework
- **Test assertion**: Must translate specs to contract language with measurable deliverables

### Public Interest (`public-interest`)
- **Personality**: Ethics-focused, transparency advocate, fairness guardian
- **Must-call tools**: `knowledge_search`, `search_far` for transparency requirements
- **KB requirement**: SAM.gov posting requirements, FOIA considerations
- **Test assertion**: Must flag fairness issues, recommend mitigation

### Document Generator (`document-generator`)
- **Personality**: Template-driven, section-complete, NCI-branded
- **Must-call tools**: `create_document`, `get_latest_document`, `knowledge_search`
- **KB requirement**: Section requirements per doc type (SOW=12 sections, IGCE=9, AP=3+approvals)
- **Test assertion**: Must generate complete documents with all required sections

---

## Strands SDK Skills/Plugin Best Practices

The EAGLE architecture uses a **4-layer skill resolution chain**:

```
1. Workspace override (wspc_store.resolve_skill)
2. DynamoDB canonical (plugin_store PLUGIN# items)
3. Bundled plugin files (PLUGIN_CONTENTS from eagle_skill_constants.py)
4. Tenant custom skills (skill_store SKILL# items)
```

### Key Pattern: @tool Subagent Factory

```python
@tool(name=skill_name)
def subagent_tool(query: str) -> str:
    agent = Agent(
        model=_model,
        system_prompt=tenant_context + skill_body,  # FULL agent.md content
        tools=kb_tools + extra_tools,                # KB + web tools
        trace_attributes=_build_trace_attrs(...),     # Langfuse tags
    )
    return str(agent(query))
```

### Test Implications

1. **Use `build_skill_tools()`** — don't hardcode prompts, use the real resolution chain
2. **Validate `result.metrics.tool_metrics`** — Strands records which tools were called
3. **Check `trace_attributes`** — verify Langfuse tags are set correctly
4. **Use `SKILL_AGENT_REGISTRY`** — validate all expected skills are registered

---

## Expanded Test Plan

### New Test Categories

#### Category 1: Tool Chain Validation (Tests 43-48)

Each test invokes a real agent and validates the tool call chain via `result.metrics.tool_metrics`.

| # | Test | Agent | Expected Tools | Validation |
|---|------|-------|---------------|------------|
| 43 | `test_intake_calls_search_far` | oa-intake | `search_far` | Tool in metrics.tool_metrics |
| 44 | `test_legal_cites_far_authority` | legal-counsel | `search_far`, `knowledge_fetch` | FAR clause in response + tool called |
| 45 | `test_market_does_web_research` | market-intelligence | `web_search`, `web_fetch` | Real URLs in response + tools called |
| 46 | `test_doc_gen_creates_sow` | document-generator | `create_document` | S3 key returned + tool called |
| 47 | `test_supervisor_delegates_not_answers` | supervisor | any skill tool | At least 1 subagent tool in metrics |
| 48 | `test_compliance_matrix_before_routing` | supervisor | `query_compliance_matrix` | Matrix queried before skill delegation |

#### Category 2: Langfuse Trace Validation (Tests 49-52)

Query Langfuse API post-test to validate trace hierarchy, token usage, and cost attribution.

| # | Test | What's Validated | Langfuse API Call |
|---|------|-----------------|-------------------|
| 49 | `test_trace_has_environment_tag` | `eagle.environment` = local/dev/prod | `GET /traces/{id}` → metadata |
| 50 | `test_trace_token_counts_match` | Tokens from metrics match Langfuse | `GET /observations?traceId={id}` → GENERATION usage |
| 51 | `test_trace_shows_subagent_hierarchy` | Supervisor → skill spans visible | `GET /observations?traceId={id}` → SPAN nesting |
| 52 | `test_trace_session_id_propagated` | Session ID in trace metadata | `GET /traces/{id}` → eagle.session_id |

#### Category 3: CloudWatch E2E Validation (Tests 53-55)

Emit test events to CloudWatch during the run, then query to confirm they arrived.

| # | Test | CW Event | Validation |
|---|------|----------|------------|
| 53 | `test_emit_test_result_event` | `test_result` event with test_id, status, tools_used | `get_log_events()` finds it |
| 54 | `test_emit_run_summary_event` | `run_summary` with total/passed/failed/cost | Event schema validates |
| 55 | `test_tool_timing_in_cw_event` | Per-tool latency in event metadata | Timing data non-zero |

#### Category 4: Knowledge Base Integration (Tests 56-60)

Validate that agents actually query the knowledge base, not hallucinate answers.

| # | Test | Agent | KB Query | Validation |
|---|------|-------|----------|------------|
| 56 | `test_far_search_returns_clauses` | legal-counsel | `search_far("sole source")` | Results contain FAR 6.302 |
| 57 | `test_kb_search_finds_policy` | oa-intake | `knowledge_search("micro purchase")` | Results found, s3_keys returned |
| 58 | `test_kb_fetch_reads_document` | legal-counsel | `knowledge_fetch(s3_key)` | Full document text returned |
| 59 | `test_web_search_for_market_data` | market-intelligence | `web_search("GSA schedule pricing")` | URLs returned, web_fetch follows |
| 60 | `test_compliance_matrix_threshold` | (deterministic) | `query_compliance_matrix(value=$500K)` | SAT triggered, correct docs listed |

#### Category 5: MVP1 UC Full Coverage (Tests 61-72)

Each test exercises a real UC with the **full agent prompt**, validates tool calls, and checks Langfuse traces.

| # | Test | UC | Agent | Prompt (from old eval) | Expected Tools | Indicators (≥3/5) |
|---|------|-----|-------|----------------------|----------------|-------------------|
| 61 | `test_uc01_new_acquisition_e2e` | UC-01 | supervisor→intake | "$2.5M CT scanner, CPFF, negotiated" | compliance_matrix, oa_intake | docs≥5, TINA triggered, FAR 15 |
| 62 | `test_uc02_micro_purchase_e2e` | UC-02 | oa-intake | "$13.8K lab supplies, purchase card" | search_far | micro_purchase, threshold, FAR 13 |
| 63 | `test_uc03_sole_source_e2e` | UC-03 | oa-intake→legal | "$280K software maintenance, only mfr" | search_far, knowledge_search | sole_source, FAR 6.302, J&A |
| 64 | `test_uc04_competitive_range_e2e` | UC-04 | legal-counsel | "$2.1M FAR 15 competitive range" | search_far, knowledge_fetch | competitive_range, discussions, FAR 15 |
| 65 | `test_uc05_package_review_e2e` | UC-05 | legal-counsel | "$487.5K package with 5 findings" | search_far | cost_mismatch, severity, FAR 52 |
| 66 | `test_uc07_contract_closeout_e2e` | UC-07 | legal-counsel | "Close out HHSN261, FAR 4.804" | search_far, knowledge_fetch | FAR 4.804, release_claims |
| 67 | `test_uc08_shutdown_notification_e2e` | UC-08 | legal-counsel | "Shutdown imminent, 200+ contracts" | knowledge_search | shutdown, FFP continue, stop_work |
| 68 | `test_uc09_score_consolidation_e2e` | UC-09 | tech-translator | "180 score sheets, 9 reviewers" | knowledge_search | score_matrix, variance |
| 69 | `test_uc10_igce_development_e2e` | UC-10 | oa-intake | "$4.5M multi-labor IGCE, 3yr PoP" | web_search, create_document | igce, labor_categories, escalation |
| 70 | `test_uc13_small_business_e2e` | UC-13 | market-intelligence | "$450K IT, Rule of Two analysis" | web_search, web_fetch | set_aside, rule_of_two, NAICS |
| 71 | `test_uc16_tech_to_contract_e2e` | UC-16 | tech-translator | "Genomic sequencing specs → SOW" | knowledge_search, create_document | sow_structure, deliverables |
| 72 | `test_uc29_full_acquisition_e2e` | UC-29 | supervisor chain | "$3.5M R&D multi-phase bioinformatics" | oa_intake, legal_counsel, create_document | full_package, FAR 15, multi_phase |

#### Category 6: Document Generation E2E (Tests 73-76)

These tests generate real documents and validate structure.

| # | Test | Doc Type | Validation |
|---|------|----------|------------|
| 73 | `test_generate_sow_with_12_sections` | SOW | All 12 required sections present, no placeholders |
| 74 | `test_generate_igce_with_pricing` | IGCE | Labor categories, real dollar amounts (not $[Amount]), 9 sections |
| 75 | `test_generate_ap_with_far_refs` | Acquisition Plan | FAR Part reference matches value threshold, 3 main sections |
| 76 | `test_generate_market_research_with_sources` | MRR | web_search called first, Sources section with URLs |

---

## Validation Gate Metrics (Per UC)

Each MVP1 UC test will report these metrics for the validation gate:

```json
{
  "test_id": 62,
  "uc": "UC-02",
  "name": "Micro-Purchase Fast Path",
  "mvp": "MVP1",
  "jira": "EAGLE-15",
  "status": "PASS",
  "indicators": {"micro_purchase": true, "threshold": true, "purchase_card": true, "streamlined": true, "far_reference": false},
  "indicators_found": 4,
  "indicators_required": 3,
  "tools_expected": ["search_far"],
  "tools_called": ["search_far", "knowledge_search"],
  "tools_validated": true,
  "langfuse_trace_id": "abc123...",
  "langfuse_url": "https://us.cloud.langfuse.com/project/.../traces/abc123",
  "tokens_in": 8455,
  "tokens_out": 1376,
  "cost_usd": 0.028,
  "latency_ms": 15200,
  "cloudwatch_event_emitted": true,
  "agent_prompt_source": "eagle-plugin/agents/supervisor/agent.md",
  "model": "us.anthropic.claude-haiku-4-5-20251001-v1:0"
}
```

---

## Context Loss & Truncation Risk Map

Analysis of `strands_agentic_service.py` reveals **6 truncation points** and **2 silent data loss risks**:

### Critical (Agent Context Loss)

| Risk | Location | Limit | Impact |
|------|----------|-------|--------|
| **Skill prompt truncation** | `_truncate_skill()` L1052, L1131 | **4000 chars** | Subagent receives incomplete instructions — may miss required behaviors, FAR citations, workflow phases |
| **Message history limit** | `session_store.get_messages()` L370 | **100 messages** | Older conversation turns silently dropped — no summarization, no pagination |
| **No context window monitoring** | `sdk_query()` L2946 | None | Supervisor prompt + history could exceed 200K tokens — fails instead of auto-summarizing |
| **No turn limit enforcement** | `max_turns=15` param | Unused | Parameter declared but never enforced — infinite tool loops possible |

### Medium (Display Truncation — No Agent Impact)

| Risk | Location | Limit | Impact |
|------|----------|-------|--------|
| Subagent result → SSE | L1386 | 3000 chars | Frontend display only — full result passes to supervisor |
| Service tool → SSE | L2407 | 3000 chars | Frontend display only |
| KB tool → SSE | L1426, L1431 | 2000 chars | Frontend display only |
| Doc tool → SSE | L1257-1260 | 2000 chars | Frontend display only |

### Handoff Context Flow

```
User Message
  │
  ├─→ sdk_query(prompt, messages=history[:-1])
  │     │
  │     ├─→ _to_strands_messages(messages)     ← 100-msg limit from DB
  │     │
  │     ├─→ _build_supervisor_prompt_body()    ← ~10KB, no size check
  │     │
  │     └─→ Agent(system_prompt, tools, messages=strands_history)
  │           │
  │           ├─→ @tool subagent_tool(query: str)
  │           │     │
  │           │     ├─→ _truncate_skill(prompt_body, 4000)  ← TRUNCATION POINT
  │           │     │
  │           │     ├─→ Agent(system_prompt=context+skill, tools=kb_tools)
  │           │     │     └─→ result = str(agent(query))     ← Full query, no truncation
  │           │     │
  │           │     ├─→ return raw                           ← Full result to supervisor
  │           │     └─→ emit(raw[:3000])                     ← Truncated for SSE only
  │           │
  │           └─→ ResultMessage(result, usage)
  │
  └─→ Save to session_store (full message, no truncation)
```

---

## New Test Categories: Context Integrity & State

### Category 7: Context Loss Detection via Langfuse (Tests 77-82)

These tests query Langfuse traces post-execution to detect truncation, context loss, and incomplete handoffs.

| # | Test | What's Checked | Langfuse Validation |
|---|------|---------------|---------------------|
| 77 | `test_skill_prompt_not_truncated` | Verify skill body < 4000 chars (or detect truncation marker) | Check `system_prompt` attr in trace metadata for `[... truncated` |
| 78 | `test_subagent_receives_full_query` | Supervisor's delegation query passes complete to subagent | Compare supervisor tool_use input vs subagent trace input |
| 79 | `test_subagent_result_not_lost` | Supervisor receives full subagent output (not 3000-char truncated) | Check supervisor's tool_result content length in trace |
| 80 | `test_input_tokens_within_context_window` | Total input tokens < 200K (Claude context limit) | `GENERATION.usage.input_tokens` < 200000 |
| 81 | `test_history_messages_count` | Verify how many history messages were sent to model | Count `messages` array length in trace metadata |
| 82 | `test_no_empty_subagent_responses` | Subagent never returns empty string | Check all SPAN observations for non-empty output |

### Category 8: Handoff Summary Validation (Tests 83-87)

These tests validate that information flows correctly between supervisor and subagents — no data lost in translation.

| # | Test | Scenario | Validation |
|---|------|----------|------------|
| 83 | `test_intake_findings_reach_supervisor` | oa-intake identifies FAR Part → supervisor references it | Supervisor response mentions FAR Part that intake identified |
| 84 | `test_legal_risk_rating_propagates` | legal-counsel rates protest risk → supervisor includes rating | Supervisor response includes risk level (high/medium/low) |
| 85 | `test_multi_skill_chain_context_preserved` | supervisor → intake → legal → market (3-hop chain) | Final response references findings from ALL three specialists |
| 86 | `test_supervisor_synthesizes_not_parrots` | Supervisor shouldn't just paste subagent output | Response is shorter than sum of subagent outputs |
| 87 | `test_document_context_from_intake_to_docgen` | Intake gathers requirements → doc-gen receives them | Generated SOW references specific requirements from intake (not generic placeholders) |

### Category 9: State Persistence & Update (Tests 88-94)

These tests validate session state management — messages saved, loaded, and not lost between turns.

| # | Test | What's Tested | Validation |
|---|------|-------------|------------|
| 88 | `test_session_creates_and_persists` | First message creates session in DynamoDB | `session_store.get_session(session_id)` returns valid session |
| 89 | `test_message_saved_after_turn` | Each turn saves user + assistant messages | `session_store.get_messages(session_id)` count increases by 2 per turn |
| 90 | `test_history_loaded_on_resume` | Session resume loads prior messages | sdk_query receives `messages` parameter with prior conversation |
| 91 | `test_100_message_limit_behavior` | Session with >100 messages — what happens? | Assert behavior: either error, summarize, or silently truncate (document which) |
| 92 | `test_tool_calls_in_saved_messages` | Tool use/result blocks persist in message history | Saved messages contain tool_use and tool_result content blocks |
| 93 | `test_session_metadata_updates` | Session metadata (last_active, message_count) updates per turn | `get_session()` shows updated timestamp and count |
| 94 | `test_concurrent_session_isolation` | Two sessions for same tenant don't cross-contaminate | Session A's messages not in Session B's history |

### Category 10: Context Window Budget (Tests 95-98)

These tests monitor and validate context window utilization to catch budget overflows before they cause failures.

| # | Test | What's Tested | Validation |
|---|------|-------------|------------|
| 95 | `test_supervisor_prompt_size_within_budget` | Measure supervisor system_prompt character count | Assert < 50K chars (leaves room for history + response) |
| 96 | `test_skill_prompts_all_within_4k_limit` | Check all skill bodies against MAX_SKILL_PROMPT_CHARS | List any skills that get truncated, flag as warning |
| 97 | `test_total_input_tokens_logged_in_langfuse` | Langfuse trace records actual token count | `GENERATION.usage.input_tokens` is non-zero and reasonable |
| 98 | `test_cache_utilization_for_system_prompt` | System prompt cache_write/cache_read tokens tracked | `cache_write_input_tokens` > 0 on first call, `cache_read` > 0 on subsequent |

---

## Implementation Order

### Phase 1: Infrastructure (1 day)
1. Add `StrandsResultCollector` class that captures `result.metrics.tool_metrics` after each `agent()` call
2. Add `LangfuseTraceValidator` helper that queries Langfuse API post-test
3. Add `CloudWatchEventValidator` helper that emits + queries CW events
4. Add `--validate-traces` flag to test runner CLI

### Phase 2: Tool Chain Tests (Tests 43-48, 1 day)
5. Write 6 tests validating tool dispatch through metrics
6. Each test uses real `build_skill_tools()` resolution chain
7. Assert `tool_name in result.metrics.tool_metrics`

### Phase 3: Observability Tests (Tests 49-55, 1 day)
8. Write Langfuse validation tests (4 tests)
9. Write CloudWatch emission tests (3 tests)
10. Wire into eval_aws_publisher for CloudWatch

### Phase 4: KB Integration Tests (Tests 56-60, 0.5 day)
11. Write 5 tests that exercise search_far, knowledge_search, knowledge_fetch, web_search
12. Each validates returned data (not just "tool was called" but "returned useful results")

### Phase 5: MVP1 UC E2E Tests (Tests 61-72, 2 days)
13. Port all 12 UC prompts from old eval with real agent.md prompts
14. Add tool chain validation to each
15. Add Langfuse trace link to each
16. Wire CloudWatch emission per UC

### Phase 6: Document Gen E2E (Tests 73-76, 1 day)
17. Write 4 document generation tests
18. Validate section structure, no placeholders, S3 persistence
19. boto3 confirmation of S3 objects

---

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `server/tests/test_strands_eval.py` | MODIFY | Add tests 43-76 |
| `server/tests/eval_helpers.py` | CREATE | StrandsResultCollector, LangfuseTraceValidator, CloudWatchEventValidator |
| `server/tests/eval_aws_publisher.py` | MODIFY | Add per-UC event emission |
| `.claude/skills/mvp1-eval/SKILL.md` | MODIFY | Update test inventory (42 → 76) |
| `.claude/skills/mvp1-eval/config.json` | MODIFY | Add new test file references |

---

## Success Criteria

| Metric | Current | Target |
|--------|---------|--------|
| Total tests | 42 | 76 |
| Tests hitting live Bedrock | 6 | 40+ |
| Tests validating tool chains | 0 | 18 |
| Tests checking Langfuse traces | 0 | 16 |
| Tests emitting CloudWatch events | 0 | 15 |
| Tests using real agent.md prompts | 20 | 40+ |
| MVP1 UCs covered with E2E | 8 (keyword only) | 12 (tool chain + Langfuse + CW) |
| Document generation validated | 0 | 4 |
| Knowledge base integration tested | 0 | 5 |

---

## Verification

```bash
# Run expanded Tier 2 (tool chain + Langfuse + CW)
AWS_PROFILE=eagle python tests/test_strands_eval.py --tests 43-76 --model haiku --validate-traces

# Run full MVP1 coverage
AWS_PROFILE=eagle python tests/test_strands_eval.py --mvp 1 --model haiku --validate-traces

# Run with CloudWatch emission
AWS_PROFILE=eagle python tests/test_strands_eval.py --full --emit-cloudwatch --validate-traces
```
