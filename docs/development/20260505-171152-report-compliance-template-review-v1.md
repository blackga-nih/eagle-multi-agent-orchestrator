# Compliance Template Review Package

**To:** Reviewing Compliance Officer
**From:** EAGLE Platform Team
**Date:** 2026-05-05
**Subject:** First-Pass Templates for Eight Acquisition Documents — Approval Requested

---

## Why this package exists

EAGLE's document generator currently produces eight Tier A acquisition documents as raw markdown without an official template structure. The Office of Acquisitions identified these as the highest-priority gaps because operators (contracting officers, card holders, source selection authorities) expect the standard federal layout when they print, sign, or attach these documents to a package.

This package contains a high-level template skeleton for each of the eight documents. **Each skeleton is ~50 lines** and consists of:

1. A persona / purpose statement explaining when the document is required and who signs it
2. A numbered list of required sections, one line each, describing what goes in that section
3. A small worked example showing how one section reads when filled in
4. A short list of generation rules (specificity, citation requirements, missing-information handling)

The template structure is uniform with the existing 23 prompts already in production (sow, igce, j&a, etc.) so the compliance officer can review one template and trust that the rest follow the same conventions.

## What we need from the compliance officer

For each of the eight templates, please verify:

| Check | Question |
|---|---|
| **Authority** | Are the FAR / HHSAR / agency policy citations correct and complete? |
| **Sections** | Are all required sections present? Are any missing or unnecessary? |
| **Worked example** | Does the example reflect the actual format operators expect to see in production? |
| **Rules** | Are the generation guardrails appropriate (no missed regulatory requirements)? |
| **Audience** | Is the right reviewer / signer named for this document? |

Mark each template **APPROVED**, **APPROVED WITH CHANGES** (specify), or **REJECTED — REWORK** (specify reason). Once approved, the templates will be wired into `server/app/doc_prompts.py` and surfaced through the document registry without code changes elsewhere.

---

## Template Summary

| # | Slug | Document | Authority | Required Sections | Worked Example |
|---|------|----------|-----------|-------------------|----------------|
| 1 | `cor_designation` | COR Designation Letter | FAR 1.602-2(d), HHSAR 301.604, OFPP 05-01 | 11 | Limitations table |
| 2 | `sb_review` | HHS-653 Small Business Review | FAR Part 19, HHSAR 319, FAR 19.502 | 8 | SB Program Assessment grid |
| 3 | `section_889` | Section 889 Compliance Documentation | FAR 4.21, FAR 52.204-24/25/26, NDAA FY2019 § 889 | 9 | Offeror Representation Review |
| 4 | `section_508` | Section 508 Compliance Statement | 29 USC 794d, 36 CFR 1194, FAR 39.2 | 8 | Product Type Checklist |
| 5 | `priority_sources_checklist` | Required & Priority Sources Checklist | FAR Part 8, HHS supplemental | 7 | Priority-of-Use Table |
| 6 | `subk_review` | Subcontracting Plan Review | FAR 19.705-4, FAR 52.219-9, HHSAR 352.219 | 8 | FAR 52.219-9 Adequacy Checklist |
| 7 | `qasp` | Quality Assurance Surveillance Plan | FAR 46.401, FAR 37.6, NIH PBA handbook | 9 | Performance Objectives Table |
| 8 | `source_selection_plan` | Source Selection Plan (SSP) | FAR 15.3, HHSAR 315.3 | 11 | Evaluation Factors & Subfactors |

Total: 8 templates · ~71 sections aggregated · ~353 lines of template content.

---

## Template Files

Each template lives at `docs/development/templates/<slug>-template-v1.md` for direct review. Open them in any markdown viewer or text editor.

| Template | File |
|---|---|
| COR Designation Letter | `docs/development/templates/cor_designation-template-v1.md` |
| HHS-653 Small Business Review | `docs/development/templates/sb_review-template-v1.md` |
| Section 889 Compliance | `docs/development/templates/section_889-template-v1.md` |
| Section 508 Compliance | `docs/development/templates/section_508-template-v1.md` |
| Required & Priority Sources Checklist | `docs/development/templates/priority_sources_checklist-template-v1.md` |
| Subcontracting Plan Review | `docs/development/templates/subk_review-template-v1.md` |
| Quality Assurance Surveillance Plan | `docs/development/templates/qasp-template-v1.md` |
| Source Selection Plan | `docs/development/templates/source_selection_plan-template-v1.md` |

---

## Approval Matrix

Please initial and date the appropriate column for each template.

| # | Template | APPROVED | APPROVED W/ CHANGES | REJECTED — REWORK | Comments |
|---|----------|:---:|:---:|:---:|---|
| 1 | `cor_designation` | | | | |
| 2 | `sb_review` | | | | |
| 3 | `section_889` | | | | |
| 4 | `section_508` | | | | |
| 5 | `priority_sources_checklist` | | | | |
| 6 | `subk_review` | | | | |
| 7 | `qasp` | | | | |
| 8 | `source_selection_plan` | | | | |

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

The four originally-broken slugs (qasp, sb_review, priority_sources_checklist, section_889) will benefit from this most directly — their current generation falls back to a generic skeleton when invoked, so this review is a real quality upgrade.

---

*Generated by EAGLE Platform Team — NCI Office of Acquisitions, National Cancer Institute*
