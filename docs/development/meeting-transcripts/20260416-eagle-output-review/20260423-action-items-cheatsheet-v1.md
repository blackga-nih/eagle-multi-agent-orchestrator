# 4/16 Output Review — Action Items Cheat Sheet

_Updated 2026-04-23. Source: [meeting v4](20260416-180100-meeting-eagle-output-review-v4.docx)_

## Status legend

| | |
|---|---|
| ✅ **Validated** | Observed working on the deployed system or in source of truth |
| 🛠 **Patched** | Code shipped, behavior not yet verified in use |
| ⛔ **Outstanding** | No work yet |
| 🔄 **Ongoing** | Stylistic guardrail, not a one-time task |

---

## Items

| # | Item | Status | Evidence |
|---|------|:---:|---|
| 1 | KB sync — RFO only, legacy FAR stripped | ✅ | S3 bucket verified 2026-04-22: `eagle-documents-695681773636-dev/eagle-knowledge-base/approved/` is RFO-only |
| 1b | Q4/Q5 regression root-cause (KB correct but still wrong answer) | ⛔ | Need to re-run against current KB and trace why |
| 2 | IGCE/budget reconcile bug | 🛠 | PR #150 — `matrix.budget_semantics` + supervisor forbids reconcile Q verbatim |
| 3 | FFP hybrid + task-area decomposition | 🛠 | PR #149 — NIH/NCI T&M institutional override in supervisor; task-area decomp portion still pending |
| 4 | Remove Labor Hour default | ✅ | PR #149 — supervisor prompt: "do NOT default to Labor-Hour" (visible in source) |
| 5 | IGCE methodology / budget narrative | 🛠 | PR #149 — template gained §2.4 Rate Derivation + §2.5 Budget Narrative; needs observed output to validate |
| 6 | Rewrite Q1–Q5 in natural CO voice | ⛔ | Pending Ingrid/Ryan working session |
| 7 | Supervisor: teaching vs acquisition mode | ⛔ | No commits |
| 8 | Early jump to doc generation | 🛠 | PR #150 — PRE-GENERATION INTAKE GATE in supervisor + market-intelligence prompts |
| 9 | Re-run Q4 & Q5 after KB sync | ⛔ | Unblocked by #1; not yet re-run |
| 10 | Fri 4/17 follow-up meeting | ✅ | Happened; `20260417-kb-agent-prompt-comparison.md` filed |
| 11 | Tone down RO-style risk framing | 🔄 | Stylistic — no discrete milestone |

---

## Roll-up

**2 validated · 4 patched · 4 outstanding · 1 ongoing · 1 meeting-done**

---

## Next validation queue

Things to verify now that deploys are unblocked (PRs #150, #151, #152):

1. **#9** — Re-run Q4 + Q5 live. Fastest validation, unblocked, low cost.
2. **#2 + #8** — Open a fresh package where a PWS/IGCE is generated, confirm:
   - EAGLE asks for required intake facts (cadence, place_of_performance, etc.) in ONE batched question before generating
   - When budget > IGCE, EAGLE does NOT ask the reconcile question
3. **#5** — Inspect a generated IGCE from the deployed app, confirm §2.4 + §2.5 present
4. **#3** — Ask EAGLE for a services acquisition on GSA Schedule, confirm T&M recommended (not LH) and FFP carve-outs offered
5. **#1b** — If #9 shows Q4/Q5 still wrong despite RFO KB, capture the agent trace and diagnose whether it's prompt drift, retrieval ranking, or a cited-citation-verification gap
