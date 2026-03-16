---
name: mvp1-eval
description: Run the MVP1 acquisition workflow evaluation suite — unit tests, integration tests, and live Bedrock eval tests covering supervisor routing, subagent orchestration, compliance matrix, document pipeline, and all UC use cases.
model: sonnet
---

# MVP1 Eval Suite

Run a curated test suite validating the MVP1 acquisition package workflow end-to-end.

## Pre-flight

1. Ensure AWS credentials are active:
```bash
aws sts get-caller-identity --profile eagle 2>/dev/null || echo "AWS_PROFILE=eagle not authenticated — run: AWS_PROFILE=eagle aws sso login"
```

2. Set working directory:
```bash
cd server/
```

## Test Tiers

The suite is organized in 3 tiers, run sequentially. Stop and report if a tier has failures before proceeding to the next.

### Tier 1: Unit Tests (fast, no AWS needed)

These validate compliance matrix logic, document pipeline, KB flow, and canonical package routing.

```bash
python -m pytest tests/test_compliance_matrix.py tests/test_chat_kb_flow.py tests/test_canonical_package_document_flow.py tests/test_document_pipeline.py -v --tb=short 2>&1
```

**Expected**: ~60+ tests, all pass. Report count and any failures.

### Tier 2: Integration Tests (needs AWS/Bedrock)

These hit live Bedrock models via Strands SDK.

```bash
AWS_PROFILE=eagle python -m pytest tests/test_strands_multi_agent.py tests/test_strands_poc.py tests/test_strands_service_integration.py -v --tb=short -x 2>&1
```

**Tests:**
| Test | File | What it validates |
|------|------|-------------------|
| `test_supervisor_routes_to_intake` | test_strands_multi_agent.py | Supervisor → OA Intake subagent routing |
| `test_supervisor_routes_to_legal` | test_strands_multi_agent.py | Supervisor → Legal Counsel subagent routing |
| `test_supervisor_routes_to_market` | test_strands_multi_agent.py | Supervisor → Market Intelligence subagent routing |
| `test_strands_uc02_micro_purchase` | test_strands_poc.py | UC-02 micro purchase end-to-end |
| `test_sdk_query_adapter_messages` | test_strands_service_integration.py | SDK query adapter message format |
| `test_sdk_query_single_skill_adapter` | test_strands_service_integration.py | Single skill adapter routing |

**Expected**: 6 tests, ~4 min total. All pass with valid Bedrock credentials.

### Tier 3: Full Eval Suite (needs AWS/Bedrock, ~30 min)

The comprehensive 37-test eval suite. **Only run if user requests `--full` or Tier 1+2 pass.**

```bash
AWS_PROFILE=eagle python -m pytest tests/test_strands_eval.py -v --tb=short -x 2>&1
```

**Note**: `test_strands_eval.py` has a top-level `argparse.parse_args()` that crashes pytest collection. If collection fails, run with:
```bash
AWS_PROFILE=eagle python tests/test_strands_eval.py 2>&1
```

**Tests (37 total):**

| # | Test | Category |
|---|------|----------|
| 1 | session_creation | Session mgmt |
| 2 | session_resume | Session mgmt |
| 3 | trace_observation | Observability |
| 4 | subagent_orchestration | Routing |
| 5 | cost_tracking | Billing |
| 6 | tier_gated_tools | Access control |
| 7 | skill_loading | Plugin system |
| 8 | subagent_tool_tracking | Observability |
| 9 | oa_intake_workflow | Specialist |
| 10 | legal_counsel_skill | Specialist |
| 11 | market_intelligence_skill | Specialist |
| 12 | tech_review_skill | Specialist |
| 13 | public_interest_skill | Specialist |
| 14 | document_generator_skill | Specialist |
| 15 | supervisor_multi_skill_chain | Orchestration |
| 16 | s3_document_ops | AWS tools |
| 17 | dynamodb_intake_ops | AWS tools |
| 18 | cloudwatch_logs_ops | AWS tools |
| 19 | document_generation | Document pipeline |
| 20 | cloudwatch_e2e_verification | AWS tools |
| 21-27 | uc02-uc09 | Use case workflows |
| 28 | strands_skill_tool_orchestration | Plugin system |
| 29-31 | compliance_matrix_* | FAR/DFARS |
| 32 | admin_manager_skill | Admin |
| 33 | workspace_store | Workspace |
| 34 | store_crud_functions | Data layer |
| 35 | uc01_new_acquisition_package | Use case |
| 36 | langfuse_trace_story | Observability |
| 37 | cloudwatch_tool_completed_events | Telemetry |

## Arguments

- `--full` — Run all 3 tiers including the full 37-test eval suite
- `--tier N` — Run only tier N (1, 2, or 3)
- `--reauth` — Run `AWS_PROFILE=eagle aws sso login` before tests
- (default) — Run Tier 1 + Tier 2 only

## Reporting

After each tier, report:
- Pass/fail count
- Failing test names with short error summary
- Wall-clock time
- Score (if eval tests report scoring)

---

## Phase 4: Langfuse Trace Report

After Tier 2+ tests complete (any tier that hits live Bedrock), query Langfuse for traces generated during the run. The Langfuse env vars are in `server/.env`:

```
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://us.cloud.langfuse.com  (default)
```

### 4a. Collect Traces

Load env vars from `server/.env`, then query recent traces (last 30 min window covers the test run):

```python
import base64, json, os, urllib.request
from datetime import datetime, timedelta, timezone

# Load from server/.env
env = {}
with open("server/.env") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()

pk = env["LANGFUSE_PUBLIC_KEY"]
sk = env["LANGFUSE_SECRET_KEY"]
host = env.get("LANGFUSE_HOST", "https://us.cloud.langfuse.com")
auth = base64.b64encode(f"{pk}:{sk}".encode()).decode()

def lf_get(path):
    req = urllib.request.Request(f"{host}{path}", headers={"Authorization": f"Basic {auth}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())

traces = lf_get("/api/public/traces?limit=20")["data"]
```

### 4b. Per-Trace Analysis

For each trace from the test run, fetch observations and extract:

1. **Trace ID** and Langfuse URL (`{host}/trace/{trace_id}`)
2. **Session ID** — links to the test that created it
3. **Tool call chain** — ordered list of every TOOL observation name
4. **Tool success/failure** — check each TOOL output for `"error"` keys
5. **Subagent invocations** — AGENT observations nested under TOOL spans
6. **Token usage** — sum `promptTokens` + `completionTokens` from GENERATION observations
7. **Documents created** — any TOOL output containing `s3_key`
8. **S3 resource URLs** — if `s3_key` found, construct:
   `https://s3.console.aws.amazon.com/s3/object/{bucket}?prefix={s3_key}`
   where bucket = `eagle-documents-695681773636-dev` (from env `S3_BUCKET`)

### 4c. Produce the Report

Output the final report in this format:

```
## MVP1 Eval Report

### Test Results

| Tier | Tests | Passed | Failed | Skipped | Time |
|------|-------|--------|--------|---------|------|
| 1 - Unit | N | N | N | N | Ns |
| 2 - Integration | 6 | N | N | N | Ns |
| 3 - Full Eval | 37 | N | N | N | Ns |
| **Total** | **N** | **N** | **N** | **N** | **Ns** |

### Agent Trace Summary

| # | Session | Tools | Subagents | Tokens (in/out) | Errors | Docs | Langfuse |
|---|---------|-------|-----------|-----------------|--------|------|----------|
| 1 | {session_id_short} | tool1, tool2, ... | legal_counsel | 150K/3K | 1 | 0 | [View]({url}) |
| 2 | ... | ... | ... | ... | ... | ... | [View]({url}) |

**Total traces**: N | **Total tokens**: N in / N out | **Est. cost**: $N.NN

### Tool Call Breakdown

| Tool | Calls | Success | Errors | Avg Tokens |
|------|-------|---------|--------|------------|
| legal_counsel | N | N | N | N |
| search_far | N | N | N | N |
| web_search | N | N | N | N |
| create_document | N | N | N | N |
| dynamodb_intake | N | N | N | N |
| s3_document_ops | N | N | N | N |
| ... | ... | ... | ... | ... |

### Documents Created

| Doc Type | S3 Key | Trace | AWS Console |
|----------|--------|-------|-------------|
| sow | eagle/tenant/.../sow_20260316_... | [View]({langfuse_url}) | [S3]({s3_console_url}) |
| (none if no documents created) |

### Errors & Warnings

- **{tool_name}** in trace {trace_id_short}: {error_message_preview}
  [View in Langfuse]({langfuse_url})

### Langfuse Dashboard

- Project: {host}/project (open to see all sessions, traces, cost dashboard)
- Recent sessions: {host}/sessions
```

### 4d. Report Rules

- Always include Langfuse URLs as clickable links — these are the "drill down" for every row
- If a tool had an error but the agent recovered (used fallback tools), note it as **recovered** not **failed**
- Group traces by test name when possible (match session_id to test output)
- If no Langfuse credentials are configured, skip Phase 4 with: "Langfuse not configured — set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY in server/.env for trace reporting"
- S3 console URLs use region `us-east-1` and bucket from `S3_BUCKET` env var or default `eagle-documents-695681773636-dev`
