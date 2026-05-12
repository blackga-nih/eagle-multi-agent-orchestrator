# EAGLE-299, EAGLE-300, and EAGLE-210 Implementation Plans

Date: 2026-05-12

## Scope

This plan covers three related Jira tickets from the AIP demo-script cluster:

- `EAGLE-299`: Required documents should show `Document | Trigger | Template`, not `Required? | Notes`.
- `EAGLE-300`: Contract-type reasoning should account for the full sentence: uncertain scope, but definable service types and frequency.
- `EAGLE-210`: Under NIH context, Labor-Hour should be presented as Time & Materials, not as a separate recommendation.

## Relevant Code Paths

- Prompt/model presentation: `eagle-plugin/agents/supervisor/agent.md`
- Backend compliance/package data: `server/app/compliance_matrix.py`, `server/app/package_store.py`
- Frontend rendering: `client/components/chat-simple/tool-result-panels/compliance-result-panel.tsx`, `client/components/chat-simple/checklist-panel.tsx`
- Contract matrix source data: `eagle-plugin/data/matrix.json`, `client/components/contract-matrix/matrix-data.ts`
- Regression tests: `server/tests/test_supervisor_prompt_invariants.py`, `server/tests/test_strands_eval.py`, `server/tests/test_compliance_matrix.py`, `server/tests/test_package_context_service.py`

## Plan 1: EAGLE-299 Required Documents Contract

Goal: make `Document | Trigger | Template` a real backend/UI contract, not just prompt wording.

### Current State

`agent.md` already instructs the model to show `Trigger` and `Template`, but the source data still primarily exposes:

- `name`
- `required`
- `note`
- sometimes `template_hint`

The compliance result panel also renders required documents with a status/check column and `Citation / Notes`. The package checklist progress UI is a different surface and should keep completion checkmarks.

### Implementation Steps

1. Add canonical required-document metadata:
   - `name` or `document`
   - `required`
   - `trigger`
   - `template`
   - keep `note` and `template_hint` for backward compatibility

2. Update `server/app/compliance_matrix.py`:
   - Convert each document entry from vague `note` text into explicit `trigger` and `template`.
   - Continue filling `note` with the trigger text for older callers.
   - Continue filling `template_hint` where an exact template filename is known.

3. Use explicit mappings for common AIP/package documents:

| Document | Trigger | Template |
|---|---|---|
| Performance Work Statement (PWS) | Services requirement; outcome-based scope under FAR 37.102 / FAR 37.6 | PWS/SOW template |
| IGCE | Required for above-MPT acquisition; labor category hours and rates needed | `01.D_IGCE_for_Commercial_Organizations.xlsx` |
| Market Research Report | Above SAT; Rule of Two / small-business capability analysis | `Attachment 5-HHS Template-Market Research Report.docx` |
| Acquisition Plan | Above SAT | `1.b AP Above SAT.docx` or resolved registry template |
| Subcontracting Plan | If large-business prime and value > $900K | `HHS SubK Plan Template - updated March 2022.doc` |

4. Preserve package checklist behavior:
   - The checklist remains a baseline compliance/progress tracker.
   - Required checklist items keep completion status.
   - Valid off-checklist documents generated from chat should land in `extra[]`, not be blocked and not be silently promoted.

5. Update frontend rendering:
   - In `client/components/chat-simple/tool-result-panels/compliance-result-panel.tsx`, replace the checkmark/note explanatory table with `Document`, `Trigger`, `Template`.
   - In `client/components/chat-simple/checklist-panel.tsx`, keep completion checkmarks for package progress, but do not use them as the explanatory required-documents table.
   - Move conditional documents to a `Suggested` / `Conditional Documents` section, or render their trigger with clear `If...` wording.

6. Update prompt examples:
   - Change `D&F for T&M/LH` to `D&F for T&M`.
   - Keep the prompt aligned with the backend contract.

### Regression Coverage

- Backend test: `get_requirements(...)["documents_required"]` includes non-empty `trigger` and `template`.
- Package document test: valid off-checklist package documents can be generated and then surface in `extra[]`.
- Frontend guard: explanatory required-documents table does not render `Required?` and does render `Trigger` and `Template`.
- Prompt invariant: required-documents instructions still forbid `Required?` and still require `Trigger` / `Template`.

## Plan 2: EAGLE-300 Contract-Type Reasoning

Goal: fix AIP contract-type reasoning so Eagle does not stop at "uncertain scope" when the user also says service types and frequency are definable.

### Current State

Commit `9c65d91` added prompt guidance for FFP unit/event pricing, but the later behavioral eval focuses on `T&M only / no LH`. That protects EAGLE-210-style leakage, but it is too narrow for EAGLE-300 because the correct AIP reasoning may be FFP unit/event pricing or a hybrid.

### Desired Decision Contract

- If exact deliverables are undefined but service categories/frequency are definable, recommend FFP unit/event pricing for the definable units.
- If some demand remains inherently variable, use T&M only for that residual portion.
- Under NIH context, do not call the residual variable portion Labor-Hour.
- Do not flatten the whole acquisition to T&M solely because the prompt says "uncertain scope."

### Implementation Steps

1. Update `eagle-plugin/agents/supervisor/agent.md`:
   - Keep the existing FFP unit/event pricing guidance.
   - Add explicit reconciliation with the NIH T&M/LH rule:
     - First evaluate FFP unit/event CLINs where service types and frequencies are definable.
     - Use T&M only for residual unpredictable coaching/advisory demand if needed.
     - Never present LH under NIH context.

2. Add/strengthen required response structure for the AIP prompt:
   - Contract-type recommendation.
   - Service type breakdown table.
   - Why FFP unit/event pricing fits definable categories.
   - When T&M is still needed.
   - CO/D&F explanation if T&M is used.

3. Update `server/tests/test_strands_eval.py`:
   - Replace the current "T&M only" expectation for the AIP prompt with a broader but stricter test:
     - no LH leakage;
     - includes "types and frequency" analysis;
     - includes service type breakdown;
     - includes FFP unit/event pricing or hybrid FFP + T&M;
     - if T&M appears, explains CO D&F approval.

4. Add service breakdown checks for:
   - coaching;
   - CSAW/workshop facilitation;
   - training development/delivery;
   - Innovation Snapshot/reference materials;
   - annual readiness survey.

### Validation

Run the AIP demo prompt and verify:

- The answer does not mention LH.
- The answer does not recommend blanket T&M just because scope is uncertain.
- The answer explains the definable service-type/frequency signal.
- The answer gives a practical CLIN/service breakdown.
- T&M, if present, is residual and carries the CO/D&F explanation.

## Plan 3: EAGLE-210 Labor-Hour to T&M

Goal: under NIH context, prevent Labor-Hour from appearing as the final recommendation for this labor-services use case. Per Jira comment on 2026-05-05, NIH uses T&M terminology; when there are no materials, T&M can have materials equal to zero.

### Current State

Prompt guardrails exist in `agent.md` and static tests exist in `server/tests/test_supervisor_prompt_invariants.py`. LH also exists in FAR/KB/backend/frontend source data:

- `server/app/compliance_matrix.py`
- `client/components/contract-matrix/matrix-data.ts`
- `eagle-plugin/data/matrix.json`

That is expected. T&M and LH are related but not identical under FAR 16.601: T&M includes labor plus materials; LH is labor only. The fix should not erase LH from source truth or FAR taxonomy.

### Implementation Steps

1. Preserve LH internally:
   - Keep `lh` as a valid FAR/matrix contract type.
   - Keep `labor_hour`, `labor hour`, `labor_hours`, and `lh` aliases resolving to `lh`.
   - Normalize ambiguous `T&M/LH` payloads to `tm` where schema parsing needs a single value, because the final NIH-facing recommendation should use T&M terminology.

2. Scope the user-facing rule:
   - Do not deny that LH exists as a FAR contract type when a KB/FAR source mentions it.
   - Do not recommend LH as the final NIH/NCI contract strategy for the AIP/GSA labor-services context.
   - Translate the final recommendation to T&M terminology, with a `$0 materials` CLIN where appropriate.

3. Keep EAGLE-300 compatibility:
   - EAGLE-300 can still recommend FFP unit/event pricing or hybrid FFP + T&M.
   - EAGLE-210 must not force a blanket all-T&M answer.
   - The variable residual portion should be called T&M, not LH, when speaking in NIH/NCI practice terms.

4. Clean prompts and downstream text:
   - In `eagle-plugin/agents/supervisor/agent.md`, replace `D&F for T&M/LH` with `D&F for T&M`.
   - If specialist/KB/template content mentions LH, preserve the source meaning but translate the final recommendation into NIH/NCI T&M terminology.

### Regression Coverage

- Static prompt test: the supervisor must not force all-T&M and must use T&M only for residual variable demand.
- Backend normalization test: `Labor Hour` and `LH` remain `lh` internally.
- Prompt test: KB/FAR LH mentions are translated for final NIH/NCI recommendations rather than treated as false.
- Eval test: AIP prompt allows FFP/hybrid/T&M reasoning but forbids LH variants.

## Recommended Sequencing

1. Implement `EAGLE-210` first, or at least in the same branch as `EAGLE-300`, because EAGLE-300's correct AIP reasoning depends on not naming the residual variable work LH.
2. Implement `EAGLE-300` next by updating the AIP contract-type decision contract and the behavioral eval.
3. Implement `EAGLE-299` after that as the required-documents data/UI contract change.

## Review Questions

- Should LH remain visible in admin/FAR-reference matrices while being suppressed from NIH/NCI recommendations?
- For AIP, should the preferred recommendation be pure FFP unit/event pricing or hybrid FFP + T&M?
- Should `trigger/template` metadata eventually be shared with package checklist details, or remain limited to explanatory compliance output for now?
