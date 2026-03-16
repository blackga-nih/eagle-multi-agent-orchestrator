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

At the end, produce a summary table:

```
## MVP1 Eval Results

| Tier | Tests | Passed | Failed | Skipped | Time |
|------|-------|--------|--------|---------|------|
| 1 - Unit | N | N | N | N | Ns |
| 2 - Integration | 6 | N | N | N | Ns |
| 3 - Full Eval | 37 | N | N | N | Ns |
| **Total** | **N** | **N** | **N** | **N** | **Ns** |
```
