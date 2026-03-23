# Plan: Intake Vehicle Recommendation + Dynamic Forms (v2)

**Date**: 2026-03-10
**Jira**: EAGLE-55 (Pizza Tracker), EAGLE-56 (Vehicle Recommendations), EAGLE-59 (Baseline Questions), EAGLE-61 (Form Cards)
**Branch**: `feat/intake-vehicle-forms`
**Supersedes**: v1 (removed SSE pipeline complexity per user feedback)

---

## Problem

Ryan's March 10 QA session exposed three gaps vs legacy Eagle:

1. **Vehicle recommendations are single-path** — EAGLE defaults to Part 15 open market even when GSA/NITAAC is better. Legacy Eagle shows a scored ranking with pros/cons.
2. **Intake questions are free-text back-and-forth** — Legacy Eagle uses structured form inputs for the 4-6 baseline questions.
3. **No contract decision matrix integration** — `docs/contract-requirements-matrix.html` has the full scoring engine (13 FAR 16.104 factors, weighted per contract type, decision tree) but it's a standalone HTML file. None of this logic feeds into the AI's responses.

---

## Key Design Constraint: No SSE Pipeline Changes

Forms are **purely frontend**. No new SSE event types, no stream protocol changes, no new hooks in `use-agent-stream.ts`.

- Form submit = regular chat message (JSON payload stringified)
- Backend fast-paths "Thanks for your submission." (same pattern as greeting fast-path)
- Card locks after submit (greyed out, "Submitted" badge)

---

## Form Card UX Spec

Every question has three elements:
1. **Radio buttons** — toggle on/off (clicking selected radio deselects it)
2. **Text field** — always present below the radios
3. **Notes box** — one general free-text area at the bottom of the card

```
┌─────────────────────────────────────────────────────┐
│  Quick Intake Questions                              │
│                                                      │
│  1. Is this new, follow-on, or recompete?            │
│     ○ New acquisition                                │
│     ○ Follow-on to existing contract                 │
│     ○ Recompete                                      │
│     [________________________________]               │
│                                                      │
│  2. Do you have baseline documents?                  │
│     ○ Yes — I can upload them                        │
│     ○ No — starting from scratch                     │
│     ○ Some but not all                               │
│     [________________________________]               │
│                                                      │
│  3. What is your role?                               │
│     ○ Requestor      ○ Purchase card holder          │
│     ○ COR            ○ Contracting Officer           │
│     [________________________________]               │
│                                                      │
│  4. Budget range                                     │
│     ○ Under $15K   ○ $15K–$350K   ○ $350K–$2.5M     │
│     ○ Over $2.5M   ○ Not sure                        │
│     [________________________________]               │
│                                                      │
│  5. IT systems or services involved?                 │
│     ○ Yes    ○ No                                    │
│     [________________________________]               │
│                                                      │
│  6. Timeline constraints?                            │
│     [________________________________]               │
│                                                      │
│  ┌───────────────────────────────────────────────┐   │
│  │ Additional notes...                           │   │
│  │                                               │   │
│  └───────────────────────────────────────────────┘   │
│                                                      │
│              [ Submit Intake Form ]                   │
└─────────────────────────────────────────────────────┘
```

After submit → card greys out, button replaced with "Submitted" badge. No more clicks.

---

## What We Have (Reference)

### Contract Requirements Matrix (`docs/contract-requirements-matrix.html`)
- `METHODS[]` — 10 acquisition methods
- `TYPES[]` — 11 contract types with risk scores and fee caps
- `THRESHOLDS[]` — 14 dollar thresholds ($15K through $150M)
- `DOC_TEMPLATES{}` — 20 document templates with sections and FAR refs
- `SELECTOR_FACTORS[]` + `FACTOR_WEIGHTS{}` — 13-factor scoring matrix
- `DECISION_TREE{}` — step-by-step guided tree (8 questions → 8 terminal types)
- `getRequirements()` → docs, thresholds, compliance, competition, timeline, risk, warnings
- `computeTypeScores()` → ranked contract types with reasons

### Existing Dead Code (`client/components/chat/`)
- `inline-equipment-form.tsx` — hardcoded CT scanner form. **Not wired to current chat.**
- `inline-funding-form.tsx` — hardcoded funding form. **Not wired to current chat.**

---

## Implementation

### Phase 1: Backend — Matrix Tool + Fast-Path

**Create**: `server/app/tools/contract_matrix.py`
- Port JS → Python: `METHODS`, `TYPES`, `THRESHOLDS`, `DOC_TEMPLATES`, `SELECTOR_FACTORS`, `FACTOR_WEIGHTS`
- Port `getRequirements()` → `get_requirements(state)`
- Port `computeTypeScores()` → `compute_type_scores(factor_answers)`
- **New**: `score_methods()` — rank acquisition methods (GSA/NITAAC/open market)
- Expose as Strands `@tool`: `query_contract_matrix(dollar_value, method, contract_type, is_it, ...)`

**Edit**: `server/app/strands_agentic_service.py`
- Add `_INTAKE_FORM_RE` regex to detect JSON intake payloads (next to `_TRIVIAL_RE`)
- Fast-path response: "Thanks for your submission."
- Register `query_contract_matrix` in agent tools list

### Phase 2: Frontend — Form Card

**Create**: `client/components/chat-simple/intake-form-card.tsx`
- Props: `onSubmit(payload)`, `disabled`
- State: `answers: Record<string, { radio: string | null; text: string }>`, `notes: string`, `submitted: boolean`
- Radio toggle: controlled state, onClick toggles (not standard HTML radio)
- Submit: builds `{ form_type: "baseline_intake", answers: {...}, notes }` → `onSubmit(payload)` → `setSubmitted(true)`

**Edit**: `client/components/chat-simple/simple-chat-interface.tsx`
- State: `showIntakeForm`, `intakeFormSubmitted`
- "New Intake" quick action → `setShowIntakeForm(true)`
- Render `<IntakeFormCard>` below messages when showing
- On submit: `sendMessage(JSON.stringify(payload))` + lock card

**Edit**: `client/components/chat-simple/simple-quick-actions.tsx`
- "New Intake" triggers form display instead of canned text

### Phase 3: Supervisor Prompt

**Edit**: `eagle-plugin/agents/supervisor/agent.md`
- Add vehicle recommendation workflow (call `query_contract_matrix`, present ranked alternatives)
- Add intake form handling (parse JSON, don't re-ask answered questions)

---

## Files Changed

| File | Action |
|------|--------|
| `server/app/tools/contract_matrix.py` | **Create** |
| `server/app/strands_agentic_service.py` | Edit |
| `client/components/chat-simple/intake-form-card.tsx` | **Create** |
| `client/components/chat-simple/simple-chat-interface.tsx` | Edit |
| `client/components/chat-simple/simple-quick-actions.tsx` | Edit |
| `eagle-plugin/agents/supervisor/agent.md` | Edit |

**NOT changed**: `stream_protocol.py`, `streaming_routes.py`, `use-agent-stream.ts`, `types/stream.ts`

---

## Verification

```bash
ruff check server/app/tools/contract_matrix.py
python -m pytest tests/test_contract_matrix.py -v
cd client && node_modules/.bin/tsc --noEmit

# Manual: New Intake → fill form → submit → "Thanks" → vehicle recs
```

---

*Generated: 2026-03-10*
