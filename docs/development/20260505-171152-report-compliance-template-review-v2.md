# Compliance Template Review Package — v2 (KB-Grounded)

**To:** Reviewing Compliance Officer
**From:** EAGLE Platform Team
**Date:** 2026-05-05
**Subject:** First-Pass Templates for Eight Acquisition Documents — Approval Requested

---

## What changed since v1

The v1 package (sent earlier today) was drafted from generic FAR/HHSAR knowledge and the existing 23 production prompts in `server/app/doc_prompts.py`. **It did not consult the EAGLE knowledge base in S3.**

A second pass enumerated `s3://eagle-documents-695681773636-dev/eagle-knowledge-base/approved/` and found authoritative NIH/HHS source documents for **6 of the 8 templates**. Those six were redrafted with explicit KB grounding. The two without explicit KB sources (`qasp`, `section_889`) remain at v1 — your review of those should treat the model's FAR-only interpretation as the working draft.

**Material differences caught during the v2 pass** (each template has a `## Source Grounding` table at the bottom of its file showing which KB doc informed which template part):

| Slug | What v1 missed that v2 surfaced |
|---|---|
| `cor_designation` | NIH COR Handbook Appendix 8A's six prescribed responsibility categories; specific FAC-COR dollar tiers (Level I ≤$250K, II $250K–$25M, III >$25M); separate signature page at internal kickoff per Appendix 8B; Project Officer's Technical Questionnaire requirement before subcontractor consent |
| `sb_review` | HHS Acquisition Alert 2023-02 Amendment 4's 5-band threshold matrix; SBCX system submission requirement; 7-day SBS / 12-day PCR review windows with default-approval rule; BPA/IDIQ/BOA exclusion |
| `section_508` | Replaced superseded HHSAR 352.239-73/74 with operative CD 2024-01 clauses 352.239-78/79; corrected WCAG baseline from 2.0 AA to 2.1 AA per OAG FY25-02; added OPDIV 508 Official pre-approval gate; added GPC/micro-purchase 508 documentation duty |
| `priority_sources_checklist` | HHSAM 308.104 three-tier framework (OFPP Required Use → HHS Mandatory Use → HHS Mandatory Consideration); HCA/SPE exception routing; Self-Service Stores first-shop rule; HHSAP Category Management dynamic verification |
| `subk_review` | Corrected threshold from $750K to **$900K**; expanded from FAR 52.219-9 generic 10-element checklist to HHS SOP's authoritative **15-element** structure; three-step CO→OSDBU SBS→SBA PCR process with all-three-signatures-before-award |
| `source_selection_plan` | HHS Down Select Acquisition Guide's confidence-based rating scheme (High/Some/Low); HHS-specific team roles (HHS/OGC, NIH DAPE/BCA/ISSO); RemedyBiz/AT&T case-law citations on SSDD documentation; Phase 1 advisory ≠ debriefing rule |

These are not stylistic refinements — they are corrections to the substantive guidance. Sending v1 to you would have asked you to mark up content that the canonical HHS source documents already settle.

## What we need from the compliance officer

For each template, please verify:

| Check | Question |
|---|---|
| **Authority** | Are the FAR / HHSAR / agency policy citations correct and complete? |
| **Sections** | Are all required sections present? Are any missing or unnecessary? |
| **Worked example** | Does the example reflect the actual format operators expect to see in production? |
| **Rules** | Are the generation guardrails appropriate (no missed regulatory requirements)? |
| **Source Grounding** | Does the table at the bottom of each v2 template accurately attribute content to the right KB doc? Are any sources we should have used but didn't? |

Mark each template **APPROVED**, **APPROVED WITH CHANGES** (specify), or **REJECTED — REWORK** (specify reason).

---

## Template Summary

| # | Slug | Document | Version | KB Grounded? | Required Sections | Worked Example |
|---|------|----------|:---:|:---:|:---:|----------------|
| 1 | `cor_designation` | COR Designation Letter | **v2** | ✅ | 11 | Limitations table |
| 2 | `sb_review` | HHS-653 Small Business Review | **v2** | ✅ | 11 | SB Program Assessment grid |
| 3 | `section_889` | Section 889 Compliance Documentation | v1 | ⚠ | 9 | Offeror Representation Review |
| 4 | `section_508` | Section 508 Compliance Statement | **v2** | ✅ | 9 | Product Type Checklist |
| 5 | `priority_sources_checklist` | Required & Priority Sources Checklist | **v2** | ✅ | 8 | Priority-of-Use Table |
| 6 | `subk_review` | Subcontracting Plan Review | **v2** | ✅ | 11 | 15-Element Adequacy Checklist |
| 7 | `qasp` | Quality Assurance Surveillance Plan | v1 | ⚠ | 9 | Performance Objectives Table |
| 8 | `source_selection_plan` | Source Selection Plan (SSP) | **v2** | ✅ | 11 | Evaluation Factors & Subfactors |

⚠ = no KB authoritative source identified for this slug; v1 reflects FAR + model-knowledge interpretation.

---

## Template Files

Open in any markdown viewer. v2 files include a `## Source Grounding` table at the bottom mapping content to its KB source.

| Template | File | Source Grounding |
|---|---|:---:|
| COR Designation Letter | `docs/development/templates/cor_designation-template-v2.md` | NIH COR Handbook + FAQ |
| HHS-653 Small Business Review | `docs/development/templates/sb_review-template-v2.md` | HHS AA 2023-02 Am. 4 |
| Section 889 Compliance | `docs/development/templates/section_889-template-v1.md` | (none — FAR 4.21 only) |
| Section 508 Compliance | `docs/development/templates/section_508-template-v2.md` | OAG FY25-02 + CD 2024-01 |
| Priority Sources Checklist | `docs/development/templates/priority_sources_checklist-template-v2.md` | NIH Reference + HHSAM 308 |
| Subcontracting Plan Review | `docs/development/templates/subk_review-template-v2.md` | HHS SubK Review Process SOP |
| Quality Assurance Surveillance Plan | `docs/development/templates/qasp-template-v1.md` | (none — FAR 46.401 only) |
| Source Selection Plan | `docs/development/templates/source_selection_plan-template-v2.md` | HHS Down Select Guides + ACQuipedia |

v1 files for the six redrafted templates remain in the directory for diff reference but should not be reviewed.

---

## Approval Matrix

| # | Template | Version | APPROVED | APPROVED W/ CHANGES | REJECTED — REWORK | Comments |
|---|----------|:---:|:---:|:---:|:---:|---|
| 1 | `cor_designation` | v2 | | | | |
| 2 | `sb_review` | v2 | | | | |
| 3 | `section_889` | v1 ⚠ | | | | |
| 4 | `section_508` | v2 | | | | |
| 5 | `priority_sources_checklist` | v2 | | | | |
| 6 | `subk_review` | v2 | | | | |
| 7 | `qasp` | v1 ⚠ | | | | |
| 8 | `source_selection_plan` | v2 | | | | |

**Reviewer signature:** ________________________________________
**Name / Title:** ____________________________________________
**Date:** ___________________

---

## What happens after approval

1. Approved templates → committed to `server/app/doc_prompts.py` as named constants
2. Each slug's `DocSpec.system_prompt` in `server/app/doc_registry.py` updated to reference the new constant
3. Module-load validator confirms the consolidated registry is consistent
4. Unit tests run; if green, the changes ship in the next deployment
5. Templates marked APPROVED W/ CHANGES return to the platform team with the change list, then back to the officer for re-review
6. Templates marked REJECTED — REWORK get a fresh draft and re-enter this review cycle
7. **For `qasp` and `section_889`** (no KB source found): if your review identifies an authoritative NCI/HHS document that should have informed the template, point us to it and we'll redraft those as v2 with KB grounding to match the rest

---

## How v2 was generated (transparency)

1. Eight parallel subagents drafted v1 templates from generic FAR/HHSAR knowledge — **without** consulting the EAGLE knowledge base.
2. Spot check raised the question: did we miss approved example documents in S3?
3. SSO refresh enabled `s3://eagle-documents-695681773636-dev/eagle-knowledge-base/approved/` enumeration.
4. Targeted searches identified KB sources for 6 of 8 slugs. Sources downloaded to local cache (`.tmp/kb-cache/`).
5. Six redrafting subagents spawned in parallel, each given the relevant KB sources as required reading. Each agent produced a v2 with a `## Source Grounding` table at the bottom attributing content to its source.
6. Spot check confirmed voice consistency with `doc_prompts.py` was preserved across the rewrite.

The v2 package is what you should review. v1 files are kept in the directory for reference but should not consume your time.

---

*Generated by EAGLE Platform Team — NCI Office of Acquisitions, National Cancer Institute*
