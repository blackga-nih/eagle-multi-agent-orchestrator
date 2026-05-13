# EAGLE Jira Status Report — 2026-05-08

**Source**: `https://tracker.nci.nih.gov` project `EAGLE`, 319 total issues.
**Method**: pulled all issues via REST; cross-referenced each open issue against `git log --grep EAGLE-` and `git grep EAGLE-` across `server/`, `client/`, and `tests/`. Strict signal = explicit `EAGLE-N` reference in a commit message. Weak signal = file-only reference. Excludes 67 nightly-triage auto-tickets (separate cleanup).

---

## Top-line

| Bucket | Count |
|---|---|
| **Total in EAGLE project** | 319 |
| Nightly-triage auto-tickets (filtered out) | 67 |
| **In scope (non-nightly)** | **252** |
| ↳ Closed in Jira (`Done` / `Cancelled`) | 85 |
| ↳ **In Progress** | 7 |
| ↳ Open + commit explicitly references it (likely-done, Jira hygiene gap) | 13 |
| ↳ Open + only test/spec file references it (weak signal) | 4 |
| ↳ **Outstanding** (no code/commit evidence) | **150** |

---

## In Progress (7)

| Key | Summary |
|---|---|
| EAGLE-38 | Define Git Branching Strategy and PR Workflow |
| EAGLE-39 | Audit and Standardize Repository Folder Structure |
| EAGLE-40 | Review and Harden .gitignore for Multi-Tenant Repo |
| EAGLE-41 | Implement Git Hooks for Code Quality Gates |
| EAGLE-44 | Implement session persistence for Strands agents using custom DynamoDB SessionMa… |
| EAGLE-48 | Replace sync `Agent()` call with `stream_async()` for real-time SSE token streaming |
| EAGLE-78 | Use knowledge base as the only source unless external lookup is required |

**Note**: EAGLE-38 through EAGLE-48 all have closing commits (`f80e3d2`, `60c2950`, `c9d8563`) — they're effectively done in code. Only the Jira status hasn't been advanced. See "Likely-done" section below.

---

## Likely-Done (commit explicitly references issue, but Jira still open) — 13

These should be closed in Jira after a quick verification.

| Key | Status | Closing commit | Summary |
|---|---|---|---|
| **EAGLE-32** | To Do | `f80e3d2` | Risk-Trigger-Based Specialist Agent Routing |
| **EAGLE-37** | To Do | `f80e3d2` | Per-Acquisition Token Cost Tracking and Budget Guardrails |
| **EAGLE-38** | In Progress | `f80e3d2` | Define Git Branching Strategy and PR Workflow |
| **EAGLE-39** | In Progress | `f80e3d2` | Audit and Standardize Repository Folder Structure |
| **EAGLE-40** | In Progress | `f80e3d2` | Review and Harden .gitignore for Multi-Tenant Repo |
| **EAGLE-41** | In Progress | `f80e3d2` | Implement Git Hooks for Code Quality Gates |
| **EAGLE-44** | In Progress | `60c2950` | Strands DynamoDB SessionManager |
| **EAGLE-48** | In Progress | `c9d8563` | Strands `stream_async()` SSE streaming |
| EAGLE-72 | To Do | `2b0fc04` | Q2 KB search — GAO B-302358 |
| EAGLE-73 | To Do | `2b0fc04` | Q3 KB search — Bona Fide Needs |
| EAGLE-74 | To Do | `1bb4c46` | Q4 KB search — fair-opportunity exceptions |
| EAGLE-76 | To Do | `4391ff2` | Q5 KB search — SBIR protest debriefing |
| EAGLE-254 | To Do | `9b313e3` | research tool latency variance + retrieval drift |

---

## Outstanding (150) — by theme

### Theme breakdown

| Cluster | Count | Notes |
|---|---|---|
| **User feedback** (auto-created) | 52 | 38 general, 7 praise, 5 bug, 2 suggestion |
| Document generation | 13 | SOW/IGCE/J&A/etc. ergonomics + edge cases |
| Use cases | 7 | UC-3 sole source, UC-9 data rights, UC-10 IGCE complex, etc. |
| Knowledge base | 5 | New content + retrieval improvements |
| Intake flow | 3 | Optimization items from QA session 2026-03-10 |
| Admin / UI | 3 | Header centering, package-panel rendering, modal polish |
| Auth | 2 | |
| Compliance | 2 | |
| Eval / test | 1 | |
| Observability | 1 | |

### Outstanding by issue type

| Type | Count |
|---|---|
| Story | 75 |
| Task | 61 |
| Epic | 12 |
| **Bug** | **2** |

### Outstanding bugs (priority)

| Key | Summary |
|---|---|
| **EAGLE-57** | Fix Micro Purchase Document Output |
| **EAGLE-60** | Fix Document Template Routing |

Note: EAGLE-60 (template routing) intersects with PR #211 / #214 from this session — those PRs unlocked QASP/SB Review/Section 889 doc-types and surfaced template provenance, which is the "template routing" foundation. Likely partially addressed; needs verification.

### Outstanding epics (12)

| Key | Summary |
|---|---|
| EAGLE-3 | UC-1 Create an acquisition package |
| EAGLE-20 | Acquisition Package by Type |
| EAGLE-22 | Technical Configuration |
| EAGLE-51 | Strands Agents SDK Migration & Stabilization |
| EAGLE-54 | Intake Flow Optimization (QA Session 2026-03-10) |
| EAGLE-66 | Eagle MVP 1 |
| EAGLE-67 | Eagle MVP 2 |
| EAGLE-75 | EAGLE QA 1 |
| EAGLE-205 | Eagle QA 2 |
| EAGLE-255 | Eagle QA 3 |
| EAGLE-271 | Eagle QA 4 |
| EAGLE-291 | Eagle QA 5 |

The 5 "Eagle QA N" epics likely contain the 5 weekly QA-session followups; some of their child stories are in the outstanding 150.

---

## What this session has shipped (cross-reference)

13 PRs merged today (2026-05-08). None of them carried explicit `EAGLE-N` tags in commit messages, so they don't appear in the "Likely-Done" bucket above. Linkage table:

| PR | Closes Jira-side |
|---|---|
| #205 path bugs | Triage #1, #4 (nightly cluster — separate cleanup) |
| #206 data-validation + flakes | Triage #6, #7, #8 (nightly) |
| #207 LH prompt + tests | Likely intersects EAGLE-78 ("KB as source of truth") prompt-discipline work |
| #208 lint fix (E402) | Internal |
| #209 teams_notifier test refactor | Internal |
| #210 soft S3_BUCKET check | Internal |
| #211 doc-gen orphan unlock + template_id | Likely closes/advances **EAGLE-60** "Fix Document Template Routing" |
| #212 qasp smoke scenario | Internal |
| #213 Tier-3 section-drift validator | Adjacent to EAGLE-60 |
| #214 package-mode provenance fix | Adjacent to EAGLE-60 |
| #215 matrix consistency | Internal/infra |
| #216 SSE watchdog (upload-button fix) | No matching Jira; new defensive layer |

**Recommendation**: tag future PRs with `EAGLE-N` in the commit message so the strong-evidence classifier picks them up automatically.

---

## Tests in place — coverage map

What's actively tested (from `server/tests/` and `client/tests/`):

| Surface | Tests | Status |
|---|---|---|
| **Doc-generation orphan unlock** | `test_ai_document_schema.py::test_get_create_document_types_includes_compliance_matrix_orphans` | ✅ Active |
| **Section-drift validator** | `test_doc_gen_section_drift.py` (4 cases + source-text guard) | ✅ Active |
| **Estimated-value parsing + Decimal** | `test_triage_pr3.py::TestEstimatedValueCoercion` (9), `TestDynamoSafeCoercion` (7) | ✅ Active |
| **Haiku ranker JSON salvage** | `test_triage_pr3.py::TestRankingJsonSalvage` (5) | ✅ Active |
| **Teams notifier per-call AsyncClient** | `test_teams_notifier.py` (full rewrite + 3 invariant guards in `test_triage_pr3.py`) | ✅ Active |
| **Supervisor LH prompt invariant** | `test_supervisor_prompt_invariants.py` (6 cases) | ✅ Active |
| **AIP behavioral LH guard** | `test_strands_eval.py::test_143_aip_lh_exclusion` | ✅ Active (eval suite) |
| **5 Jira-QA Q1–Q5 evals** | `test_strands_eval.py::test_138`–`142` (EAGLE-70..76) | ✅ Active |
| **Compliance matrix** | `test_compliance_matrix.py` + `kb_matrix_analysis.py` | ✅ Active (PR #215 made script tolerate ties) |
| **Frontend Playwright E2E** | `client/tests/` (Playwright + e2e-judge skill) | ✅ Active |
| **Post-deploy smoke** | `server/tests/post_deploy_smoke.py` (8 scenarios incl. new `qasp_orphan_unlock`) | ✅ Active |

---

## Recommendations

1. **Quick win: close 13 likely-done in Jira**. They're ID'd in this report with the closing commit. ~15 min of Jira clicks.
2. **Tag future PRs with `EAGLE-N`** in commit messages so this report auto-updates.
3. **Triage the 52 feedback items** — 5 marked `bug` are highest priority. Most of the 38 `general` + 7 `praise` are probably auto-archive candidates.
4. **Verify EAGLE-60 status** against PR #211/#214 — likely closable.
5. **Audit the 12 outstanding epics** — many appear to be milestone containers (MVP 1, MVP 2, QA 1–5) whose child stories drive the real work.

---

## Secondary task — nightly triage cleanup

67 issues with summary `[Triage] Nightly Fix Plan — {env} — {date}`. All auto-created. Cleanup pending — see status update on that workstream.
