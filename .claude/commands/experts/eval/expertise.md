---
type: expert-file
parent: "[[eval/_index]]"
file-type: expertise
human_reviewed: false
tags: [expert-file, mental-model, eval, testing, eagle, aws, cloudwatch]
last_updated: 2026-02-10T00:00:00
---

# Eval Expertise (Complete Mental Model)

> **Sources**: server/tests/test_eagle_sdk_eval.py, server/app/agentic_service.py, server/eagle_skill_constants.py

---

## Part 1: Test Suite Architecture

### File Layout

```
server/tests/test_eagle_sdk_eval.py        # 28 tests, CLI entry point
server/tests/eval_aws_publisher.py         # S3 archival + CloudWatch custom metrics
server/eagle_skill_constants.py      # Embedded skill/prompt constants
server/app/agentic_service.py        # execute_tool(), AWS tool implementations
data/eval/results/                   # Per-run JSON results (run-<ts>.json, latest.json)
data/eval/videos/                    # Browser recording videos (.webm/.mp4)
```

### Test Tiers

| Tier | Tests | Type | LLM Cost | Dependencies |
|------|-------|------|----------|-------------|
| SDK Patterns | 1-6 | claude-agent-sdk query() | Yes (Bedrock) | AWS Bedrock |
| Skill Validation | 7-15 | query() with skill system_prompt | Yes (Bedrock) | eagle_skill_constants |
| AWS Tool Integration | 16-20 | execute_tool() direct | None | boto3, AWS services |
| UC Workflow Validation | 21-27 | Multi-turn workflow queries | Yes (Bedrock) | Skills, tools |
| SDK Architecture | 28 | sdk_agentic_service AgentDefinition | Yes (Bedrock) | sdk_agentic_service, SKILL_CONSTANTS |

### CLI Interface

```bash
# Run all 20 tests
python server/tests/test_eagle_sdk_eval.py --model haiku

# Run specific tests
python server/tests/test_eagle_sdk_eval.py --model haiku --tests 16,17,18,19,20

# Run with async parallelism (tests 3-20)
python server/tests/test_eagle_sdk_eval.py --model haiku --async
```

### Execution Flow

```
main()
  |-- Parse args (--model, --tests, --async)
  |-- Phase A: Sequential tests 1-2 (session create/resume, linked)
  |-- Phase B: Independent tests 3-27 (sequential or --async parallel)
  |-- Summary printout
  |-- Write data/eval/results/run-<ts>.json + latest.json
  |-- emit_to_cloudwatch() -> /eagle/test-runs (structured log events)
  |-- if _HAS_AWS_PUBLISHER:
  |     |-- publish_eval_metrics() -> EAGLE/Eval namespace (custom CW metrics)
  |     |-- archive_results_to_s3() -> s3://eagle-eval-artifacts/eval/results/
  |     |-- archive_videos_to_s3() -> s3://eagle-eval-artifacts/eval/videos/
```

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

## Part 4: AWS Tool Integration Tests (16-20)

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

## Part 5: CloudWatch Telemetry

### Log Group Structure

```
/eagle/test-runs/
  |-- run-2026-02-09T...Z/    # Per-run stream
      |-- test_result events   # One per test
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
  "run_timestamp": "2026-02-09T..."
}

// run_summary event
{
  "type": "run_summary",
  "run_timestamp": "2026-02-09T...",
  "total_tests": 20,
  "passed": 18,
  "skipped": 1,
  "failed": 1,
  "pass_rate": 90.0
}
```

### Emission Pattern

```python
# Stage 1: Structured log events (emit_to_cloudwatch)
emit_to_cloudwatch(trace_output, results)
# Non-fatal: catches all exceptions
# Creates log group + stream if needed
# Sorts events by timestamp (CloudWatch requirement)

# Stage 2: Custom metrics + S3 archival (eval_aws_publisher)
if _HAS_AWS_PUBLISHER:
    publish_eval_metrics(results, run_ts)    # ~32 metrics to EAGLE/Eval namespace
    archive_results_to_s3(trace_file, run_ts)  # JSON to s3://eagle-eval-artifacts/
    archive_videos_to_s3(video_dir, run_ts)    # .webm/.mp4 to s3://eagle-eval-artifacts/
```

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
| `TestStatus` (x27) | None | `TestName` | 1.0=pass, 0.0=fail per test |

### S3 Artifact Archival

Published by `eval_aws_publisher.archive_results_to_s3()` and `archive_videos_to_s3()`:

```
s3://eagle-eval-artifacts/
  eval/results/run-<ISO-ts>.json                # Results JSON per run
  eval/videos/<run-ts>/<test_dir>/<file>.webm   # Browser recordings
```

---

## Part 6: Registration Mappings

Every test must be registered in **8 locations** across 4 files. Missing any causes silent data loss (test runs but results don't show in dashboards or CloudWatch).

### Backend Registrations (server/tests/test_eagle_sdk_eval.py)

| # | Location | Line | Format | Purpose |
|---|----------|------|--------|---------|
| 1 | `TEST_REGISTRY` | ~2319 | `N: ("N_snake_name", test_N_snake_name)` | Dispatch: maps test ID to (result_key, function) |
| 2 | `test_names` in `emit_to_cloudwatch()` | ~2252 | `N: "N_snake_name"` | CloudWatch event `test_name` field |
| 3 | `result_key` in `main()` trace output | ~2479 | `N: "N_snake_name"` | trace_logs.json result key per test |
| 4 | Summary printout in `main()` | varies | `print()` line for test N | Terminal output after run |
| 5 | `selected_tests` default range | ~2405 | `range(1, N+1)` | Include test when `--tests` not specified |

### Frontend Registrations (3 files)

| # | File | Variable | Line | Format |
|---|------|----------|------|--------|
| 6 | `test_results_dashboard.html` | `TEST_DEFS` | ~123 | `{ id: N, name: "...", desc: "...", category: "..." }` |
| 7 | `client/app/admin/tests/page.tsx` | `TEST_NAMES` | ~28 | `'N': 'Human-Readable Name'` |
| 8 | `client/app/admin/eval/page.tsx` | `SKILL_TEST_MAP` | ~446 | `tool_key: [N]` (AWS tools only) |

### Category Tags (test_results_dashboard.html)

| Category | Tests | Description |
|----------|-------|-------------|
| `core` | 1, 2, 5 | Session management, cost tracking |
| `traces` | 3 | Frontend event type mapping |
| `agents` | 4, 8 | Subagent orchestration and tracking |
| `tools` | 6 | MCP tool access |
| `skills` | 7, 10-14 | Skill loading and validation |
| `workflow` | 9, 15 | Multi-turn and multi-skill workflows |
| `aws` | 16-20 | AWS tool integration with boto3 confirm |

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

### Readiness Panel (test_results_dashboard.html)

The readiness panel at ~line 305 shows pass/fail dots for each test. Each entry maps `results[N]?.status === 'pass'` to a human label. Must add an entry for every new test.

---

## Part 7: Standard Operating Procedure — Adding a New Test

### Pre-Flight

1. **Pick the next test ID** — check `TEST_REGISTRY` for the highest current ID, increment by 1
2. **Choose the tier** — SDK Pattern, Skill Validation, or AWS Tool Integration
3. **Choose a category** — core, traces, agents, tools, skills, workflow, or aws
4. **Name it** — snake_case for code (`N_descriptive_name`), Title Case for dashboards

### Step 1: Write the Test Function

Add before the `# ── Main` section in `server/tests/test_eagle_sdk_eval.py`:

```python
async def test_N_descriptive_name():
    """Brief description of what this test validates."""
    print(f"\n{'='*60}")
    print("Test N: Descriptive Title")
    print(f"{'='*60}")

    passed = True
    tenant_id = "test-tenant"
    session_id = "test-session-001"

    try:
        # --- Step 1: Primary operation ---
        print("\n  Step 1: [description]...")
        # ... test logic ...
        print("    -> [result summary]")

        # --- Step 2: Verification ---
        print("\n  Step 2: [description]...")
        # ... assertions ...

        # --- Cleanup (if test creates resources) ---
        try:
            # delete S3 objects, DDB items, etc.
            pass
        except Exception:
            print("    (cleanup failed, non-fatal)")

    except Exception as e:
        print(f"\n  EXCEPTION: {e}")
        import traceback; traceback.print_exc()
        passed = False

    status = "PASS" if passed else "FAIL"
    print(f"\n  Result: {status}")
    return passed
```

**Rules for the function body:**
- SDK tests (tier 1): use `query()` from claude-agent-sdk
- Skill tests (tier 2): load from `SKILL_CONSTANTS`, inject as `system_prompt`
- AWS tool tests (tier 3): call `execute_tool()` directly, confirm with boto3
- Always return `True`, `False`, or `None` (skip)
- Print step-by-step progress for debugging
- Cleanup all created resources in a try/except (non-fatal)

### Step 2: Register in Backend (4 edits in server/tests/test_eagle_sdk_eval.py)

**2a. `TEST_REGISTRY`** (~line 2319 in `_run_test()`):
```python
N: ("N_descriptive_name", test_N_descriptive_name),
```

**2b. `test_names`** (~line 2252 in `emit_to_cloudwatch()`):
```python
N: "N_descriptive_name",
```

**2c. `result_key`** (~line 2479 in `main()` trace output loop):
```python
N: "N_descriptive_name",
```

**2d. Summary printout** (in `main()`, add a print line in the appropriate tier section):
```python
print(f"  Test N  {'PASS' if results.get('N_descriptive_name') else 'FAIL':6s}  Descriptive Title")
```

**2e. `selected_tests` default range** (~line 2405) — extend to include N:
```python
selected_tests = list(range(1, N+1))
```

### Step 3: Register in Frontend (3 files)

**3a. `test_results_dashboard.html` — `TEST_DEFS`** (~line 123):
```javascript
{ id: N, name: "Descriptive Title", desc: "One-line description", category: "aws" },
```

**3b. `test_results_dashboard.html` — readiness panel** (~line 305):
```javascript
{ label: "Descriptive label", ready: results[N]?.status === 'pass' },
```

**3c. `client/app/admin/tests/page.tsx` — `TEST_NAMES`** (~line 28):
```typescript
'N': 'Descriptive Title',
```

**3d. `client/app/admin/eval/page.tsx` — `SKILL_TEST_MAP`** (~line 446, if applicable):
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
python -c "import json; d=json.load(open('trace_logs.json')); print(list(d['results'].keys()))"
```

### Step 5: Verify Dashboards

- Open `test_results_dashboard.html` in browser — test N card should appear
- Check the category filter button shows/hides it correctly
- Check readiness panel dot for test N
- If Next.js frontend is running, verify `/admin/tests` shows the test

### Checklist (copy-paste for PR descriptions)

```
- [ ] test function `test_N_name()` added
- [ ] TEST_REGISTRY entry (server/tests/test_eagle_sdk_eval.py ~2319)
- [ ] test_names entry (server/tests/test_eagle_sdk_eval.py ~2252)
- [ ] result_key entry (server/tests/test_eagle_sdk_eval.py ~2479)
- [ ] summary printout line (server/tests/test_eagle_sdk_eval.py main())
- [ ] selected_tests range updated (server/tests/test_eagle_sdk_eval.py ~2405)
- [ ] TEST_DEFS entry (test_results_dashboard.html ~123)
- [ ] readiness panel entry (test_results_dashboard.html ~305)
- [ ] TEST_NAMES entry (client/.../tests/page.tsx ~28)
- [ ] SKILL_TEST_MAP entry if applicable (client/.../eval/page.tsx ~446)
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

### Cleanup Requirement
All tests that create AWS resources MUST clean up:
- S3: `s3.delete_object()`
- DynamoDB: `table.delete_item()`
- CloudWatch: read-only tests don't need cleanup

---

## Part 9: Known Issues and Gotchas

### MCP Race Condition (Test 6)
- Windows ExceptionGroup on MCP server cleanup
- Handled with try/except for CLIConnection errors
- May return SKIP if no messages collected

### Session Resume (Test 2)
- `system_prompt` is NOT preserved across `query(resume=session_id)`
- Must re-provide system_prompt on every call
- Correct for multi-tenant: tenant context should always be explicit

### Tenant Scoping in Tests
- `_extract_tenant_id()` always returns "demo-tenant" for test sessions
- `_extract_user_id()` returns "demo-user" for non "ws-" session IDs
- Tests use session_id="test-session-001"

### Skill Loading
- Uses dict lookup from `eagle_skill_constants.SKILL_CONSTANTS`
- No filesystem dependency on nci-oa-agent
- Self-contained for test portability

### CloudWatch Emission
- Non-fatal: catches all exceptions
- Falls back to local trace_logs.json
- Events must be sorted by timestamp

---

## Learnings

### patterns_that_work
- Direct execute_tool() testing is deterministic, fast, and free
- boto3 independent confirmation prevents false positives
- Cleanup with try/except prevents test pollution
- Structured CloudWatch events enable dashboard querying
- Import-guard pattern (`try: from eval_aws_publisher import ...; _HAS_AWS_PUBLISHER = True except ImportError: _HAS_AWS_PUBLISHER = False`) makes AWS publisher zero-impact when module unavailable (discovered: 2026-02-10, component: eval_aws_publisher integration)
- Lazy-loaded boto3 clients in eval_aws_publisher avoid import-time AWS calls — clients only created on first use (discovered: 2026-02-10, component: eval_aws_publisher)
- Each publisher function is independently non-fatal — one failure doesn't block others (discovered: 2026-02-10, component: eval_aws_publisher)
- Publishing ~32 CloudWatch custom metrics in a single put_metric_data call is well under the 1000-per-call limit (discovered: 2026-02-10, component: eval_aws_publisher)
- `run_ts_file` format `%Y-%m-%dT%H-%M-%SZ` is shared between local file naming and S3 key paths for consistent cross-referencing (discovered: 2026-02-10, component: eval_aws_publisher)
- Testing `sdk_agentic_service` functions (build_skill_agents, build_supervisor_prompt) deterministically before running live sdk_query() — catches import/config issues without LLM cost (discovered: 2026-02-10, component: test_28)
- Limiting subagent skills in test (2 of 6) for cost control while still validating the delegation pattern (discovered: 2026-02-10, component: test_28)

### patterns_to_avoid
- Don't rely on LLM output for deterministic assertions
- Don't skip cleanup — leaves artifacts that confuse future runs
- Don't test CloudWatch writes in same run as reads (eventual consistency)
- Don't import eval_aws_publisher at module top-level without guard — breaks eval suite on machines without boto3 (discovered: 2026-02-10, component: eval_aws_publisher)

### common_issues
- AWS credentials not configured -> all tool tests fail
- S3 bucket "nci-documents" doesn't exist -> test 16/19 fail
- DynamoDB table "eagle" doesn't exist -> test 17 fails
- CloudWatch log group doesn't exist -> test 18/20 may still pass (get_stream returns empty)
- S3 bucket "eagle-eval-artifacts" doesn't exist -> archive_results_to_s3 and archive_videos_to_s3 print non-fatal error and return None/0 (component: eval_aws_publisher)
- CloudWatch EAGLE/Eval namespace has no data -> publish_eval_metrics prints non-fatal error, dashboard shows no data until first successful publish (component: eval_aws_publisher)

### tips
- Run tests 16-20 first when debugging AWS connectivity
- Use `--tests 16` to isolate a single test
- Check `data/eval/results/latest.json` for per-test logs after a run
- CloudWatch test 20 validates the PREVIOUS run's data
- After an eval run, check S3 archival: `aws s3 ls s3://eagle-eval-artifacts/eval/results/`
- Check custom metrics: `aws cloudwatch list-metrics --namespace "EAGLE/Eval"`
- View eval dashboard in CloudWatch console: search for `EAGLE-Eval-Dashboard`
- The publisher module lives at `server/tests/eval_aws_publisher.py` — import it from the same directory as the eval suite
- Test 28 depends on `server/app/sdk_agentic_service.py` — import via `sys.path` (server/app already in path from line 30)
- When testing AgentDefinition-based services, verify `build_skill_agents()` and `build_supervisor_prompt()` deterministically first, then run live `sdk_query()` — layered validation
- Test 28 is in the "SDK Architecture" tier — runs with `--tests 28` or as part of the full suite
