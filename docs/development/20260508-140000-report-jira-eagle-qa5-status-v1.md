# EAGLE QA5 Status — 2026-05-08

**Epic**: EAGLE-291 "Eagle QA5"
**Children**: 21 stories, all currently `To Do` in Jira
**Method**: cross-referenced each issue against recent commits, this session's PRs (#205–#216), and active tests.

---

## Top-line

| | |
|---|---|
| Total QA5 stories | 21 |
| **Addressed by recent work** | **5** |
| Partially addressed | 2 |
| Outstanding | 14 |

---

## ✅ Addressed (5)

| Key | Summary | Closing work |
|---|---|---|
| **EAGLE-292** | Generated document has different content as specified template (UC3 — $280K) | **PR #213 + #214** — Tier-3 section-drift validator. `_template_provenance.section_drift` now reports `{total_sections, filled_sections, missing_sections[], completeness_pct, is_complete}` on every `create_document` response (both package-mode and workspace-mode). Supervisor can self-correct. |
| **EAGLE-293** | UC3-$280K didn't generate Acquisition Plan | **PR #211** unlocked orphan doc_types in `get_create_document_types()`; **PR #206** fixed the `"$280"` currency-string parsing that was rejecting AI-extracted estimated_value. Both gates that blocked this UC3 flow are gone. Verified live: 6 successful post-deploy `create_document` calls including QASP. |
| **EAGLE-302** | Generated AP section headers differ from specified template | Same as EAGLE-292 — section_drift validator surfaces exactly which sections are missing/renamed. |
| **EAGLE-308** | Source summary repeated after follow-up | **PR #196** — `fix(chat): sources_summary chip renders last with visual separation`. Rendered once, after the prompt. |
| **EAGLE-316** | Error occurred when clicking on attach button | **PR #216 (this session)** — SSE watchdog. The button was grayed because runtime stayed stuck in `status: 'streaming'` after a stalled SSE stream (no log entries on either side, matching the symptom). 60s no-event watchdog now aborts the stream and dispatches `generation/error`, releasing the upload button. |

---

## 🟡 Partially addressed (2)

| Key | Summary | What's done / what's left |
|---|---|---|
| **EAGLE-300** | Contract type reasoning is partial vs RO's reasoning | **PR #207** strengthened the supervisor prompt for T&M vs LH (related), with a regression test that exercises the AIP scenario. EAGLE-300 specifically calls out that the supervisor only considered "uncertain in scope" but ignored "we can define types and frequency" — that's a prompt-reasoning depth issue, not the LH gap. The LH guard is in place; the broader reasoning improvement still pending. |
| **EAGLE-309** | Previous chat interrupted after clicking new chat | The SSE session-crossover spec exists at `.claude/specs/20260506-150700-pbi-sse-session-crossover-fix-v1.md`. **PR #216 watchdog** closes the orphan-streaming-state half (any abandoned stream auto-clears in 60s). The deliberate reducer-level guards described in the spec — preventing session-A's `onLog` and `onStateUpdate` callbacks from leaking into session-B's panels — are still pending implementation. |

---

## ❌ Outstanding (14)

### Document quality / format (5)

| Key | Summary |
|---|---|
| **EAGLE-294** | UC3-$280K downloaded SOW + Market Research are in MD format instead of PDF/Word |
| **EAGLE-298** | Subcontracting plan wording not as clear/logical as RO |
| **EAGLE-301** | Inaccurate NAICS code (Eagle: 541612, RO: 541611) |
| **EAGLE-303** | Markdown table cells have stray `**` around text (rendering bug) |
| **EAGLE-310** | Downloaded filename not per KB usage guide |

### Use-case-specific gaps (3)

| Key | Summary |
|---|---|
| **EAGLE-311** | UC13: $450K IT services set-aside — Eagle missing FAR 19.104 GAO/SBA citations + CIO-SP3 SB vehicle recommendation |
| **EAGLE-312** | UC10: IGCE — Excel has no projected numbers; download is Excel-only, no Word counterpart |
| **EAGLE-313** | UC4: Competitive range — Eagle adds unnecessary RFO; FAR 15.2 quote less detailed than RO's FAR 15.204-1 |

### Supervisor prompt / output quality (3)

| Key | Summary |
|---|---|
| **EAGLE-296** | Source summary should exclude template files (currently bundles them as input) |
| **EAGLE-297** | Used legacy vehicle name "GSA PSS" instead of new "GSA MAS" — supervisor prompt update needed |
| **EAGLE-299** | Required-documents section: "Required" flag is redundant with section header; Notes column adds noise |

### UI (3)

| Key | Summary |
|---|---|
| **EAGLE-295** | Add "Think cube" to display Eagle's reasoning process after input files pulled |
| **EAGLE-307** | Text got cut off by Web search cube |
| **EAGLE-317** | Banner updates: rename to "Enhanced Acquisition Guidance and Learning Engine"; remove Eagle icon mid-screen; add username right side |

---

## Cross-reference: this session's PRs

| PR | Closes / Advances | Note |
|---|---|---|
| #196 (earlier) | EAGLE-308 | Sources summary chip ordering |
| #206 | EAGLE-293 (partial) | `$280` parsing unblocks the IGCE that gates UC3 doc-gen |
| #207 | EAGLE-300 (partial) | Stronger LH/T&M supervisor rule |
| #211 | EAGLE-293 | Orphan doc_type unlock — UC3 docs now generate |
| #213 | EAGLE-292, EAGLE-302 | Section-drift validator |
| #214 | EAGLE-292, EAGLE-302 | Drift surfacing on package-mode response (the actual UC3 path) |
| #216 | EAGLE-316, EAGLE-309 (partial) | SSE watchdog — unsticks attach button + clears orphan streams |

---

## Recommended next moves

1. **Verify & close 5 in Jira** (EAGLE-292, 293, 302, 308, 316). Each has a concrete closing PR.
2. **Update partial pair** (EAGLE-300, 309) with current state — mark "in progress, partial" with notes pointing at this session's PRs.
3. **Group the 14 outstanding** into 4 mini-batches:
   - **Doc quality batch** (5): EAGLE-294/298/301/303/310 — needs export pipeline + KB content fixes
   - **UC-specific batch** (3): EAGLE-311/312/313 — supervisor reasoning + KB gaps
   - **Supervisor prompt batch** (3): EAGLE-296/297/299 — pure prompt edits, fast
   - **UI batch** (3): EAGLE-295/307/317 — frontend polish

The supervisor-prompt batch (EAGLE-296/297/299) is the cheapest wins — small prompt edits with regression-test patterns already established this session.
