# Eval Rewrite Plan: Real AWS Wiring + Requirements Matrix Coverage

**Date**: 2026-02-25T16:58:00
**Type**: Eval plan — two work streams: (A) rewire tests 16–20 to SDK path,
(B) derive new tests from the requirements matrix
**Status**: Plan (not yet implemented)
**Precursors**:
- `.claude/specs/20260222-224042-plan-eval-sdk-migration-v1.md` (existing eval gap analysis)
- `.claude/specs/20260225-164422-plan-codebase-cleanup-v1.md` (agentic_service.py preservation decision)
- `contract-requirements-matrix.html` (acquisition scenario decision engine)

---

## 1. Problem Statement

### Tests 16–20: Wrong Layer

Tests 16–20 call `execute_tool()` from `agentic_service.py` directly — no LLM,
no SDK, no skill subagent. They validate that the boto3 wrapper functions work.
That is useful infrastructure validation, but it tells you nothing about whether
the **production path** (`sdk_query → supervisor → skill subagent`) can actually
perform real AWS operations. It is possible to have 28/28 tests pass and have a
production deployment where no document ever reaches S3.

### Tool Gap in SDK Path

The new SDK path gives skill subagents only file-system tools (`Read`, `Glob`,
`Grep`, `Bash`). The `_exec_s3_document_ops()`, `_exec_dynamodb_intake()`,
`_exec_create_document()` etc. implementations in `agentic_service.py` are never
called by the SDK path. The skill subagents produce text but cannot persist to
S3 or DynamoDB without a tool bridge.

### Requirements Matrix Not Covered

`contract-requirements-matrix.html` encodes the full NCI acquisition logic as a
decision engine — 9 acquisition methods, 8 contract types, 13 dollar thresholds,
4 flags (IT, SB, R&D, HS). It defines exactly what documents are **required** for
any given scenario. None of this decision logic is tested by the current eval suite.
The tests cover skill *responses* (does the agent mention FAR citations?) but not
*correctness* against the authoritative requirements matrix.

---

## 2. What We Are NOT Changing

Per `.claude/specs/20260222-223657-plan-backend-sdk-wiring-v1.md`:
- `agentic_service.py` is **preserved** — `execute_tool()` + all `_exec_*` handlers stay
- Tests 16–20 are **kept** as infrastructure validation (fast, free, deterministic)
- They are renamed/reclassified but not deleted

---

## 3. Work Stream A — Bridge EAGLE Business Tools into the SDK Path

### 3.1 The Problem

Skill subagents have `allowed_tools=["Read", "Glob", "Grep"]`. They cannot call
S3, DynamoDB, or CloudWatch. `ClaudeAgentOptions` supports custom tools via MCP
servers. The fix is to expose the EAGLE business tool handlers as a local MCP
server that subagents can call.

### 3.2 Solution: `server/app/eagle_tools_mcp.py`

Create a new module that wraps the existing `_exec_*` functions from
`agentic_service.py` as an MCP server. The MCP server is started in-process
and passed to `ClaudeAgentOptions.mcp_servers`.

**New file**: `server/app/eagle_tools_mcp.py`

```python
"""
EAGLE Business Tools MCP Server

Exposes the execute_tool() dispatcher from agentic_service.py as a local
MCP server so that SDK skill subagents can call S3, DynamoDB, CloudWatch,
and document generation tools.

Tools exposed:
  - s3_document_ops       (read/write/list S3 documents)
  - dynamodb_intake       (create/read/update/list intake records)
  - cloudwatch_logs       (search/read CloudWatch log streams)
  - create_document       (generate SOW/IGCE/AP/J&A etc. and save to S3)
  - get_intake_status     (check intake package completeness)
  - intake_workflow       (advance workflow stages)
  - search_far            (search FAR/DFARS database)
"""
```

**Wire into `sdk_agentic_service.py`**:

```python
# sdk_agentic_service.py — add to sdk_query()
options = ClaudeAgentOptions(
    ...
    mcp_servers=[create_eagle_mcp_server(tenant_id=tenant_id, session_id=session_id)],
    agents=agents,
)
```

Skill subagents that list `eagle_tools` in their `AgentDefinition.tools` will
then have access to the EAGLE business tool suite.

### 3.3 Update Tier Tool Gates

Extend `TIER_TOOLS` to include the new MCP-backed tools:

```python
TIER_TOOLS = {
    "basic":    [],
    "advanced": ["Read", "Glob", "Grep", "s3_document_ops", "create_document"],
    "premium":  ["Read", "Glob", "Grep", "Bash", "s3_document_ops",
                 "dynamodb_intake", "cloudwatch_logs", "create_document",
                 "get_intake_status", "intake_workflow", "search_far"],
}
```

---

## 4. Work Stream A — Rewrite Tests 16–20

Once the MCP bridge exists, the tests can be rewritten to exercise the full
production path. The rewrite follows a two-layer pattern:

```
Layer 1 (kept, renamed): execute_tool() direct — AWS infra up/reachable
Layer 2 (new, tests 34–38): sdk_query() → skill subagent → MCP tool → AWS
```

### Tests 34–38: SDK Path AWS Integration

**Test 34 — `sdk_s3_intake_document`**
- Prompt: `"Process an intake for a $2M IT services contract. Generate and save an SOW to S3."`
- Skill invoked: `document-generator` via supervisor
- Assertion: boto3 `head_object` confirms an SOW key exists in `eagle/{tenant}/{user}/` prefix
- Validates: full SDK path + MCP bridge + S3 write

**Test 35 — `sdk_dynamodb_intake_record`**
- Prompt: `"Start a new intake package for a CT scanner acquisition at NCI."`
- Skill invoked: `oa-intake` via supervisor
- Assertion: boto3 `get_item` confirms an intake record exists in DynamoDB with `PK=INTAKE#{session_id}`
- Validates: full SDK path + MCP bridge + DynamoDB write

**Test 36 — `sdk_far_search_result`**
- Prompt: `"What FAR clauses apply to a sole source IT services contract over $1M?"`
- Skill invoked: `knowledge-retrieval` or `legal-counsel` via supervisor
- Assertion: response contains correct FAR part numbers (6.302, 52.207, 52.212)
- cross-validates against `eagle-plugin/data/far-database.json`
- Validates: FAR search tool reachable via MCP, results factually correct

**Test 37 — `sdk_document_generation_compliance`**
- Prompt: `"Generate a J&A for a $2.5M sole source award to BioResearch Labs for proprietary reagents."`
- Skill invoked: `document-generator` via supervisor (with `legal-counsel` consulted)
- Assertion: document text includes FAR 6.302-1 citation, authority statement, SPE-level approval note
- Validates: document generation skill + legal compliance knowledge

**Test 38 — `sdk_cloudwatch_audit_trail`**
- Prompt: `"Retrieve the last 5 log entries for this session's intake work."`
- Skill invoked: `oa-intake` or supervisor directly
- Assertion: boto3 `describe_log_streams` confirms a log entry for this session_id
- Validates: audit trail written to CloudWatch during SDK path execution

---

## 5. Work Stream B — Requirements Matrix → Eval Tests

### 5.1 Five Canonical Scenarios (from Matrix Presets)

The matrix has 5 presets that represent the most common NCI acquisition patterns:

| Preset | Method | Type | Value | Flags | Required Docs |
|--------|--------|------|-------|-------|---------------|
| `micro` | Micro-Purchase | FFP | $8K | — | PR only; no SOW/IGCE/AP |
| `simple-product` | SAP | FFP | $150K | SB | PR, SOW, IGCE, MR, HHS-653 |
| `it-services` | IDIQ Task Order | T&M | $2M | IT, Svc | PR, SOW, IGCE, AP, D&F, QASP, Section 508, IT Security Cert, SubK |
| `rd-contract` | Negotiated | CPFF | $8M | R&D, HS, Svc | PR, SOW, IGCE, MR, AP, D&F, SSP, QASP, Human Subjects, 15% fee cap |
| `large-sole` | Sole Source / J&A | FFP | $25M | IT, Svc | PR, SOW, IGCE, AP (HCA), J&A (SPE), SubK, Section 508, IT Cert, HHS-653, SSP |

### 5.2 New Tests 29–33: Requirements Correctness

Each test asks EAGLE to determine what's required for the scenario, then asserts
against the ground truth from the matrix.

**Test 29 — `matrix_micro_purchase`**
- Input: `"I need to buy office supplies for $8,000. What acquisition documents are required?"`
- Skill: `oa-intake`
- Assert PRESENT: Purchase Request, micro-purchase classification
- Assert ABSENT: SOW, IGCE, Acquisition Plan, J&A (not required at $8K)
- Assert FAR citation: `13.2`
- Pass threshold: 4/5 assertions correct

**Test 30 — `matrix_sap_small_business`**
- Input: `"We need a $150,000 supply purchase set aside for small business. What documents do we need?"`
- Skill: `oa-intake` + `market-intelligence`
- Assert PRESENT: SOW/SON, IGCE, Market Research (documented), HHS-653 SB Review
- Assert ABSENT: Acquisition Plan (below $350K SAT), J&A (no sole source)
- Assert: SB set-aside routing identified
- Pass threshold: 4/5

**Test 31 — `matrix_it_services_idiq`**
- Input: `"We're issuing a $2M T&M IDIQ task order for IT services. What's the full compliance package?"`
- Skill: `oa-intake` + `legal-counsel` + `document-generator`
- Assert PRESENT: SOW, IGCE, AP, D&F (T&M justification), QASP, Section 508 ICT eval, IT Security & Privacy cert, SubK plan (>$750K non-SB)
- Assert: D&F cites FAR 16.601 (T&M least preferred)
- Assert: Section 508 required (IT flag + >$15K)
- Pass threshold: 5/8

**Test 32 — `matrix_rd_cpff`**
- Input: `"We're awarding a $8M CPFF R&D contract with human subjects research. What does NCI require?"`
- Skill: `legal-counsel` + `oa-intake`
- Assert PRESENT: AP, D&F, SSP, QASP, Human Subjects Provisions (HHSAR 370.3), CPFF fee cap 15% (FAR 16.304)
- Assert: CPFF requires adequate contractor accounting system (FAR 16.301)
- Assert: HCA approval level for AP at $8M
- Pass threshold: 4/6

**Test 33 — `matrix_large_sole_source`**
- Input: `"We need a $25M sole source IT services contract. This requires SPE-level approval. Walk me through everything."`
- Skill: `legal-counsel` + `oa-intake` + `market-intelligence` + `document-generator`
- Assert PRESENT: J&A citing FAR 6.302 (SPE-level approval), Acquisition Plan (HCA), SSP, SubK plan, Section 508, IT Security cert
- Assert: $25M triggers SPE J&A approval threshold ($20M+)
- Assert: Sole source protest risk flagged
- Assert: Market Research required to justify sole source
- Pass threshold: 5/8

---

## 6. Test Registration Requirements

All new tests (29–38) must be registered following the existing pattern in
`test_eagle_sdk_eval.py`:

1. Add `async def test_N_name()` function before the `# ── Main` section
2. Register in `TEST_REGISTRY` dict
3. Register in `test_names` list
4. Register in `result_key` mapping
5. Register in summary printout block
6. Update `selected_tests = list(range(1, 39))`
7. Register in all 3 frontend result files (eval dashboard, test results page, admin eval page)

---

## 7. Test Classification Reclassification

Rename test groups in the registry for clarity:

| Tests | Old Label | New Label |
|-------|-----------|-----------|
| 16–20 | AWS Tool Integration | **Layer 1: AWS Infrastructure** (direct `execute_tool`) |
| 29–33 | (new) | **Layer 2: Requirements Matrix** (sdk_query + knowledge correctness) |
| 34–38 | (new) | **Layer 3: SDK Path AWS Integration** (sdk_query + real AWS via MCP bridge) |

---

## 8. Implementation Order

Execute in this order — each phase is independently testable:

```
Phase 1 (no AWS changes needed):
  → Write tests 29-33 (requirements matrix, text-only assertions)
  → Run: just eval-quick 29,30,31,32,33
  → Expected: 3+/5 indicator pass on each

Phase 2 (requires eagle_tools_mcp.py):
  → Write eagle_tools_mcp.py
  → Wire into sdk_agentic_service.py
  → Run: just eval-aws (tests 16-20 still pass — no regression)
  → Write tests 34-38 (SDK path AWS validation)
  → Run: just eval-quick 34,35,36,37,38

Phase 3 (cleanup):
  → Rename tests 16-20 as Layer 1 in registry
  → Update eval dashboard with new group labels
  → Run: just eval (all 38 tests)
```

---

## 9. Validation Commands

```bash
# Phase 1 gate
just eval-quick 29,30,31,32,33
# Expected: all PASS (3+/5 indicators each)

# Phase 2 gate — no regression
just eval-aws
# Expected: tests 16-20 still PASS (MCP bridge doesn't break execute_tool)

# Phase 2 gate — new AWS path
just eval-quick 34,35,36,37,38
# Expected: all PASS; boto3 confirmations green

# Full suite
just eval
# Expected: 38/38 pass (or consistent baseline)

# CloudWatch coverage check
just cloudwatch-eval-summary
# Expected: pass_rate ≥ 90%, all 3 layers represented in run_summary
```

---

## 10. Coverage Summary After Implementation

| Dimension | Current (28 tests) | After (38 tests) |
|---|---|---|
| SDK path tested | Test 28 only | Tests 28–38 |
| Real AWS via sdk_query | None | Tests 34–38 |
| Requirements matrix correctness | None | Tests 29–33 |
| Acquisition method coverage | Partial (UC scenarios) | All 5 canonical presets |
| Compliance threshold coverage | None | $8K / $150K / $2M / $8M / $25M |
| Layer 1 AWS infra | Tests 16–20 | Tests 16–20 (renamed, unchanged) |
| Agent skill coverage | 6 skills | All 7 skills + supervisor routing |
