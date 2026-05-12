# Handoff — Draft Implementation Plan for Intake Gate + Budget Semantics

**From**: Greg (via Claude Opus 4.7)
**Date**: 2026-04-22
**Target**: Next planning agent (e.g., `/gsd-plan-phase` or `/experts:backend:plan`)
**Output goes in**: `.claude/specs/20260422-HHMMSS-plan-intake-gate-budget-semantics-v1.md`

---

## 1. Assignment

Produce a phased implementation plan for two changes to EAGLE's compliance matrix that address three concrete failures from the April 16 EAGLE-vs-Research-Optimizer review. The design decisions are already made; your job is to break the work into atomic, verifiable tasks with validation commands.

**Do not redesign.** The decision to keep rules in `matrix.json` (data) rather than prompt text was made because the backend validator can read data but cannot read prompt text — this is load-bearing and should not be re-litigated.

---

## 2. Background — Read First

| File | What it gives you |
|------|-------------------|
| `docs/development/meeting-transcripts/20260416-eagle-output-review/20260416-180100-meeting-eagle-output-review-v1.md` | Full meeting notes. Read sections: Budget vs IGCE Reconciliation (line ~131), Contract Type (line ~99), Key Decisions 2 & 3 (lines ~159, ~163), Action Item #8 (line ~192) |
| `docs/development/meeting-transcripts/20260416-eagle-output-review/20260422-compliance-matrix-flow-v1.pdf` | Architecture flow visualization — 7 pages, shows where matrix.json sits today and where proposals plug in |
| `docs/development/meeting-transcripts/20260416-eagle-output-review/20260422-compliance-matrix-flow-static-v1.html` | Same content as PDF, source form |

---

## 3. Problems Being Solved

Three failures from the meeting, all originating between the supervisor's decision to call `create_document` and the document actually being emitted:

1. **Under-asking** — EAGLE generated a PWS before confirming training-event cadence. No intake-completeness gate.
2. **Over-asking (wrong question)** — "Your budget is $2M but IGCE is $450K, what do you want?" Ryan: *"That question should never be asked."*
3. **Ceiling ballooning** — Research Optimizer inflated IGCE to $2M when given a budget range. Model treated budget as a target instead of a not-to-exceed ceiling.

---

## 4. The Two Changes to Plan

### Change A — `intake_required_facts` (fixes problem 1)

Add a new top-level key to `eagle-plugin/data/matrix.json`:

```json
"intake_required_facts": {
  "pws":              { "required": ["scope", "pop", "place_of_performance", "event_cadence", "deliverable_format"], "blocker": true },
  "sow":              { "required": ["scope", "pop", "place_of_performance", "task_breakdown"], "blocker": true },
  "igce":             { "required": ["scope", "pop", "labor_categories_or_line_items", "budget_ceiling"], "blocker": true },
  "market_research":  { "required": ["scope", "naics_or_category", "estimated_value_range"], "blocker": true },
  "acquisition_plan": { "required": ["scope", "igce_value", "contract_type", "competition_approach"], "blocker": true },
  "ja":               { "required": ["scope", "proposed_contractor", "authority_far_6_302_x", "sole_source_rationale"], "blocker": true }
}
```

Wire it into:
- **Supervisor prompt**: new `PRE-GENERATION INTAKE GATE` section in `eagle-plugin/agents/supervisor/agent.md`, placed after the `CHECKLIST-FIRST` rule (~line 141). Reads matrix, batches missing facts into ONE clarifying question, then generates.
- **document-generator skill**: extend the Research Prerequisites table in `eagle-plugin/skills/document-generator/SKILL.md` (~line 27) with a new "Intake Facts Required" column sourced from the new matrix key.
- **oa-intake skill**: trim hardcoded Phase 2 question lists in `eagle-plugin/skills/oa-intake/SKILL.md`; point at matrix instead.
- **Backend validator**: add a pre-dispatch check in `create_document` handler (likely `server/app/tools/documents.py` — verify path) that reads `matrix.intake_required_facts[doc_type]` and returns a structured `missing_facts` error if inputs are absent from package/session context.

### Change B — `budget_semantics` (fixes problems 2 and 3)

Add a new top-level key to `matrix.json`:

```json
"budget_semantics": {
  "budget_is_ceiling": true,
  "igce_is_estimated_value": true,
  "propagation": "IGCE auto-propagates as estimated_value to AP, J&A, SSP, and downstream docs",
  "locked_after_intake": ["budget_ceiling"],
  "forbidden_behaviors": [
    "asking user to reconcile IGCE vs budget",
    "suggesting scope expansion to consume remaining budget",
    "inflating quantities/rates to reach a budget target",
    "recommending a contract value that exceeds budget_ceiling"
  ]
}
```

Wire it into:
- **Supervisor prompt**: new `BUDGET SEMANTICS RULE` section in `supervisor/agent.md`, placed near the intake gate. Forbids the reconcile question explicitly.
- **Subagent prompts with `create_document` access**: same `BUDGET SEMANTICS RULE` block must be copied into every subagent that can emit documents. Currently that's `eagle-plugin/agents/market-intelligence/agent.md` (line 63 confirms direct `create_document` + `edit_docx_document` access). Audit `_build_subagent_doc_tools()` in `server/app/strands_agentic_service.py` (~line 2477) to enumerate every subagent that inherits doc tools — any hit gets the same block. Prompt-level enforcement must reach every agent that can reach the tool.
- No backend validator needed for this change — it's a prompt-enforced rule with matrix as authoritative source. (The validator for Change A already forces matrix-read discipline.)

### Subagent Scope — Why the Backend Validator Is Load-Bearing

The supervisor prompt is not the only entry point into `create_document`. Subagents wired through `_build_subagent_doc_tools()` call it directly, skipping any rule that lives only in `supervisor/agent.md`. This is why Change A's backend validator is not optional:

| Layer | Catches | Misses |
|-------|---------|--------|
| Supervisor prompt (Change A.1) | Supervisor-initiated doc calls | Subagent direct calls |
| Subagent prompts (Change A.3/B extension) | That specific subagent's calls | Subagents added later without the block |
| **Backend validator (Change A.4)** | **All callers, universally — the chokepoint** | **Nothing** |

The backend validator reads `matrix.intake_required_facts[doc_type]` at the handler boundary and rejects any call missing required facts, regardless of which agent initiated it. Prompt rules are the fast-path (stop early, batch the clarifying question); the validator is the correctness guarantee.

---

## 5. Current Codebase Touchpoints (already verified)

| Path | Role |
|------|------|
| `eagle-plugin/data/matrix.json` | Source of truth. Loaded once at import, cached. Adding keys is zero-risk; existing tools ignore unknown keys. |
| `server/app/compliance_matrix.py` | Loads matrix.json at module import via `_load_json`. `execute_operation()` is the query entry point. |
| `server/app/tools/admin_tools.py` | `exec_query_compliance_matrix` wraps compliance_matrix module for tool dispatch. |
| `server/app/tools/legacy_dispatch.py` | Routes tool names to handlers (line 77 registers `query_compliance_matrix`). |
| `server/app/package_store.py` | `manage_package` — already matrix-aware for checklist generation. Good reference for how to read new keys. |
| `server/app/tools/documents.py` | `create_document` handler. Verify path — plan's backend validator goes here. |
| `eagle-plugin/agents/supervisor/agent.md` | Supervisor prompt. ~928 lines. New sections go after line 141 (CHECKLIST-FIRST rule). |
| `eagle-plugin/agents/market-intelligence/agent.md` | Subagent with **direct** `create_document` + `edit_docx_document` access (line 63). Bypasses supervisor prompt — needs its own INTAKE GATE + BUDGET SEMANTICS block. |
| `server/app/strands_agentic_service.py` | `_build_subagent_doc_tools()` at ~line 2477. Audit callers to enumerate every subagent that inherits doc tools — any hit needs the same prompt-level blocks. |
| `eagle-plugin/skills/oa-intake/SKILL.md` | Intake flow skill. Phase 2 (lines 78-189) has hardcoded clarifying questions. |
| `eagle-plugin/skills/document-generator/SKILL.md` | Doc templates. Research Prerequisites table is at line 27. |
| `server/tests/test_compliance_matrix.py` | Existing tests — new keys will need parallel test coverage. |
| `server/tests/test_dynamic_required_docs.py` | Existing dynamic-requirements test. Extend for intake_required_facts. |

---

## 6. Fix Matrix — Traceability

| Meeting issue | matrix.json key | Supervisor section | Backend change |
|---------------|-----------------|---------------------|----------------|
| PWS before cadence | `intake_required_facts.pws.event_cadence` | PRE-GENERATION INTAKE GATE | validator in `create_document` |
| "Budget vs IGCE reconcile" question | `budget_semantics.forbidden_behaviors[0]` | BUDGET SEMANTICS RULE | none |
| Ceiling ballooning | `budget_semantics.budget_is_ceiling` + `forbidden_behaviors[1,2]` | BUDGET SEMANTICS RULE | none |

---

## 7. Out of Scope for This Plan

The meeting surfaced additional issues that are **NOT** part of this work — do not roll them in:

- **KB sync (legacy FAR vs RFO)** — belongs to Action Item #1 (Alvi/WADA). Separate plan.
- **"Labor Hour" default removal** — tiny matrix edit; handle as a separate PR.
- **IGCE methodology narrative** — template change in document-generator, separate.
- **Rewriting Q1–Q5 test questions** — Action Item #6, Ingrid/Ryan working session.
- **Tone-down RO-style risk framing** — ongoing polish, not a coded change.

---

## 8. Phase Structure Suggestion

Recommend four phases, each independently shippable:

1. **Matrix schema** — add both new keys to `matrix.json`, write tests in `test_compliance_matrix.py` that assert key presence and shape. (Zero behavioral impact until consumers wired.)
2. **Supervisor prompt wiring** — add two new sections to `agent.md`. Verifiable via eval suite: run `test_strands_eval.py` and confirm no regressions on existing tests; add new eval tests for the intake-gate and budget-reconcile refusal behaviors.
3. **Backend validator** — add pre-dispatch check in `create_document` handler. Test with `test_tool_dispatch.py`-style unit test that constructs a missing-facts scenario and asserts the structured error.
4. **Skill file cleanup** — trim hardcoded lists in `oa-intake/SKILL.md`, extend table in `document-generator/SKILL.md`. Pure documentation/prompt work; no code tests.

Each phase should include its own Nyquist-style validation (test exists, test passes, behavior observable).

---

## 9. Validation Commands to Include in the Plan

```bash
# Level 1 — Python lint
ruff check server/app/

# Level 2 — Unit + eval (the critical one for this work)
python -m pytest server/tests/test_compliance_matrix.py -v
python -m pytest server/tests/test_dynamic_required_docs.py -v
python -m pytest server/tests/test_strands_eval.py -v
python -m pytest server/tests/test_tool_dispatch.py -v

# Matrix JSON must still parse
python -c "import json; json.load(open('eagle-plugin/data/matrix.json'))"
```

New eval tests to add:
- Intake-gate: given a package missing `event_cadence`, supervisor asks for it before calling `create_document(doc_type="pws")`.
- Budget-reconcile refusal: given a session with budget=$2M and IGCE=$450K, supervisor does NOT ask the reconcile question.
- Ceiling enforcement: given budget=$2M, supervisor does not produce an IGCE exceeding $2M.

---

## 10. Deliverable Shape

Write the plan to `.claude/specs/{YYYYMMDD}-{HHMMSS}-plan-intake-gate-budget-semantics-v1.md` with:

- **Goal statement** (one sentence)
- **Phase-by-phase task breakdown** — each task atomic, one-commit-sized
- **Per-task validation command** — how to confirm the task worked
- **Dependency graph** — which phase/task blocks which
- **Rollback procedure** per phase
- **Success criteria** mapping back to the Fix Matrix above

Do NOT include the full matrix.json key content in the plan — reference this handoff for the schema and just name the key in each task.

---

## 11. Gotchas

- `matrix.json` version field (line 2) should bump from `"2026-02-25"` to a new date when keys are added. Note the consumers in `compliance_matrix.py` that may key off version.
- The supervisor prompt already has a `DEFAULT TO ACTION` rule (line 228) and `WHEN IN DOUBT: Generate the work product` (line 244) that pull against the intake gate. The new gate section must explicitly carve out an exception — do not remove those rules.
- The `PWS vs SOW are DIFFERENT documents` rule (line 139) says "do NOT ask clarifying questions" when the user asks for PWS after a SOW exists. The intake gate should not re-introduce that specific prompt. Check that the `intake_required_facts` gate fires for *missing required facts*, not for disambiguation.
- **Subagent doc-tool reach**: `market-intelligence/agent.md:63` grants direct `create_document` access. Any INTAKE GATE or BUDGET SEMANTICS rule that lives only in `supervisor/agent.md` will not fire when this subagent generates a Market Research Report. Phase 2 (prompt wiring) must cover every subagent returned by `_build_subagent_doc_tools()`, not just the supervisor. When adding a new subagent later, doc-tool grants must be paired with the prompt blocks — add a checklist item to agent-creation docs.
- **New eval test for subagent path**: add a case where `market-intelligence` is invoked directly and confirm it respects the intake gate + budget semantics (e.g., asks for `estimated_value_range` before emitting MRR, does not propose scope that exceeds `budget_ceiling`).
- Git branch: per `memory/git-workflow.md`, use a feature branch, not direct-to-main.
