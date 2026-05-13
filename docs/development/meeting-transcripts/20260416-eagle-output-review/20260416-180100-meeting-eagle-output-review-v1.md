# Eagle Output Review — Meeting Notes

**Date**: April 16, 2026
**Time**: 6:01 PM — 7:19 PM (1h 17m 42s)
**Format**: Meeting Notes
**Type**: QA Review / EAGLE vs Research Optimizer (RO) Output Comparison

---

## Executive Summary

Ingrid (QA) walked Ryan (SME/COR) through a side-by-side comparison of EAGLE vs Research Optimizer (RO) across five Q&A test items (Q1–Q5) plus a full acquisition-package generation scenario sourced from Ryan's HHS demo script. RO outperformed EAGLE on two items — an SBIR protest question (legal framing) and a FAR 16 fair-opportunity question (knowledge-base sync). EAGLE matched or exceeded RO on the remaining three Q&A items, the Acquisition Plan (used correct template), and the IGCE (RO was too high due to FFP/LH hybrid ballooning to budget ceiling). Two concrete root causes surfaced: a legacy-FAR vs RFO bucket sync issue, and a budget-vs-IGCE reconciliation bug in the intake flow. Follow-up meeting scheduled Friday 4/17 at 2 PM.

---

## Attendees

| Name | Org | Role |
|------|-----|------|
| Hash, Ryan (NIH/NCI) [E] | NCI | Subject Matter Expert / Contracting Officer |
| Li, Jitong (NIH/NCI) [C] | EAGLE | QA Engineer (Ingrid) |
| Valisetty, Srichaitra (NIH/NCI) [C] | EAGLE | Developer (WADA) |
| Hoque, Mohammed (NIH/NCI) [C] | EAGLE | Developer (Alvi) |
| Liang, Shan (NIH/NCI) [E] | EAGLE | Engineer (Chen) |
| Black, Gregory (NIH/NCI) [C] | EAGLE | Dev Lead (joined ~38:37) |

---

## Agenda

1. Q5 — SBIR protest / FAR 33 comparison
2. Q4 — Fair opportunity exceptions / FAR 16.505
3. Q3 — Cerebral vs non-cerebral appropriation
4. Q2 — GAO holding B-302358 on IDIQ minimums
5. Q1 — Simplified acquisition thresholds / FAC 2025-06
6. End-to-end demo script — PWS, IGCE, AP generation
7. Skill feature demo (Greg)
8. Next steps

---

## Question-by-Question Results

### Q5 — SBIR protest / FAR 33 (EAGLE wrong)

| System | Framing | Verdict |
|--------|---------|---------|
| EAGLE | SBIR governed by FAR Part 15 | **Incorrect** |
| RO | SBIR uses "other competitive procedures" under FAR 6.102(d); cites GAO case; timeliness = 10-day rule from knowledge of basis, not debriefing | **Correct** |

Ryan: *"That's a completely correct answer from RO. I'm starting with RO on this one."* EAGLE also surfaced an unrelated "filing timeline" document that neither matched RO nor supported the answer.

### Q4 — Fair opportunity exceptions (knowledge-base sync bug)

| System | Citation | Verdict |
|--------|----------|---------|
| EAGLE | FAR 16.505(b)(2) | **Stale / legacy FAR** |
| RO | FAR 16.507-6 (RFO — FAR Overhaul 2025) | **Correct** |

Root cause: FAR 16.505 under the new RFO is now "Solicitation provisions and contract clauses" — not fair-opportunity exceptions. Ryan recently replaced legacy FAR with RFO in the source material. EAGLE's knowledge base is out of sync — either legacy FAR is still present, or the RFO update hadn't propagated when Ingrid ran the test last week. Alvi confirmed the KB was updated to the new material, but possibly after the test run.

Ryan: *"A big selling point of the system — change it in the back end and everybody has instant compliance. If people are still using old FAR docs, they're pulling the wrong stuff."*

### Q3 — Cerebral vs non-cerebral appropriation (tie / acceptable)

Both pulled the same three documents in nearly the same order (Georgia Redbook, Eagle Proof financial advisor, appropriations). EAGLE additionally invoked the financial agent at the end. Conclusions substantially identical. Ryan: *"Yes, it appropriately identified this is not a FAR rule."*

Observation: EAGLE always pulls the supervisor agent first — that's the system instruction and is expected behavior.

### Q2 — GAO holding B-302358 / IDIQ minimums (stylistic difference, both acceptable)

Both located the same case documents. Difference was tone:
- **EAGLE**: legal-analyst framing — applies the law, discusses clauses, technical
- **RO**: operational CO framing — explanatory, teaching tone

Ryan: *"You asked a legal question and got a legal answer. I don't fault yours. They complement each other. I call it acceptable and move on."*

### Q1 — Simplified acquisition thresholds / FAC 2025-06 (tie / unremarkable)

Both answered correctly; EAGLE cited FAR 2.101, 13.2, Part 6 explicitly; RO mentioned 13/14/15 without citation. Ryan: *"Unremarkable. Both effectively saying 'I read the document, here's the information.'"*

---

## End-to-End Scenario — Acquisition Package Generation

**Prompt**: Acquisition package for acquisition coaching, innovation coaching, CSAW workshop facilitation. Budget $2–2.2M. Remote-only. Monthly training events.

### Category / Vehicle — Both correct

Both systems: Professional Services category → HHS PMR FSS checklist, same template. ✅

### PWS Depth — RO more extensive, EAGLE simpler

RO auto-pulled its "tech translator" agent (designed for SOW development). Result: very extensive PWS with streamlined performance-based format and a second traditional TOC format. EAGLE produced a simpler initial-concept PWS.

Ryan: *"More is not necessarily better. Don't cut yourself short. Both acceptable."*

### Contract Type — Major divergence

| System | Recommendation | Estimate | Reasoning |
|--------|---------------|----------|-----------|
| EAGLE | T&M / Labor Hour only | **~$428K** | Single contract type across all tasks |
| RO | FFP + T&M hybrid | **~$2.0M** | Decomposed by task/deliverable: PM → T&M, Coaching → T&M, CSAW workshop → FFP, Innovation snapshots → FFP, Training events → FFP, Readiness survey → FFP |

Ryan's verdict:
- RO's task-area decomposition approach is sound
- **Both wrong to use "Labor Hour" — it's riskier than T&M and "no one ever does labor hour"**
- RO ballooned to ceiling because budget range was given and the system picked the upper bound
- FFP carve-outs are a good idea to *offer* even when T&M dominates — prompts the user to consider risk allocation

### IGCE — EAGLE more grounded, RO ballooned

EAGLE: narrative, ~$428K, 192 hrs at reasonable rates (~$200/hr loaded) — *grounded in detailed inputs Ingrid provided (12 training events, remote, no travel).*
RO: landed near the $2M ceiling without justification; reached the target by inflating quantities/rates.

Ryan: *"Research optimizer seems off. It just said 'what's your budget? OK, I can land near there.'"*

However, RO did one thing better: **methodology / budget narrative** explaining how hourly rates and FFP unit prices were derived. That narrative is standard IGCE practice — lets a reviewer determine whether a later quote is fair and reasonable. Greg confirmed EAGLE already has a markdown ride-along with the IGCE spreadsheet; it needs to carry a methodology/narrative section.

### AP (Acquisition Plan) — EAGLE correct, RO wrong

- **EAGLE**: built from HHS streamlined acquisition plan template (.docx attachment) ✅
- **RO**: built from "AP Structure Guide.txt" — which is a *descriptor* of how to use templates, **not the template itself**

Ryan: *"RO did it wrong. The .txt files in S3 are descriptors on how to use the things in there. The only reason to have .docx/PDF in there is if it's a specific form we are required to use. I'm more confident yours is correct than RO's on this one."*

EAGLE's AP: lighter, section 1–7 aligned to template. RO's AP: heavier, more FAR citations, compliance-heavy, extensive risk framing (which Ryan flagged as "white-knighting" — over-identifying inherently governmental and Privacy-Act concerns that aren't warranted).

Ryan: *"Lighter is better as long as lighter is sufficient. Yours is impressive."*

### Budget vs IGCE Reconciliation — Intake bug

EAGLE asked Ingrid: *"Your budget is $2M but IGCE only comes to $450K — what do you want to do?"*

Ryan: *"That question should never be asked. The IGCE is the new estimated value. If you have a $2M budget but only need a six-pack of soda, you're not spending $2M. I shouldn't even let you do that."*

Action: the IGCE output must promulgate through all downstream documents as the authoritative estimated value. Budget is a ceiling reference, not a target.

### Trade-offs Section (AP Section 6)

Trade-offs are among cost / quality / schedule — "pick 2." Ryan notes this is the most commonly miswritten AP section. EAGLE's answer was simple but acceptable; RO's first trade-off was solid, second silly, third inapplicable.

---

## Greg's Skill Demo (mid-meeting)

Greg demonstrated EAGLE's *skill* feature — a user-created "policy quiz" skill that looks up a policy and quizzes the user with multiple-choice questions. This is a differentiator RO does not have. Combined with MVP1 package download (full end-to-end), Ryan characterized the package/document-management UI as *"leagues beyond what research optimizer can do."*

Greg's framing: skills are author-once, send-to-other-user packages. Ryan's perspective: the individual-user workflow-authoring experience may not be how average users interact with the system, but power users and admins can build skills for broader distribution.

---

## Key Decisions

### 1. Knowledge Base Must Strictly Use RFO, Not Legacy FAR

The FAR 16.505 / 16.507 discrepancy was caused by EAGLE pulling legacy FAR content that has since been superseded by RFO (FAR Overhaul 2025). EAGLE's S3 knowledge-base bucket must be diffed and synced to remove legacy FAR entirely and retain only RFO content. Alvi confirmed the update was applied but timing relative to the test is unclear.

### 2. IGCE Is the Authoritative Estimated Value

EAGLE must stop asking the user to reconcile an IGCE estimate against a stated budget. The IGCE result is the new estimated value and must flow unchanged into the AP and downstream docs. Budget is a separate concept (checking-account ceiling) and must not override IGCE.

### 3. Contract-Type Recommendation Should Offer FFP Hybrid as an Option

Even when T&M is dominant, EAGLE should surface FFP carve-outs for quantifiable deliverables (workshops, training events, discrete snapshots). Do not recommend "Labor Hour" — substitute T&M. Decomposition by task area / deliverable (RO's approach) is the right mental model.

### 4. IGCE Output Must Include a Methodology / Budget Narrative

Either embedded in the IGCE markdown ride-along or as a distinct short document. Purpose: let a reviewer determine price reasonableness when only one quote comes back. Standard government practice.

### 5. Test Questions Must Be Rewritten to Natural CO Language

Current Q1–Q5 are "on-the-nose" knowledge-base probes (explicit FAR citations, alert numbers). Real users will ask *"Has the micro-purchase threshold changed recently?"* rather than *"What are the thresholds under FAC 2025-06?"* Ingrid and Ryan will collaborate on a more realistic question set.

### 6. Supervisor Prompt Distinguishes Acquisition vs Teaching Mode

Existing supervisor instruction says "you're here to do acquisition work, not teach the FAR." Clarification: when a user asks an exploratory how-does-this-work question (e.g., Q3), EAGLE should be verbose/Socratic. When doing document generation, stay terse and operational. This distinction must be reflected in the supervisor prompt.

---

## Action Items

| # | Owner | Action | Priority | Target |
|---|-------|--------|----------|--------|
| 1 | Alvi / WADA | Diff EAGLE S3 knowledge-base bucket against canonical RFO source; strip any remaining legacy FAR; re-ingest | **High** | Before Fri 4/17 follow-up |
| 2 | Backend / Ingrid | Fix intake reconciliation — IGCE value must auto-promulgate as estimated value; remove the "budget vs IGCE" user-facing question | **High** | This sprint |
| 3 | Backend | Add FFP-hybrid option surfacing to contract-type recommendation agent; decompose by task area / deliverable | **High** | This sprint |
| 4 | Backend | Remove "Labor Hour" from default contract-type recommendations; substitute T&M | **High** | This sprint |
| 5 | Backend / Greg | Ensure IGCE output carries a methodology / budget-narrative section explaining rate derivation and FFP unit-price logic | **Medium** | This sprint |
| 6 | Ingrid + Ryan | Rewrite Q1–Q5 and add a natural-language question set (10–15 questions in real user voice) | **High** | Fri 4/17 working session |
| 7 | Backend / TAC | Update supervisor prompt to distinguish teaching mode (exploratory questions → verbose) vs acquisition mode (doc generation → terse) | **Medium** | Next sprint |
| 8 | Backend | Investigate why EAGLE jumps to document generation before gathering enough intake context (PWS scenario started before confirming training-event cadence) | **Medium** | Next sprint |
| 9 | Ingrid | Re-run Q5 (SBIR) and Q4 (fair opportunity) after the KB sync to confirm fix | **High** | After Action 1 |
| 10 | Ryan + Ingrid | Continue full scenario analysis at Fri 4/17 2:00–2:30 PM — focus on PWS/IGCE tuning | **High** | Fri 4/17 |
| 11 | Team | Tone down RO-style risk-framing for AP — do not over-identify inherently-governmental and Privacy-Act concerns without cause | **Low** | Ongoing |

---

## Notes for Future Improvements

- **"Explain your actions" pattern**: when EAGLE asks a nonsensical question, tell it to explain why it asked — usually surfaces a bad inference or stale doc reference. Ryan uses this pattern regularly.
- **Demo-question voice**: knowledge-base probe questions are useful regression tests but should not be the public demo set. Switch to natural voice before external demos.
- **RO strength to absorb**: methodology/narrative attached to numeric outputs (IGCE), task-area decomposition for contract-type reasoning.
- **RO weakness to avoid**: ballooning to budget ceiling, over-citing FAR in AP, using descriptor .txt files as templates, over-identifying speculative risks.
- **EAGLE strengths to preserve**: correct template use (HHS streamlined AP), grounded IGCE numbers, package/document management UI, skill system, supervisor-first orchestration.

---

## Next Meeting

**Friday, April 17, 2026 — 2:00–2:30 PM** (Ryan's dev-sec-ops slot, repurposed)
Focus: rewrite test questions in natural voice, validate KB sync fix, continue PWS/IGCE tuning discussion.
