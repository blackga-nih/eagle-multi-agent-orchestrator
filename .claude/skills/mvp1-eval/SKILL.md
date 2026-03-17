---
name: mvp1-eval
description: Run the EAGLE evaluation suite — unit tests, integration tests, and live Bedrock eval tests covering supervisor routing, subagent orchestration, compliance matrix, document pipeline, and all UC use cases. Tests are tagged by MVP phase (MVP1 core, MVP2 intake optimization, MVP3 integrations).
model: sonnet
---

# EAGLE Eval Suite

Run the curated test suite validating the EAGLE acquisition package workflow end-to-end. Tests are organized by **MVP phase** so you can run only what's relevant to the current milestone.

## Source Documents & References

### Business Requirements
| Source | Path | Description |
|--------|------|-------------|
| Use Case List (Excel) | `Use Case List.xlsx` | 30 use cases across MVP1/2/3 with roles, FAR parts, thresholds, scenarios. Sheet "use case list" has the master UC table, "MVP summary" has counts by role, "Baseline questions" has 6 QA test prompts with expected agent responses |
| Sprint Update (DOCX) | `EAGLE-Sprint-Update-2026-03-16.docx` | Current sprint status — "What's Done" table, "Working for Demo" bullets, bottom line summary. Updated weekly |
| Demo Script | `EAGLE-DEMO-SCRIPT.md` | 14-step demo script with UC-to-step mapping, pre-demo checklist, talking points, and fallback plan |

### Jira Sources
| Source | Path | Description |
|--------|------|-------------|
| Jira Issues (full) | `docs/jira-issues.md` | 41 issues — 3 epics (EAGLE-3, EAGLE-20, EAGLE-22), 32 stories, 6 tasks. Team assignments, expert domains, status. Updated 2026-02-27 |
| Jira New Items (Mar 10) | `docs/jira-new-items-20260310.md` | EAGLE-42 through EAGLE-64 — completed stories (SSE migration, observability, compliance) + new EAGLE-54 epic (intake optimization) with 10 stories. Source: March 10 QA session |
| Jira Completed (early) | `jira-tickets.md` | EAGLE-001 through EAGLE-006 — early frontend bugs and stories (doc checklist, viewer, smart naming, home page) |

### Jira Epics
| Epic | Summary | MVP |
|------|---------|-----|
| EAGLE-3 | UC-1 Create an acquisition package | MVP1 |
| EAGLE-20 | Acquisition Package by Type | MVP1 |
| EAGLE-22 | Technical Configuration | MVP1 |
| EAGLE-54 | Intake Flow Optimization | MVP2 |

### Test & Eval Files
| Source | Path | Description |
|--------|------|-------------|
| Eval suite | `server/tests/test_strands_eval.py` | 42 async test functions (test_1 through test_42) — Strands Agent + compliance matrix + AWS tools + UC workflows |
| CloudWatch publisher | `server/tests/eval_aws_publisher.py` | `_TEST_NAMES` dict (42 entries), `publish_eval_metrics()`, `archive_results_to_s3()` |
| Tier 1 unit tests | `server/tests/test_compliance_matrix.py` | Compliance matrix logic — thresholds, documents, FAR lookups |
| Tier 1 unit tests | `server/tests/test_chat_kb_flow.py` | Knowledge base query flow |
| Tier 1 unit tests | `server/tests/test_canonical_package_document_flow.py` | Package-to-document routing |
| Tier 1 unit tests | `server/tests/test_document_pipeline.py` | Document generation pipeline |
| Tier 2 integration | `server/tests/test_strands_multi_agent.py` | Live Bedrock — supervisor routing to subagents |
| Tier 2 integration | `server/tests/test_strands_poc.py` | Live Bedrock — UC-02 micro purchase E2E |
| Tier 2 integration | `server/tests/test_strands_service_integration.py` | SDK query adapter tests |
| Skill config | `.claude/skills/mvp1-eval/config.json` | Multi-repo config (sm_eagle, sample-multi-tenant, eagle-multi-agent) |

### Backend Key Files
| Source | Path | Description |
|--------|------|-------------|
| Strands orchestration | `server/app/strands_agentic_service.py` | Supervisor + 7 subagent @tools, `sdk_query_streaming()`, Langfuse OTEL exporter |
| Document export | `server/app/document_export.py` | `markdown_to_docx()` + `markdown_to_pdf()` — NCI branding, DRAFT watermarks, branded tables |
| Langfuse client | `server/app/telemetry/langfuse_client.py` | `list_traces()`, `get_trace()`, `list_observations()` — Langfuse REST API for admin dashboard |
| Main routes | `server/app/main.py` | FastAPI endpoints — `/api/chat`, `/api/documents/export`, `/api/admin/traces`, etc. |
| Compliance matrix | `server/app/compliance_matrix.py` | Deterministic FAR/DFARS threshold lookup — no LLM |
| Environment | `server/.env` | AWS, Langfuse, Cognito, S3, model config |

### Frontend Key Files
| Source | Path | Description |
|--------|------|-------------|
| Workflows/Packages | `client/app/workflows/page.tsx` | Package cards with pathway badges, status, progress tracking |
| Langfuse traces | `client/app/admin/traces/page.tsx` | Traces dashboard — summary cards, env filter, detail panel with observations |
| Admin dashboard | `client/app/admin/page.tsx` | System health, stats, active sessions |
| Chat UI | `client/components/chat-simple/simple-chat-interface.tsx` | Primary chat interface with activity panel |

### External Systems
| System | URL / Identifier | Purpose |
|--------|-----------------|---------|
| Jira | `tracker.nci.nih.gov` / Project: EAGLE | Issue tracking — epics, stories, bugs |
| Langfuse | `https://us.cloud.langfuse.com/project/cmmtw4vjq026kad07iu2y1nuc` | OTEL trace viewer, cost dashboard, session analysis |
| AWS Console (S3) | `eagle-documents-695681773636-dev` | Document storage bucket (us-east-1) |
| GitHub | `CBIIT/sm_eagle` | Source repo, PRs, CI/CD |
| CloudWatch | `/eagle/test-runs` log group | Eval metrics and test result archival |

## MVP Phase Definitions

| Phase | Scope | Jira Epic | Demo Target |
|-------|-------|-----------|-------------|
| **MVP1** | Core infrastructure — sessions, streaming, Strands SDK, supervisor routing, specialist agents, document gen, compliance, observability, cost tracking, basic UC flows | EAGLE-3 (UC-1), EAGLE-22 (Tech Config) | POC demo: simple + complex acquisition walkthrough |
| **MVP2** | Intake optimization — baseline questions (EAGLE-59), verbosity reduction (EAGLE-58), deferred doc gen (EAGLE-62), vehicle recommendations (EAGLE-56), staged checklist (EAGLE-55), form cards (EAGLE-61), template routing (EAGLE-60), micro purchase fix (EAGLE-57) | EAGLE-54 (Intake Flow Optimization) | QA-validated intake flow matching legacy Eagle quality |
| **MVP3** | Enterprise integrations — SharePoint (EAGLE-11), NVision vehicle detection, ServiceNow, CO feedback loop, historical analysis, crisis workflows, 800+ concurrent users | Future epics | Production-scale multi-tenant deployment |

## Step 0: Load Repo Config

Resolve all environment-specific values from the config file before running anything.

```bash
# Determine repo name (used as config key)
REPO_NAME=$(basename $(git rev-parse --show-toplevel))
echo "Repo: $REPO_NAME"
```

Then read `.claude/skills/mvp1-eval/config.json` and look up the entry matching `$REPO_NAME`.
Extract these values for use in all subsequent steps:

| Variable | Config key | Fallback |
|----------|-----------|---------|
| `AWS_PROFILE` | `aws_profile` | `eagle` |
| `S3_BUCKET` | `s3_bucket` | `eagle-documents-dev` |
| `SERVER_DIR` | `server_dir` | `server` |
| `ENV_FILE` | `env_file` | `server/.env` |
| `LANGFUSE_HOST` | `langfuse_host` | `https://us.cloud.langfuse.com` |
| `TIER1_TESTS` | `tier1_tests[]` | see defaults below |
| `TIER2_TESTS` | `tier2_tests[]` | see defaults below |
| `TIER3_TEST` | `tier3_test` | `tests/test_strands_eval.py` |

If `$REPO_NAME` is not found in the config, print a warning and use fallback values. Do **not** abort — the skill should work in unknown repos with sensible defaults.

> **Adding a new repo**: Copy the `_template` block in `config.json`, rename the key to your repo basename, and fill in `aws_account` + `s3_bucket`. Everything else is usually identical.

## Pre-flight

1. Ensure AWS credentials are active (using `AWS_PROFILE` from config):
```bash
aws sts get-caller-identity --profile $AWS_PROFILE 2>/dev/null || echo "AWS_PROFILE=$AWS_PROFILE not authenticated — run: AWS_PROFILE=$AWS_PROFILE aws sso login"
```

2. Set working directory (using `SERVER_DIR` from config):
```bash
cd $SERVER_DIR
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
| `test_supervisor_routes_to_intake` | test_strands_multi_agent.py | Supervisor -> OA Intake subagent routing |
| `test_supervisor_routes_to_legal` | test_strands_multi_agent.py | Supervisor -> Legal Counsel subagent routing |
| `test_supervisor_routes_to_market` | test_strands_multi_agent.py | Supervisor -> Market Intelligence subagent routing |
| `test_strands_uc02_micro_purchase` | test_strands_poc.py | UC-02 micro purchase end-to-end |
| `test_sdk_query_adapter_messages` | test_strands_service_integration.py | SDK query adapter message format |
| `test_sdk_query_single_skill_adapter` | test_strands_service_integration.py | Single skill adapter routing |

**Expected**: 6 tests, ~4 min total. All pass with valid Bedrock credentials.

### Tier 3: Full Eval Suite (needs AWS/Bedrock, ~30 min)

The comprehensive 42-test eval suite. **Only run if user requests `--full` or Tier 1+2 pass.**

```bash
AWS_PROFILE=eagle python -m pytest tests/test_strands_eval.py -v --tb=short -x 2>&1
```

**Note**: `test_strands_eval.py` has a top-level `argparse.parse_args()` that crashes pytest collection. If collection fails, run with:
```bash
AWS_PROFILE=eagle python tests/test_strands_eval.py 2>&1
```

**Tests (42 implemented):**

| # | Test | Category | MVP | Jira | Excel UC |
|---|------|----------|-----|------|----------|
| 1 | session_creation | Session mgmt | MVP1 | EAGLE-44 | -- |
| 2 | session_resume | Session mgmt | MVP1 | EAGLE-21 | -- |
| 3 | trace_observation | Observability | MVP1 | EAGLE-44 | -- |
| 4 | subagent_orchestration | Routing | MVP1 | EAGLE-51 | -- |
| 5 | cost_tracking | Billing | MVP1 | EAGLE-37 | -- |
| 6 | tier_gated_tools | Access control | MVP1 | EAGLE-22 | -- |
| 7 | skill_loading | Plugin system | MVP1 | EAGLE-51 | -- |
| 8 | subagent_tool_tracking | Observability | MVP1 | EAGLE-51 | -- |
| 9 | oa_intake_workflow | Specialist | MVP1 | EAGLE-5 | -- |
| 10 | legal_counsel_skill | Specialist | MVP1 | EAGLE-9 | -- |
| 11 | market_intelligence_skill | Specialist | MVP1 | EAGLE-32 | -- |
| 12 | tech_review_skill | Specialist | MVP1 | EAGLE-32 | -- |
| 13 | public_interest_skill | Specialist | MVP1 | EAGLE-32 | -- |
| 14 | document_generator_skill | Specialist | MVP1 | EAGLE-8 | -- |
| 15 | supervisor_multi_skill_chain | Orchestration | MVP1 | EAGLE-51 | -- |
| 16 | s3_document_ops | AWS tools | MVP1 | EAGLE-8 | -- |
| 17 | dynamodb_intake_ops | AWS tools | MVP1 | EAGLE-5 | -- |
| 18 | cloudwatch_logs_ops | AWS tools | MVP1 | EAGLE-44 | -- |
| 19 | document_generation | Document pipeline | MVP1 | EAGLE-8 | -- |
| 20 | cloudwatch_e2e_verification | AWS tools | MVP1 | EAGLE-44 | -- |
| 21 | uc02_micro_purchase | Use case | MVP1 | EAGLE-15 | UC-2.1 |
| 22 | uc03_option_exercise | Use case | **MVP2** | -- | -- |
| 23 | uc04_contract_modification | Use case | **MVP2** | EAGLE-17 | -- |
| 24 | uc05_co_package_review | Use case | **MVP2** | EAGLE-9 | -- |
| 25 | uc07_contract_closeout | Use case | **MVP3** | -- | -- |
| 26 | uc08_shutdown_notification | Use case | **MVP3** | -- | -- |
| 27 | uc09_score_consolidation | Use case | **MVP3** | -- | -- |
| 28 | strands_skill_tool_orchestration | Plugin system | MVP1 | EAGLE-51 | -- |
| 29 | compliance_matrix_query_requirements | FAR/DFARS | MVP1 | EAGLE-9 | -- |
| 30 | compliance_matrix_search_far | FAR/DFARS | MVP1 | EAGLE-9 | -- |
| 31 | compliance_matrix_vehicle_suggestion | FAR/DFARS | MVP1 | EAGLE-9 | -- |
| 32 | admin_manager_skill | Admin | MVP1 | EAGLE-22 | -- |
| 33 | workspace_store | Workspace | MVP1 | EAGLE-22 | -- |
| 34 | store_crud_functions | Data layer | MVP1 | EAGLE-22 | -- |
| 35 | uc01_new_acquisition_package | Use case | MVP1 | EAGLE-16 | UC-1 |
| 36 | uc02_gsa_schedule | Use case | MVP1 | EAGLE-18 | UC-2 |
| 37 | uc03_sole_source | Use case | MVP1 | EAGLE-27 | UC-3 |
| 38 | uc04_competitive_range | Use case | MVP1 | -- | UC-4 |
| 39 | uc10_igce_development | Use case | MVP1 | EAGLE-29 | UC-10 |
| 40 | uc13_small_business_setaside | Use case | MVP1 | -- | UC-13 |
| 41 | uc16_tech_to_contract_language | Use case | MVP1 | -- | UC-16 |
| 42 | uc29_e2e_acquisition | Use case | MVP1 | -- | UC-29 |

### Planned MVP2 Tests (not yet implemented)

These tests will validate the EAGLE-54 intake optimization epic. Add them as the features land.

| # | Test (planned) | Category | MVP | Jira |
|---|----------------|----------|-----|------|
| 43 | baseline_intake_questions | Intake flow | MVP2 | EAGLE-59 |
| 44 | response_verbosity_reduction | Output quality | MVP2 | EAGLE-58 |
| 45 | deferred_document_generation | Doc pipeline | MVP2 | EAGLE-62 |
| 46 | ranked_vehicle_recommendations | Routing | MVP2 | EAGLE-56 |
| 47 | staged_checklist_progression | UI/backend | MVP2 | EAGLE-55 |
| 48 | micro_purchase_correct_docs | Doc pipeline | MVP2 | EAGLE-57 |
| 49 | template_routing_per_acq_type | Doc pipeline | MVP2 | EAGLE-60 |
| 50 | quick_form_cards_intake | UI/backend | MVP2 | EAGLE-61 |

### Planned MVP3 Tests (future)

| # | Test (planned) | Category | MVP | Jira |
|---|----------------|----------|-----|------|
| 51 | sharepoint_package_store | Integration | MVP3 | EAGLE-11 |
| 52 | co_session_handoff | Workflow | MVP3 | EAGLE-36 |
| 53 | concurrent_users_load | Scale | MVP3 | -- |

## Arguments

- `--full` — Run all 3 tiers including the full 42-test eval suite
- `--tier N` — Run only tier N (1, 2, or 3)
- `--mvp N` — Run only tests tagged as MVP N (1, 2, or 3). Currently all implemented tests are MVP1; MVP2 tests will land as EAGLE-54 features ship
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
with open(ENV_FILE) as f:  # ENV_FILE from config (e.g. "server/.env")
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
   where bucket = `$S3_BUCKET` (from config, e.g. `eagle-documents-695681773636-dev`)

### 4c. Produce the Report

Output the final report in this format:

```
## EAGLE Eval Report

### Test Results

| Tier | Tests | Passed | Failed | Skipped | Time |
|------|-------|--------|--------|---------|------|
| 1 - Unit | N | N | N | N | Ns |
| 2 - Integration | 6 | N | N | N | Ns |
| 3 - Full Eval | 42 | N | N | N | Ns |
| **Total** | **N** | **N** | **N** | **N** | **Ns** |

### Coverage by MVP Phase

| MVP | Tests | Passed | Failed | Coverage |
|-----|-------|--------|--------|----------|
| MVP1 | 36 | N | N | Core infra, specialists, 9 Excel UCs, observability |
| MVP2 | 3+0/8 | N | N | 3 existing (uc03/04/05) + 8 planned (EAGLE-54) |
| MVP3 | 3+0/3 | N | N | 3 existing (uc07/08/09) + 3 planned |

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
