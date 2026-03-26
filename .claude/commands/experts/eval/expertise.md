---
type: expert-file
parent: "[[eval/_index]]"
file-type: expertise
human_reviewed: false
tags: [expert-file, mental-model, eval, testing, eagle, aws, cloudwatch]
last_updated: 2026-03-23T00:00:00
tags: [expert-file, mental-model, eval, testing, eagle, strands, aws, cloudwatch, langfuse, self-improve]
---

# Eval Expertise (Complete Mental Model)

> **Sources**: server/tests/test_strands_eval.py, server/tests/eval_helpers.py, server/tests/eval_aws_publisher.py, server/app/strands_agentic_service.py, eagle-plugin/

---

## Part 1: Test Suite Architecture

### File Layout

```
server/tests/test_strands_eval.py          # 98 tests, standalone CLI entry point (not pytest)
server/tests/eval_helpers.py               # Validators: Langfuse, CloudWatch, ToolChain, SkillPrompt
server/tests/eval_aws_publisher.py         # S3 archival + CloudWatch custom metrics
server/eagle_skill_constants.py            # Embedded skill/prompt constants
server/app/strands_agentic_service.py      # sdk_query(), build_skill_tools(), build_supervisor_prompt()
eagle-plugin/agents/*/agent.md             # Specialist agent prompts (source of truth)
eagle-plugin/skills/*/SKILL.md             # Skill workflow definitions
data/eval/results/                         # Per-run JSON results (run-<ts>.json, latest.json)
data/eval/videos/                          # Browser recording videos (.webm/.mp4)
data/eval/telemetry/                       # Local CloudWatch mirror (cw-<ts>.json)
```

### Test Categories (10 categories, 98 tests)

| Category | Tests | Type | LLM Cost | Dependencies |
|----------|-------|------|----------|-------------|
| 1. SDK Patterns | 1-8 | Sessions, traces, subagents, cost, tools | Yes (Bedrock) | AWS Bedrock |
| 2. Skill Validation | 9-15 | Skill system_prompt + specialist queries | Yes (Bedrock) | eagle_skill_constants |
| 3. AWS Tools | 16-20 | execute_tool() direct + boto3 confirm | None | boto3, AWS services |
| 4. UC Workflows | 21-27 | Multi-turn workflow queries via sdk_query() | Yes (Bedrock) | strands_agentic_service |
| 5. SDK Architecture | 28-34 | Admin, workspace, CRUD, skill-subagent | Yes (Bedrock) | strands_agentic_service |
| 6. Compliance Matrix | 35-48 | Requirements matrix + FAR + tool chains | Yes (Bedrock) | strands_agentic_service |
| 7. Langfuse + CW | 49-55 | Trace validation, token counts, CW events | Partial | Langfuse API, CloudWatch |
| 8. Context Loss | 56-60, 77-82 | KB integration, prompt truncation, empty responses | Yes (Bedrock) | strands_agentic_service |
| 9. Handoff | 83-87 | Cross-agent context propagation | Yes (Bedrock) | strands_agentic_service |
| 10. State + Budget | 88-98 | Session persistence, isolation, prompt size | Yes (Bedrock) | DynamoDB, Langfuse |

### CLI Interface

```bash
# Run all 98 tests (sequential)
cd server && python tests/test_strands_eval.py --model us.anthropic.claude-3-5-haiku-20241022-v1:0

# Run specific tests
python tests/test_strands_eval.py --model us.anthropic.claude-3-5-haiku-20241022-v1:0 --tests 16,17,18,19,20

# Run with trace validation and CloudWatch emission
python tests/test_strands_eval.py --model us.anthropic.claude-3-5-haiku-20241022-v1:0 --validate-traces --emit-cloudwatch

# Run a category
python tests/test_strands_eval.py --model us.anthropic.claude-3-5-haiku-20241022-v1:0 --tests 61,62,63,64,65,66,67,68,69,70,71,72
```

### Execution Flow

```
main()
  |-- Parse args (--model, --tests, --async, --validate-traces, --emit-cloudwatch)
  |-- Phase A: Sequential tests 1-2 (session create/resume, linked)
  |-- Phase B: Independent tests 3-98 (sequential or --async parallel)
  |      selected_tests = list(range(1, 99))  # default: all 98
  |-- Summary printout (grouped by category, 10 sections)
  |-- Write data/eval/results/run-<ts>.json + latest.json
  |-- emit_to_cloudwatch() -> /eagle/test-runs (structured log events)
  |-- if _HAS_AWS_PUBLISHER:
  |     |-- publish_eval_metrics() -> EAGLE/Eval namespace (custom CW metrics)
  |     |-- archive_results_to_s3() -> s3://eagle-eval-artifacts/eval/results/
  |     |-- archive_videos_to_s3() -> s3://eagle-eval-artifacts/eval/videos/
```

### Self-Improvement Levers

The eval expert can modify these 5 levers to improve agent behavior based on test failures:

| # | Lever | File(s) | Impact |
|---|-------|---------|--------|
| 1 | Agent prompts | `eagle-plugin/agents/*/agent.md` | Domain knowledge, output format |
| 2 | Skill workflows | `eagle-plugin/skills/*/SKILL.md` | Tool usage patterns, step ordering |
| 3 | Supervisor routing | `eagle-plugin/agents/supervisor/agent.md` | FAST vs DEEP delegation |
| 4 | Trigger patterns | YAML frontmatter in agent/skill files | Keyword activation |
| 5 | Context budget | `MAX_SKILL_PROMPT_CHARS` in strands_agentic_service.py | Truncation threshold (currently 4000) |

### Root Cause Classification

| Code | Root Cause | Fix Lever | Signal |
|------|-----------|-----------|--------|
| ROUTING | Wrong specialist or FAST when DEEP needed | 3 | Expected agent not invoked |
| PROMPT | Missing domain knowledge in specialist | 1 | Right agent, wrong answer |
| TOOL | Expected tool not called | 2 | Skill workflow missing tool step |
| TRUNCATION | Skill prompt truncated, losing instructions | 5 | Skill > 4000 chars, lost section matters |
| DATA | Test assertion too strict for model | Test file | Haiku can't hit threshold Sonnet can |
| BUDGET | Total prompt exceeds context window | 5 + 1 | Token count errors |

---

## Part 2: SDK Pattern Tests (1-6)

### Test 1: Session Creation
- Creates session via `query()` with tenant context in `system_prompt`
- Captures `session_id` from `SystemMessage.data` or `ResultMessage.session_id`
- Passes session_id to Test 2

### Test 2: Session Resume
- Uses `query(resume=session_id)` with same system_prompt
- Validates same session_id returned
- Checks conversation history awareness
- **Key discovery**: `system_prompt` is NOT preserved across resume

### Test 3: Trace Observation
- Triggers ToolUseBlock traces via Glob/Read tools
- Validates ThinkingBlock, TextBlock, ResultMessage presence
- Maps to frontend event types

### Test 4: Subagent Orchestration
- Defines `file-analyzer` and `code-reader` subagents via `AgentDefinition`
- Validates Task tool calls with `parent_tool_use_id`
- Checks Bedrock backend (toolu_bdrk_ prefix)

### Test 5: Cost Tracking
- Runs 2 queries, accumulates `ResultMessage.usage`
- Tracks input/output tokens, cache, cost USD
- Validates within tier budget

### Test 6: Tier-Gated MCP Tools
- Creates SDK MCP server with `lookup_product` tool
- Tests premium-tier tool access
- Handles MCP race condition on Windows (ExceptionGroup)

---

## Part 3: Skill Validation Tests (7-15)

### Skill Loading Pattern

```python
from eagle_skill_constants import SKILL_CONSTANTS
content = SKILL_CONSTANTS["oa-intake"]  # or "02-legal.txt", etc.
system_prompt = tenant_context + content
```

### Available Skills

| Key | Skill | Test |
|-----|-------|------|
| `oa-intake` | OA Intake (SKILL.md) | 7, 9 |
| `02-legal.txt` | Legal Counsel | 10 |
| `04-market.txt` | Market Intelligence | 11 |
| `03-tech.txt` | Tech Review | 12 |
| `05-public.txt` | Public Interest | 13 |
| `document-generator` | Document Generator | 14 |

### Validation Pattern
Each skill test:
1. Loads skill content from `SKILL_CONSTANTS`
2. Injects as `system_prompt` with tenant context prefix
3. Sends domain-specific prompt
4. Checks response for skill indicators (keywords)
5. Passes if >= 3/5 indicators found

### Test 9: Multi-Turn Workflow
- 3-phase CT scanner acquisition intake
- Uses session resume between turns
- Validates keyword progression across phases

### Test 15: Supervisor Multi-Skill Chain
- Defines 3 skill subagents (intake, market, legal) via `AgentDefinition`
- Supervisor orchestrates sequential delegation
- Validates >= 2 subagent invocations + synthesis

---

## Part 4: AWS Tool Integration Tests (16-20) — Layer 1: AWS Infrastructure

### execute_tool() Interface

```python
from app.agentic_service import execute_tool

# Returns JSON string
result_json = execute_tool("tool_name", {params}, session_id)
result = json.loads(result_json)
```

### Tool Dispatch

| Tool Name | Handler | Needs Session |
|-----------|---------|--------------|
| `s3_document_ops` | `_exec_s3_document_ops` | Yes |
| `dynamodb_intake` | `_exec_dynamodb_intake` | No |
| `cloudwatch_logs` | `_exec_cloudwatch_logs` | No |
| `create_document` | `_exec_create_document` | Yes |
| `search_far` | `_exec_search_far` | No |
| `get_intake_status` | `_exec_get_intake_status` | Yes |
| `intake_workflow` | `_exec_intake_workflow` | No |

### Tenant/User Scoping

```python
# session_id="test-session-001" resolves to:
_extract_tenant_id(session_id) -> "demo-tenant"
_extract_user_id(session_id)   -> "demo-user"  (non "ws-" prefix)

# S3 prefix: eagle/demo-tenant/demo-user/
# DDB key: PK=INTAKE#demo-tenant, SK=INTAKE#{item_id}
```

### Test 16: S3 Document Operations
Steps: write -> list -> read -> boto3 head_object -> cleanup delete
- Bucket: `nci-documents`
- Key pattern: `eagle/{tenant}/{user}/{test_key}`

### Test 17: DynamoDB Intake Operations
Steps: create -> read -> update -> list -> boto3 get_item -> cleanup delete
- Table: `eagle`
- Key: `PK=INTAKE#{tenant}`, `SK=INTAKE#{item_id}`

### Test 18: CloudWatch Logs Operations
Steps: get_stream -> recent -> search -> boto3 describe_log_groups
- Log group: `/eagle/test-runs`
- No cleanup needed (read-only)

### Test 19: Document Generation
Steps: create 3 docs (sow, igce, acquisition_plan) -> boto3 list_objects_v2 -> cleanup
- Documents saved to `eagle/{tenant}/{user}/documents/{type}_{timestamp}.md`
- Validates content headers, word count, $ amounts, FAR references

### Test 20: CloudWatch E2E Verification
Steps: describe_log_streams -> get_log_events -> parse structure -> check run_summary
- Validates previous run's CloudWatch events
- Checks structured JSON (type, test_id, status fields)
- Verifies run_summary tally: passed + skipped + failed == total

---

## Part 4b: SDK Architecture Tests (28)

### Test 28: SDK Skill→Subagent Orchestration
- Tests `sdk_agentic_service.py` — the skill→subagent pattern with separate context windows
- Step 1: `build_skill_agents()` builds all 6 AgentDefinitions from SKILL_CONSTANTS
- Step 2: `build_supervisor_prompt()` generates routing prompt (no skill content leaked)
- Step 3: `sdk_query()` runs supervisor that delegates to subagents via Task tool
- Uses only 2 skills (oa-intake, legal-counsel) for cost control
- Handles ExceptionGroup for Windows MCP cleanup
- 5 indicators: agents_built, supervisor_prompt_valid, subagent_delegation, intake_or_legal_invoked, response_has_content
- **Depends on**: `server/app/sdk_agentic_service.py`, `eagle_skill_constants.py`

---

## Part 4c: Layer 2 — Requirements Matrix Tests (29-33)

### Overview
Tests 29-33 validate EAGLE's acquisition domain correctness by running five canonical
acquisition scenarios through `sdk_query()` and asserting the presence/absence of
specific document types and FAR citations in the response text.

### sdk_query() Shim
All Layer 2 and Layer 3 tests use a local shim that delegates to `sdk_agentic_service.sdk_query`:

```python
async def sdk_query(
    prompt: str,
    tenant_id: str = "demo-tenant",
    user_id: str = "demo-user",
    tier: str = "advanced",
    model: str = None,
    skill_names=None,
    session_id=None,
    workspace_id=None,
    max_turns: int = 15,
)
```

The shim is defined in the test file itself; it lazily imports `sdk_agentic_service.sdk_query`
on first call via `try: from sdk_agentic_service import sdk_query as _sdk_query_import`.

### Assertion Pattern
Each matrix test:
1. Calls `sdk_query()` with `tier="advanced"`, `max_turns=5`
2. Accumulates all TextBlocks + ResultMessage.result into `all_text` (lowercased)
3. Checks PRESENT assertions (keywords that MUST appear)
4. Checks ABSENT assertions (keywords that must NOT appear — validates no over-engineering)
5. Passes if `passes >= threshold AND summary_ok(collector)`
6. `summary_ok()` returns True if `collector.total_messages > 0`

### Test 29: Micro-Purchase ($8K)
- Scenario: office supplies purchase at $8K
- PRESENT: `purchase_request`, `micro_purchase/micro-purchase`, `far_13_2` (FAR Part 13)
- ABSENT: SOW, acquisition plan, J&A
- Threshold: 4/6
- Unique validation: confirms EAGLE does NOT over-engineer a micro-purchase

### Test 30: SAP Small Business Set-Aside ($150K)
- Scenario: $150K supply purchase, small business set-aside
- PRESENT: IGCE, market research, small business review (HHS-653/SBR/SBSA), SOW
- ABSENT: acquisition plan (not required below $350K SAT)
- Threshold: 4/5

### Test 31: IT Services T&M IDIQ ($2M)
- Scenario: $2M T&M IDIQ task order for IT services
- PRESENT: SOW, IGCE, acquisition plan, D&F (Determination & Findings), QASP,
  Section 508/accessibility, subcontracting, FAR 16.601 (T&M least-preferred D&F)
- Threshold: 5/8
- Key cite: FAR 16.601 D&F is NCI-specific requirement for T&M type

### Test 32: R&D CPFF Human Subjects ($8M)
- Scenario: $8M CPFF R&D contract with human subjects research
- PRESENT: acquisition plan, D&F, human subjects/IRB, QASP, fee cap (15%),
  FAR 16.301 or accounting system reference
- Threshold: 4/6
- Key cite: human subjects / IRB is NCI-specific domain knowledge

### Test 33: Large Sole Source IT ($25M, SPE)
- Scenario: $25M sole source IT services requiring Senior Procurement Executive approval
- PRESENT: J&A, FAR 6.302, SPE reference, acquisition plan, Section 508,
  subcontracting, competition/protest risk (double-weighted via `has_acquisition_plan_2`)
- Threshold: 5/8
- Key cite: FAR 6.302-1 authority + SPE approval level

---

## Part 4d: Layer 3 — SDK Path AWS Integration Tests (34-38)

### Overview
Tests 34-38 exercise the full `sdk_query() → MCP → AWS tool` path. The LLM path is
primary (same text-assertion pattern as Layer 2); AWS connectivity is a **soft check**
(non-fatal boto3 call that adds a `_reachable` detail key but does not affect pass/fail).

### Assertion Pattern
Each Layer 3 test:
1. Calls `sdk_query()` with `tier="premium"` (34, 35, 37, 38) or `tier="advanced"` (36)
2. Asserts 2-4 core text indicators
3. Runs a soft boto3 or `execute_tool()` check for AWS reachability
4. Pass condition: `passes >= threshold AND summary_ok(collector)`
   - Soft `_reachable` keys are excluded from the pass count

### Test 34: SDK→S3 Intake Document (SOW)
- Prompt: process $2M IT services intake, generate and save SOW to S3
- Core assertions: `has_sow_or_doc`, `has_it_services` (threshold 2/2)
- Soft: boto3 `list_objects_v2` on `EAGLE_S3_BUCKET` env var (default `eagle-documents-dev`)
- S3 prefix checked: `tenants/{tenant_id}/documents/`

### Test 35: SDK→DynamoDB Intake Record
- Prompt: start new intake package for CT scanner at NCI
- Core assertions: `has_intake`, `has_ct_scanner` (threshold 2/2)
- Soft: `execute_tool("dynamodb_intake", {"action": "list", ...})` via session ID `{tenant}-premium-{user}-test35`

### Test 36: SDK→FAR Search Result
- Prompt: FAR clauses for sole source IT contract > $1M
- Core assertions: `has_far_6_302`, `has_52_207_or_52_212`, `has_response` (threshold 2/3)
- No boto3 soft check (knowledge/search only)

### Test 37: SDK→Document Generation J&A Compliance
- Prompt: generate J&A for $2.5M sole source to BioResearch Labs for proprietary reagents
- Core assertions: `has_6_302` (FAR 6.302-1), `has_far`, `has_authority_or_approval`, `has_response` (threshold 3/4)
- Tier: premium, max_turns=8

### Test 38: SDK→CloudWatch Audit Trail
- Prompt: retrieve last 5 log entries for session's intake work
- Core assertions: `has_logs_or_cw` (log/cloudwatch/audit keywords), `has_response` (threshold 1/2)
- Tier: premium, max_turns=5

---

## Part 5: CloudWatch Telemetry

### Log Group Structure

```
/eagle/test-runs/
  |-- run-2026-02-09T...Z/    # Per-run stream
      |-- test_result events   # One per test (test_id 1-38)
      |-- run_summary event    # Totals
```

### Event Schema

```json
// test_result event
{
  "type": "test_result",
  "test_id": 1,
  "test_name": "1_session_creation",
  "status": "pass|fail|skip",
  "log_lines": 42,
  "run_timestamp": "2026-02-09T...",
  "model": "haiku",
  "input_tokens": 1234,
  "output_tokens": 567,
  "cost_usd": 0.000123
}

// run_summary event
{
  "type": "run_summary",
  "run_timestamp": "2026-02-09T...",
  "total_tests": 98,
  "passed": 36,
  "skipped": 1,
  "failed": 1,
  "pass_rate": 94.7,
  "model": "haiku",
  "total_input_tokens": 45000,
  "total_output_tokens": 12000,
  "total_cost_usd": 0.012345
}
```

### Emission Pattern

```python
# Stage 1: Structured log events (emit_to_cloudwatch)
emit_to_cloudwatch(trace_output, results)
# Non-fatal: catches all exceptions
# Creates log group + stream if needed
# Sorts events by timestamp (CloudWatch requirement)
# Also writes local mirror: data/eval/telemetry/cw-<ts>.json

# Stage 2: Custom metrics + S3 archival (eval_aws_publisher)
if _HAS_AWS_PUBLISHER:
    publish_eval_metrics(results, run_ts, test_summaries=_test_summaries)
    archive_results_to_s3(trace_file, run_ts_file)
    archive_videos_to_s3(video_dir, run_ts_file)
```

### Timestamp Encoding
- `test_result` events: `timestamp = now_ms + test_id` (unique per test)
- `run_summary` event: `timestamp = now_ms + 200` (after all test IDs 1-98)

### Custom Metrics (EAGLE/Eval Namespace)

Published by `eval_aws_publisher.publish_eval_metrics()`:

| Metric | Unit | Dimensions | Purpose |
|--------|------|------------|---------|
| `PassRate` | Percent | (none) | Dashboard trending |
| `PassRate` | Percent | `RunId` | Per-run detail |
| `TestsPassed` | Count | (none) | Aggregate pass count |
| `TestsFailed` | Count | (none) | Aggregate fail count |
| `TestsSkipped` | Count | (none) | Aggregate skip count |
| `TotalCost` | None | (none) | USD cost if > 0 |
| `TestStatus` (x98) | None | `TestName` | 1.0=pass, 0.0=fail per test |

### S3 Artifact Archival

Published by `eval_aws_publisher.archive_results_to_s3()` and `archive_videos_to_s3()`:

```
s3://eagle-eval-artifacts/
  eval/results/run-<ISO-ts>.json                # Results JSON per run
  eval/videos/<run-ts>/<test_dir>/<file>.webm   # Browser recordings
```

---

## Part 6: Registration Mappings

Every test must be registered in **3 backend locations** in `server/tests/test_strands_eval.py`. Missing any causes silent data loss (test runs but results don't show in CloudWatch).

### Backend Registrations (server/tests/test_strands_eval.py)

| # | Location | Format | Purpose |
|---|----------|--------|---------|
| 1 | `TEST_REGISTRY` in `_run_test()` | `N: ("N_snake_name", test_N_snake_name)` | Dispatch: maps test ID to (result_key, function) |
| 2 | `test_names` in `emit_to_cloudwatch()` | `N: "N_snake_name"` | CloudWatch event `test_name` field |
| 3 | Summary `print()` line in `main()` | `print(f"    Label: {_rdy(key)}")` | Terminal readiness output |

Additional registrations:
- `selected_tests` default: `list(range(1, 99))` -- include test when `--tests` not specified
- `eval_aws_publisher.py` `_TEST_NAMES` dict: must match test_names for CloudWatch metric per-test emission

### Frontend Registrations (optional, for dashboards)

| # | File | Variable | Format |
|---|------|----------|--------|
| 4 | `test_results_dashboard.html` | `TEST_DEFS` | `{ id: N, name: "...", desc: "...", category: "..." }` |
| 5 | `client/app/admin/tests/page.tsx` | `TEST_NAMES` | `'N': 'Human-Readable Name'` |
| 6 | `client/app/admin/eval/page.tsx` | `SKILL_TEST_MAP` | `tool_key: [N]` (AWS tools only) |

### Category Tags

| Category | Tests | Description |
|----------|-------|-------------|
| `sdk` | 1-8 | SDK patterns: sessions, traces, subagents, cost, tools |
| `skills` | 9-15 | Skill loading, specialist validation, multi-skill chains |
| `aws` | 16-20 | AWS tool integration with boto3 confirm |
| `uc` | 21-27 | UC workflow validation (UC-02 through UC-09) |
| `arch` | 28-34 | SDK architecture: admin, workspace, CRUD, skill-subagent |
| `matrix` | 35-48 | Compliance matrix, FAR/DFARS, tool chains |
| `langfuse` | 49-55 | Langfuse trace validation + CloudWatch E2E |
| `kb` | 56-60 | KB integration: FAR search, web search, thresholds |
| `e2e` | 61-72 | MVP1 UC E2E workflows |
| `docgen` | 73-76 | Document generation: SOW, IGCE, AP, market research |
| `context` | 77-82 | Context loss detection: truncation, empty responses |
| `handoff` | 83-87 | Cross-agent handoff: findings propagation, synthesis |
| `state` | 88-94 | State persistence: sessions, messages, isolation |
| `budget` | 95-98 | Context budget: prompt sizes, token counts, cache |

### Full Test Name/Key Reference (1-38 shown; 39-98 in test file)

> Tests 39-98 are registered in `test_strands_eval.py` `TEST_REGISTRY` and cover categories:
> kb (56-60), e2e (61-72), docgen (73-76), context (77-82), handoff (83-87), state (88-94), budget (95-98).
> Run `python tests/test_strands_eval.py --tests 39` (or any ID) to see the test name at runtime.

| ID | Result Key | Summary Label |
|----|------------|---------------|
| 1 | `1_session_creation` | Session management (create/resume) |
| 2 | `2_session_resume` | Session management (create/resume) |
| 3 | `3_trace_observation` | Trace events (ThinkingBlock/ToolUseBlock) |
| 4 | `4_subagent_orchestration` | Subagent traces (agent_log events) |
| 5 | `5_cost_tracking` | Cost ticker (ResultMessage.usage) |
| 6 | `6_tier_gated_tools` | Tier-gated tools (MCP) |
| 7 | `7_skill_loading` | Skill loading (system_prompt) |
| 8 | `8_subagent_tool_tracking` | Subagent tool tracking |
| 9 | `9_oa_intake_workflow` | OA Intake workflow |
| 10 | `10_legal_counsel_skill` | Legal Counsel skill |
| 11 | `11_market_intelligence_skill` | Market Intelligence skill |
| 12 | `12_tech_review_skill` | Tech Review skill |
| 13 | `13_public_interest_skill` | Public Interest skill |
| 14 | `14_document_generator_skill` | Document Generator skill |
| 15 | `15_supervisor_multi_skill_chain` | Supervisor Multi-Skill Chain |
| 16 | `16_s3_document_ops` | S3 Document Operations |
| 17 | `17_dynamodb_intake_ops` | DynamoDB Intake Operations |
| 18 | `18_cloudwatch_logs_ops` | CloudWatch Logs Operations |
| 19 | `19_document_generation` | Document Generation (3 types) |
| 20 | `20_cloudwatch_e2e_verification` | CloudWatch E2E Verification |
| 21 | `21_uc02_micro_purchase` | UC-02 Micro-Purchase (<$15K) |
| 22 | `22_uc03_option_exercise` | UC-03 Option Exercise |
| 23 | `23_uc04_contract_modification` | UC-04 Contract Modification |
| 24 | `24_uc05_co_package_review` | UC-05 CO Package Review |
| 25 | `25_uc07_contract_closeout` | UC-07 Contract Close-Out |
| 26 | `26_uc08_shutdown_notification` | UC-08 Shutdown Notification |
| 27 | `27_uc09_score_consolidation` | UC-09 Score Consolidation |
| 28 | `28_sdk_skill_subagent_orchestration` | Skill→Subagent Orchestration |
| 29 | `29_matrix_micro_purchase` | Micro-Purchase ($8K) |
| 30 | `30_matrix_sap_small_business` | SAP Small Business ($150K) |
| 31 | `31_matrix_it_services_idiq` | IT Services T&M IDIQ ($2M) |
| 32 | `32_matrix_rd_cpff` | R&D CPFF Human Subjects ($8M) |
| 33 | `33_matrix_large_sole_source` | Large Sole Source SPE ($25M) |
| 34 | `34_sdk_s3_intake_document` | S3 Intake Document (SOW) |
| 35 | `35_sdk_dynamodb_intake_record` | DynamoDB Intake Record |
| 36 | `36_sdk_far_search_result` | FAR Search Result |
| 37 | `37_sdk_document_generation_compliance` | Document Generation J&A |
| 38 | `38_sdk_cloudwatch_audit_trail` | CloudWatch Audit Trail |

### SKILL_TEST_MAP (eval cross-reference)

| Key | Tests | Notes |
|-----|-------|-------|
| `intake` | 7, 9 | OA Intake skill |
| `docgen` | 14 | Document Generator skill |
| `tech-review` | 12 | Tech Review skill |
| `compliance` | 10 | Legal Counsel (compliance prompt key) |
| `supervisor` | 15 | Multi-skill chain |
| `02-legal.txt` | 10 | Legal skill file key |
| `04-market.txt` | 11 | Market skill file key |
| `03-tech.txt` | 12 | Tech skill file key |
| `05-public.txt` | 13 | Public Interest skill file key |
| `s3_document_ops` | 16 | S3 tool name |
| `dynamodb_intake` | 17 | DynamoDB tool name |
| `cloudwatch_logs` | 18 | CloudWatch tool name |
| `create_document` | 14, 19 | Doc generator (skill + tool) |
| `cloudwatch_e2e` | 20 | E2E verification |

---

## Part 7: Standard Operating Procedure -- Adding a New Test

### Pre-Flight

1. **Pick the next test ID** -- check `TEST_REGISTRY` for the highest current ID (currently 98), increment by 1
2. **Choose the tier** — SDK Pattern, Skill Validation, AWS Tool Integration, UC Workflow, SDK Architecture, Requirements Matrix, or SDK Path AWS
3. **Choose a category** — core, traces, agents, tools, skills, workflow, aws, uc, sdk-arch, matrix, or sdk-aws
4. **Name it** — snake_case for code (`N_descriptive_name`), Title Case for dashboards

### Step 1: Write the Test Function

Add before the `# ── Main` section in `server/tests/test_eagle_sdk_eval.py`:

**For Layer 2 (Requirements Matrix) pattern:**
```python
async def test_N_matrix_scenario():
    """Layer 2: Requirements Matrix — scenario description."""
    print("\n" + "=" * 70)
    print("TEST N: Requirements Matrix — Scenario Title")
    print("=" * 70)

    prompt = "Scenario-specific acquisition question..."

    tenant_id = "nci-oa"
    user_id = f"test-user-{N}"
    collector = TraceCollector()
    details: dict[str, bool] = {}

    try:
        async for message in sdk_query(
            prompt=prompt, tenant_id=tenant_id, user_id=user_id,
            tier="advanced", model=MODEL, max_turns=5,
        ):
            collector.process(message, indent=2)
    except ExceptionGroup as eg:
        real_errors = [e for e in eg.exceptions if "CLIConnection" not in type(e).__name__]
        if real_errors:
            raise ExceptionGroup("SDK errors", real_errors)
        print("    (MCP cleanup race on Windows — non-fatal)")
    except Exception as e:
        print(f"    sdk_query() error: {type(e).__name__}: {e}")

    all_text = " ".join(collector.text_blocks).lower()
    for msg_entry in collector.messages:
        msg = msg_entry["message"]
        if hasattr(msg, "result") and msg.result:
            all_text += " " + msg.result.lower()

    # PRESENT / ABSENT assertions
    details["has_required_doc"] = "required phrase" in all_text
    details["absent_over_engineering"] = "over-complex thing" not in all_text

    passes = sum(1 for v in details.values() if v)
    passed = passes >= THRESHOLD and summary_ok(collector)
    print(f"\n  Assertions: {passes}/{len(details)}")
    print(f"  {'PASS' if passed else 'FAIL'} - Requirements Matrix: Scenario Title")
    return passed
```

**For Layer 3 (SDK Path AWS Integration) pattern:**
```python
async def test_N_sdk_feature():
    """Layer 3: SDK Path AWS Integration — feature description."""
    # ... same sdk_query() setup ...
    details: dict[str, bool] = {}

    # ... text assertions ...

    # Soft AWS check (non-fatal)
    try:
        import boto3
        # boto3 reachability check
        details["aws_reachable"] = True
    except Exception as err:
        details["aws_reachable"] = False  # soft — does not affect pass/fail

    passes = sum(1 for k, v in details.items() if v and k != "aws_reachable")
    passed = passes >= THRESHOLD and summary_ok(collector)
    return passed
```

**Rules for the function body:**
- SDK/LLM tests (tiers 1, 2, 5, 6, 7): use `query()` from claude-agent-sdk
- Skill tests (tier 3): load from `SKILL_CONSTANTS`, inject as `system_prompt`
- AWS tool tests (tier 4 / Layer 1): call `execute_tool()` directly, confirm with boto3
- Requirements Matrix (Layer 2): call `sdk_query()`, assert text, threshold >= 4/N
- SDK Path AWS (Layer 3): call `sdk_query()`, assert text, soft boto3 check (non-fatal)
- Always return `True`, `False`, or `None` (skip)
- Always handle `ExceptionGroup` for Windows MCP race on cleanup
- Cleanup all created AWS resources in a try/except (non-fatal)

### Step 2: Register in Backend (5 edits in server/tests/test_eagle_sdk_eval.py)

**2a. `TEST_REGISTRY`** (in `_run_test()`):
```python
N: ("N_descriptive_name", test_N_descriptive_name),
```

**2b. `test_names`** (in `emit_to_cloudwatch()`):
```python
N: "N_descriptive_name",
```

**2c. `result_key` dict** (in `main()` trace output loop):
```python
N: "N_descriptive_name",
```

**2d. Summary printout** (in `main()`, add a print line in the appropriate tier section):
```python
print(f"    Descriptive Title: {'Ready' if results.get('N_descriptive_name') else 'Needs work'}")
```

**2e. `selected_tests` default range** — update to:
```python
selected_tests = list(range(1, N+1))  # currently range(1, 99)
```

### Step 3: Register in Frontend (3 files)

**3a. `test_results_dashboard.html` — `TEST_DEFS`**:
```javascript
{ id: N, name: "Descriptive Title", desc: "One-line description", category: "matrix" },
```

**3b. `test_results_dashboard.html` — readiness panel**:
```javascript
{ label: "Descriptive label", ready: results[N]?.status === 'pass' },
```

**3c. `client/app/admin/tests/page.tsx` — `TEST_NAMES`**:
```typescript
'N': 'Descriptive Title',
```

**3d. `client/app/admin/eval/page.tsx` — `SKILL_TEST_MAP`** (if applicable):
```typescript
tool_or_skill_key: [N],
```

### Step 4: Validate

```bash
# Syntax check
python -c "import py_compile; py_compile.compile('server/tests/test_eagle_sdk_eval.py', doraise=True)"

# Run just the new test
python server/tests/test_eagle_sdk_eval.py --model haiku --tests N

# Verify CloudWatch emission
# (check /eagle/test-runs for event with test_id=N)

# Verify trace_logs.json has entry for test N
python -c "import json; d=json.load(open('data/eval/results/latest.json')); print(list(d['results'].keys()))"
```

### Step 5: Verify Dashboards

- Open `test_results_dashboard.html` in browser — test N card should appear
- Check the category filter button shows/hides it correctly
- Check readiness panel dot for test N
- If Next.js frontend is running, verify `/admin/tests` shows the test

### Checklist (copy-paste for PR descriptions)

```
- [ ] test function `test_N_name()` added with correct tier pattern
- [ ] ExceptionGroup handler included (MCP Windows race)
- [ ] TEST_REGISTRY entry (server/tests/test_eagle_sdk_eval.py _run_test())
- [ ] test_names entry (server/tests/test_eagle_sdk_eval.py emit_to_cloudwatch())
- [ ] result_key entry (server/tests/test_eagle_sdk_eval.py main() trace loop)
- [ ] summary printout line (server/tests/test_eagle_sdk_eval.py main())
- [ ] selected_tests range updated to range(1, N+1)
- [ ] TEST_DEFS entry (test_results_dashboard.html)
- [ ] readiness panel entry (test_results_dashboard.html)
- [ ] TEST_NAMES entry (client/.../tests/page.tsx)
- [ ] SKILL_TEST_MAP entry if applicable (client/.../eval/page.tsx)
- [ ] syntax check passes
- [ ] test passes with --tests N
- [ ] cleanup removes all test artifacts
```

---

## Part 8: Test Patterns and Conventions

### Test Naming Convention

- Result key: `{N}_{snake_case_name}` (e.g., `16_s3_document_ops`)
- Function: `test_{N}_{snake_case_name}` (e.g., `test_16_s3_document_ops`)

### AWS Tool Tests Pattern (16-20)

```python
async def test_N_name():
    # 1. Call execute_tool()
    result = json.loads(execute_tool("tool_name", {params}, session_id))
    # 2. Assert tool result
    # 3. boto3 independent confirmation
    # 4. Cleanup test artifacts
    # 5. Return pass/fail
```

### Requirements Matrix Tests Pattern (29-33)

```python
async def test_N_matrix_scenario():
    # 1. Call sdk_query() tier="advanced", max_turns=5
    # 2. Accumulate all_text from TextBlocks + ResultMessage.result
    # 3. Assert PRESENT (document types, FAR citations)
    # 4. Assert ABSENT (over-engineering indicators)
    # 5. passes >= threshold AND summary_ok(collector)
    # 6. Return pass/fail
```

### SDK Path AWS Integration Tests Pattern (34-38)

```python
async def test_N_sdk_feature():
    # 1. Call sdk_query() tier="premium", max_turns=8
    # 2. Accumulate all_text
    # 3. Assert 2-4 core text indicators (exclude _reachable from count)
    # 4. Soft boto3 or execute_tool() check (non-fatal, _reachable key)
    # 5. passes >= threshold (counting only non-_reachable keys)
    # 6. Return pass/fail
```

### Cleanup Requirement
All tests that create AWS resources MUST clean up:
- S3: `s3.delete_object()`
- DynamoDB: `table.delete_item()`
- CloudWatch: read-only tests don't need cleanup

---

## Part 9: Known Issues and Gotchas

### MCP Race Condition (Tests 6, 28-38)
- Windows ExceptionGroup on MCP server cleanup
- Handled with try/except for CLIConnection errors in ALL sdk_query() tests
- Pattern: filter `real_errors = [e for e in eg.exceptions if "CLIConnection" not in type(e).__name__]`
- May return SKIP if no messages collected

### Session Resume (Test 2)
- `system_prompt` is NOT preserved across `query(resume=session_id)`
- Must re-provide system_prompt on every call
- Correct for multi-tenant: tenant context should always be explicit

### Tenant Scoping in Tests
- `_extract_tenant_id()` always returns "demo-tenant" for test sessions
- `_extract_user_id()` returns "demo-user" for non "ws-" session IDs
- Tests 16-20 use session_id="test-session-001"
- Tests 29-38 use `tenant_id="nci-oa"`, `user_id="test-user-{N}"`

### Layer 2 Assertion Calibration
- Thresholds are intentionally loose (4/5 or 4/6 or 5/8) — LLM output is non-deterministic
- ABSENT assertions are load-bearing: they confirm EAGLE does not over-engineer
- `summary_ok()` is always AND-ed with the threshold: a zero-message response is always FAIL
- Test 33 double-weights `acquisition_plan` via a second key `has_acquisition_plan_2` for priority

### Layer 3 Soft AWS Checks
- `_reachable` detail keys are excluded from `passes` count by design
- AWS unreachability does not fail the test — the LLM path is the primary signal
- S3 bucket env var: `EAGLE_S3_BUCKET` (default `eagle-documents-dev`)

### Skill Loading
- Uses dict lookup from `eagle_skill_constants.SKILL_CONSTANTS`
- No filesystem dependency on nci-oa-agent
- Self-contained for test portability

### CloudWatch Emission
- Non-fatal: catches all exceptions
- Falls back to local data/eval/results/latest.json
- Events must be sorted by timestamp (CloudWatch requirement)
- Local telemetry mirror written to data/eval/telemetry/cw-<ts>.json

---

## Learnings

### patterns_that_work
- Direct execute_tool() testing is deterministic, fast, and free (Layer 1)
- boto3 independent confirmation prevents false positives (Layer 1)
- PRESENT + ABSENT text assertions together validate domain correctness without LLM determinism (Layer 2)
- Loose thresholds (4/5, 4/6, 5/8) tolerate phrasing variation while catching gross failures
- `summary_ok()` guard (total_messages > 0) prevents empty-response false passes
- Soft boto3 / execute_tool() checks in Layer 3 validate AWS reachability without blocking the test
- Excluding `_reachable` keys from pass-count separates LLM correctness from infra availability
- Cleanup with try/except prevents test pollution
- Structured CloudWatch events enable dashboard querying
- Import-guard pattern (`try: from eval_aws_publisher import ...; _HAS_AWS_PUBLISHER = True except ImportError: _HAS_AWS_PUBLISHER = False`) makes AWS publisher zero-impact when module unavailable (discovered: 2026-02-10, component: eval_aws_publisher integration)
- Lazy-loaded boto3 clients in eval_aws_publisher avoid import-time AWS calls — clients only created on first use (discovered: 2026-02-10, component: eval_aws_publisher)
- Each publisher function is independently non-fatal — one failure doesn't block others (discovered: 2026-02-10, component: eval_aws_publisher)
- Publishing ~38 CloudWatch custom metrics in a single put_metric_data call is well under the 1000-per-call limit (discovered: 2026-02-25, component: eval_aws_publisher)
- `run_ts_file` format `%Y-%m-%dT%H-%M-%SZ` is shared between local file naming and S3 key paths for consistent cross-referencing (discovered: 2026-02-10, component: eval_aws_publisher)
- Testing `sdk_agentic_service` functions (build_skill_agents, build_supervisor_prompt) deterministically before running live sdk_query() — catches import/config issues without LLM cost (discovered: 2026-02-10, component: test_28)
- Limiting subagent skills in test (2 of 6) for cost control while still validating the delegation pattern (discovered: 2026-02-10, component: test_28)
- sdk_query() shim defined locally in test file — delegates to sdk_agentic_service.sdk_query via lazy import, avoids circular dependency (discovered: 2026-02-25, component: tests 29-38)
- NCI-specific knowledge (human subjects/IRB, HHS-653 form, SPE approval, FAR 16.601 T&M D&F) is testable via text assertion -- validates domain knowledge is embedded in skill prompts (discovered: 2026-02-25, component: tests 29-33)
- `_collect_sdk_query()` shared helper reduces boilerplate across tests 49-98 -- single function wraps sdk_query() call, error handling, and text accumulation (discovered: 2026-03-20, component: tests 49-98)
- `_rdy(key)` helper for summary output -- returns "Ready" if results.get(key) else "Needs work", cleaner than inline ternary (discovered: 2026-03-20, component: summary output)
- eval_helpers.py validators (LangfuseTraceValidator, CloudWatchEventValidator, ToolChainValidator, SkillPromptValidator) enable post-test assertions without modifying the test runner (discovered: 2026-03-20, component: eval_helpers)
- 9 of 15 skills exceed MAX_SKILL_PROMPT_CHARS (4000) and get truncated by _truncate_skill() -- critical context loss point (discovered: 2026-03-20, component: strands_agentic_service)
- Closed-loop self-improvement (DIAGNOSE -> PRIORITIZE -> FIX -> VALIDATE) is more effective than open-loop (just updating docs) -- the 5 levers (agent prompts, skill workflows, supervisor routing, trigger patterns, context budget) are the actual fix surfaces (discovered: 2026-03-20, component: self-improve)

### patterns_to_avoid
- Don't rely on LLM output for deterministic assertions — use threshold-based keyword checks
- Don't skip cleanup — leaves artifacts that confuse future runs
- Don't test CloudWatch writes in same run as reads (eventual consistency)
- Don't import eval_aws_publisher at module top-level without guard — breaks eval suite on machines without boto3 (discovered: 2026-02-10, component: eval_aws_publisher)
- Don't make boto3 AWS checks in Layer 3 fatal -- they will fail in local dev without AWS credentials
- Don't use Unicode characters (arrows, em-dashes, >=) in print statements -- Windows cp1252 encoding crashes stdout. Use ASCII equivalents: -> instead of U+2192, -- instead of U+2014, >= instead of U+2265 (discovered: 2026-03-20, component: Windows compatibility)
- Don't update expertise.md without also fixing the actual agent/skill code -- open-loop self-improvement (docs only) doesn't close the feedback loop (discovered: 2026-03-20, component: self-improve pattern)
- Don't batch multiple lever changes before re-running tests -- isolate one lever per fix to identify which change worked (discovered: 2026-03-20, component: self-improve)

### pytest INTERNALERROR on test_strands_eval.py
- `test_strands_eval.py` has a top-level `argparse.parse_args()` call — running with `pytest` causes `SystemExit: 2` during collection (INTERNALERROR)
- **Fix**: Always run as `python tests/test_strands_eval.py --model <model>` directly, never with pytest
- **Symptom**: `INTERNALERROR> SystemExit: 2` on `pytest tests/test_strands_eval.py`

### Relative Import Failure in Standalone Mode
- Tests that use `from .compliance_matrix import ...` (relative import) fail when running as standalone script
- **Root cause**: Module not imported as a package when using `python tests/test_strands_eval.py`
- **Symptom**: `ImportError: attempted relative import with no known parent package`
- **Fix**: Use absolute import with `sys.path.insert(0, 'app')` pattern

### common_issues
- AWS credentials not configured -> all tool tests (16-20) fail; Layer 3 soft checks show `_reachable=False`
- S3 bucket "nci-documents" doesn't exist -> test 16/19 fail
- DynamoDB table "eagle" doesn't exist -> test 17 fails
- CloudWatch log group doesn't exist -> test 18/20 may still pass (get_stream returns empty)
- S3 bucket "eagle-eval-artifacts" doesn't exist -> archive_results_to_s3 and archive_videos_to_s3 print non-fatal error
- CloudWatch EAGLE/Eval namespace has no data -> dashboard shows no data until first successful publish
- `sdk_agentic_service.sdk_query` import fails -> tests 21-38 all fail; check server/app/ is on sys.path

### tips
- Run tests 16-20 first when debugging AWS connectivity
- Run tests 29-33 with `--model sonnet` if haiku is missing NCI-specific domain knowledge
- Use `--tests 29` to isolate a single matrix test
- Check `data/eval/results/latest.json` for per-test logs after a run
- CloudWatch test 20 validates the PREVIOUS run's data
- After an eval run, check S3 archival: `aws s3 ls s3://eagle-eval-artifacts/eval/results/`
- Check custom metrics: `aws cloudwatch list-metrics --namespace "EAGLE/Eval"`
- View eval dashboard in CloudWatch console: search for `EAGLE-Eval-Dashboard`
- The publisher module lives at `server/tests/eval_aws_publisher.py` — import it from the same directory as the eval suite
- Test 28 depends on `server/app/sdk_agentic_service.py` — import via `sys.path` (server/app already in path from line 30)
- Tests 29-38 also depend on `sdk_agentic_service.sdk_query` via the local shim — same path dependency
- Layer 2 (29-33) and Layer 3 (34-38) use `tenant_id="nci-oa"` (not "demo-tenant") — matches production NCI tenant
- When Layer 2 tests fail on text assertions, check if the skill prompts in `eagle-plugin/` contain the expected domain knowledge (human subjects, FAR citations, etc.)

---

## Part 10: mvp1-eval Skill Integration

The `.claude/skills/mvp1-eval/SKILL.md` skill provides a structured 5-phase runner that wraps the test suite for interactive use.

### Skill Location and Config

```
.claude/skills/mvp1-eval/SKILL.md      # 5-phase runner
.claude/skills/mvp1-eval/config.json   # Repo-keyed config (sm_eagle key = aws_profile, s3_bucket, etc.)
```

### Phase Overview

| Phase | What it does |
|-------|-------------|
| Step 0 | Load repo config from config.json (AWS_PROFILE, S3_BUCKET, SERVER_DIR, ENV_FILE) |
| Pre-flight | `aws sts get-caller-identity --profile $AWS_PROFILE` — **HARD ABORT** if fails |
| Tier 1 | `python -m pytest tests/test_*.py` (unit tests, no AWS) |
| Tier 2 | `AWS_PROFILE=eagle python -m pytest tests/test_strands_*.py` (live Bedrock, 6 tests) |
| Tier 3 | `AWS_PROFILE=eagle python tests/test_strands_eval.py --model <model>` (98 tests, ~30 min) |
| Phase 4 | Langfuse trace query — tokens, costs, per-trace subagent breakdown |
| Phase 5 | Teams webhook notification — Adaptive Card v1.4 to Azure Logic App |

### Pre-flight Hard Abort

If `aws sts get-caller-identity --profile eagle` exits non-zero:
```
PREFLIGHT FAILED: AWS profile 'eagle' is not authenticated.
Run: aws sso login --profile eagle
Aborting eval suite.
```
Do not proceed to any tier. This was added after the skill silently continued when unauthenticated.

### Teams Webhook (Phase 5)

- **Hardcoded fallback URL**: Azure Logic App at `prod-52.usgovtexas.logic.azure.us` — embedded in SKILL.md so Teams notification works even when `TEAMS_WEBHOOK_URL` is absent from `server/.env`
- **Lookup order**: `env.get("TEAMS_WEBHOOK_URL") or env.get("ERROR_WEBHOOK_URL") or _DEFAULT_WEBHOOK`
- **Card style**: `"good"` (green) if all tiers pass, `"attention"` (red) if any failures
- **Cap**: max 10 failing test names in card body
- **Actions**: Langfuse Traces link + CloudWatch Logs link
- **Status 202**: Azure Logic App returns 202 (accepted async) — not 200

### Tier 3 Execution Note

`test_strands_eval.py` has top-level `argparse.parse_args()` — **never use pytest for Tier 3**.
Always run as: `python tests/test_strands_eval.py --model us.anthropic.claude-3-5-haiku-20241022-v1:0`

---

## Part 11: Model Rules

**CRITICAL: These rules apply to all eval expert work.**

| Task | Model | Why |
|------|-------|-----|
| Running eval suite (any tier) | Haiku: `us.anthropic.claude-3-5-haiku-20241022-v1:0` | Cost control — 98 tests at ~$0.03/test |
| Diagnosing failures | Opus: `claude-opus-4-6` | Needs deep reasoning to identify root cause |
| Writing code fixes (levers 1-5) | Opus: `claude-opus-4-6` | Higher quality edits for agent prompts + code |
| Langfuse/CloudWatch analysis | Opus: `claude-opus-4-6` | Complex trace analysis |
| Re-running specific failing tests | Haiku | Even for validation after a fix |

**Rule**: Never run eval tests with Sonnet or Opus — use Haiku exclusively for test execution.

---

## Part 12: Known Failure Patterns (as of 2026-03-22)

Identified from Tier 3 run (98 tests, Haiku model).

| Test | Root Cause | Details | Fix Lever |
|------|-----------|---------|-----------|
| 43 | DATA (FIXED) | Test checked `expected_tools=["oa_intake"]` but oa-intake skill calls `search_far` directly. Fixed to `expected_tools=["search_far"]` | Fixed in test_strands_eval.py:3493 |
| 45 | DATA (FIXED) | Test checked `expected_tools=["market_intelligence"]` but skill calls `web_search` directly. Fixed to `expected_tools=["web_search"]` | Fixed in test_strands_eval.py:3655 |
| 46 | DATA (FIXED) | Test checked `expected_tools=["document_generator"]` but skill calls `create_document` directly. Fixed to `expected_tools=["create_document"]` | Fixed in test_strands_eval.py:3735 |
| 47 | DATA (FIXED) | `known_skills` set only contained subagent wrapper names; actual tools are direct. Updated to include all direct domain tool names | Fixed in test_strands_eval.py:3809 |
| 52 | DATA | Langfuse session ID `eval-test-*` not found — session not propagated to Langfuse during eval run | Lever 1 — session tagging in sdk_query() |
| 59 | BUG (FIXED) | Test called `exec_web_search({"query": "..."}, "test-tenant")` — dict instead of string. Fixed to `exec_web_search("...")` | Fixed in test_strands_eval.py:4447 |
| 60 | BUG (FIXED) | Test used `"acquisition_method": "competitive"` — not a valid method ID. Fixed to `"negotiated"` (valid for $500K contracts) | Fixed in test_strands_eval.py:4474 |

### Test 59 Fix (web_search.py)

In `server/app/tools/web_search.py`, find the `converse()` call that passes the query param.
The query argument must be a string, not a dict. Pattern:
```python
# BAD:
query_param = {"query": user_query}
# GOOD:
query_param = user_query  # or str(user_query)
```

### Test 60 Fix (compliance_matrix.py)

Add `"competitive"` as an accepted acquisition method alias. Check the accepted methods list
and either add it directly or map it to `"competitive_acquisition"` / `"full_and_open"`.

---

## Part 13: E2E Vision Judge (Screenshot-Based Testing)

### Overview

The **e2e-judge** skill provides screenshot-based E2E testing with LLM-as-judge evaluation. It runs Playwright on the EC2 devbox (inside VPC) against the deployed ALB, captures full-page screenshots at each UI step, and sends them to Claude Sonnet via Bedrock `converse()` for structured pass/fail evaluation.

**Skill**: `.claude/skills/e2e-judge/SKILL.md`
**Agent**: `.claude/agents/e2e-judge-agent.md`

### Architecture

```
EC2 devbox (VPC) -> Playwright headless Chromium
  -> Screenshot capture (PNG, SHA-256 hashed)
    -> Bedrock converse (Sonnet 4.5 vision judge)
      -> SHA-256 cache (7-day TTL)
        -> Results JSON + markdown report
          -> S3 upload -> gallery HTML
```

### Python Modules (server/tests/)

| Module | Purpose |
|--------|---------|
| `e2e_judge_orchestrator.py` | CLI entry point — wires capture + judge + report |
| `e2e_screenshot_capture.py` | Playwright screenshot utility, Cognito auth |
| `e2e_vision_judge.py` | Bedrock converse with image blocks, structured verdicts |
| `e2e_judge_cache.py` | SHA-256 file cache for judgments |
| `e2e_judge_prompts.py` | Page-specific judge prompts |
| `e2e_judge_journeys.py` | Journey definitions with `@journey` decorator |

### Available Journeys

| Journey | Steps | What it tests |
|---------|-------|---------------|
| `login` | 3 | Cognito auth flow |
| `home` | 4 | Landing page, feature cards, navigation |
| `chat` | 10 | Multi-turn conversation, streaming, agent responses |
| `documents` | 2 | Document list, templates |
| `workflows` | 4 | Acquisition packages grid, document checklist modal |
| `admin` | 6 | Dashboard, skills, templates, traces, tests, costs |
| `responsive` | 12+ | Key pages at mobile/tablet viewports |
| `acquisition_package` | 25-35 | Full UC-1 lifecycle: intake -> doc gen -> checklist -> revision -> finalize -> export |

### Running on EC2 Devbox

```bash
# SSH or SSM into the devbox (i-0390c06d166d18926)
export PLAYWRIGHT_BROWSERS_PATH=/home/ec2-user/pw-browsers
export EAGLE_TEST_EMAIL=<cognito-email>
export EAGLE_TEST_PASSWORD=<cognito-password>
cd /home/ec2-user/e2e-judge/server

# Run specific journeys
python3.12 -m tests.e2e_judge_orchestrator \
  --base-url http://internal-eaglec-front-teerfwosqs71-1457581412.us-east-1.elb.amazonaws.com \
  --journeys login,home,chat,workflows,admin \
  --output /home/ec2-user/e2e-judge/data/e2e-judge/results \
  --purge-cache

# Upload results to S3
aws s3 sync /home/ec2-user/e2e-judge/data/e2e-judge/screenshots/<run-id>/ \
  s3://eagle-eval-artifacts-695681773636-dev/e2e-judge/screenshots/<run-id>/
```

### Key Details

- **Judge model**: `us.anthropic.claude-sonnet-4-5-20250929-v1:0` (cross-region inference profile)
- **Python**: `/usr/bin/python3.12` on the devbox (NOT system python3 which is 3.9)
- **Auth**: Cognito login via `#email` and `#password` selectors, `button[type='submit']`
- **Page loads**: Use `wait_until="domcontentloaded"` (NOT `networkidle` — SSE keeps connections open)
- **Cost**: ~$0.15 for 25 screenshots, ~$0.03 for 4 screenshots (cached runs are free)
- **Cache**: SHA-256 of PNG bytes -> `data/e2e-judge/cache/{sha256}.json`, 7-day TTL
- **Deploy code**: Upload via S3 (`s3://eagle-eval-artifacts-695681773636-dev/e2e-judge-deploy/`)

### Invoke via Skill

Use `/e2e-judge` or ask Claude to "run the e2e vision judge" to invoke the skill directly.

