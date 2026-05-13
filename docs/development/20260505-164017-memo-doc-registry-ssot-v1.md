# Memorandum

**To:** EAGLE Engineering / NCI Office of Acquisitions
**From:** EAGLE Platform Team
**Date:** 2026-05-05
**Subject:** Document Type Registry — Single Source of Truth Refactor

---

## Background

EAGLE generates 24 distinct federal acquisition documents through `create_document` (SOW, IGCE, J&A, QASP, Section 889 Compliance, etc.). The canonical document-type list had drifted across multiple backend layers — labels, prompts, generators, templates, aliases, and the compliance map each held their own copy. Adding a new document type required keeping all of them in sync, and any miss produced runtime "Unknown document type" errors or silent registry conflicts.

The triggering incident: a contracting officer's package required QASP, HHS-653 Small Business Review, Required & Priority Sources Checklist, and Section 889 Compliance documents. The package compliance map demanded those slugs but the document generator rejected them — the two layers had drifted out of sync over multiple commits. Manual investigation of the diagnostics output identified four additional class-A blockers (D&F, Source Selection Plan, Human Subjects Provisions, COR Designation Letter) and four others requiring different routing (SAM exclusions, FPDS report, Inherently Governmental Certification, Wage Determination).

## Action Taken

A single-source-of-truth refactor was implemented to make this class of drift structurally impossible. All slug-keyed behavior — labels, LLM system prompts, generators, S3 templates, alias resolution, and compliance-matrix integration — now derives from one declaration per slug in `server/app/doc_registry.py`. A module-load validator runs at import time and refuses to start the server if any inconsistency is detected.

The refactor consolidated:

- 23 per-slug generator wrapper functions (deleted)
- The 600-line `_DOC_TYPE_SYSTEM_PROMPTS` dict (relocated to `doc_prompts.py`, derived from registry at runtime)
- The 200-line `TEMPLATE_REGISTRY` dict literal (replaced with a builder that reads the registry)
- The duplicated `DOC_TYPE_ALIASES`, `_FALLBACK_DOC_TYPES`, `_MARKDOWN_ONLY_TYPES`, `_DOC_TYPE_LABELS`, `FORM_TEMPLATES`, and `_COMPLIANCE_DOC_TO_SLUG` dicts (all now derived views)

In addition, **8 previously-blocked document types** were added to the registry and wired end-to-end: QASP, HHS-653 SB Review, Priority Sources Checklist, Section 889, D&F, Source Selection Plan, Human Subjects Provisions, COR Designation Letter, Inherently Governmental Certification, and Wage Determination. Two additional types (SAM exclusions, FPDS report) were classified as `EVIDENCE` kind — externally fetched data routed away from `create_document` with an explicit error pointing operators to the package evidence path.

## Results

| Metric | Before | After |
|---|---|---|
| Adding a new doc type requires | Edits across multiple modules in sync | One registry entry |
| Slugs in the registry | 27 | 44 |
| Slugs accepted by `create_document` | 23 | 41 |
| Drift detection | Runtime errors only | Module-load validator |
| Tests passing | 162/162 | 162/162 |
| Lint clean | yes | yes |

The validator catches alias collisions, slug-key mismatches, generated documents missing both prompt and template, and evidence-kind documents incorrectly declaring a prompt or template. None of these conditions can now reach production.

## Remaining Template Gaps

17 generated document types still produce raw markdown rather than filling an official S3 template. Eight of them have known federal/HHS forms and would benefit from template wiring:

| Slug | Template source | Priority |
|---|---|---|
| `cor_designation` | Reuse existing NIH COR Appointment Memorandum | Quick win — template already in S3 |
| `sb_review` | HHS-653 form (slug is named after it) | High |
| `section_889` | SAM.gov 52.204-26 attestation | High |
| `section_508` | GSA VPAT/ACR template | High |
| `priority_sources_checklist` | HHS/NIH "GSA First" PDF | High |
| `subk_review` | HHSAR 352.219 fillable checklist | Medium |
| `qasp` | NIH PBA handbook example | Medium |
| `source_selection_plan` | NCI/HHSAR 315.3 SSP template | Medium |

Six additional types (D&F, Contract Type Justification, Price Reasonableness, Required Sources, Inherently Governmental, Eval Criteria) could be templated with lower expected gain. Three (Wage Determination, Human Subjects, Security Checklist) are best left as markdown — they are either data lookups or system-specific narratives that resist a single template.

## Recommendation

Begin with `cor_designation`. The NIH COR Appointment Memorandum docx is already in S3 and currently used by the related `cor_certification` slug; pointing `cor_designation` at it is a roughly 15-minute change that exercises the registry's "add a template = edit one file" property. From there, prioritize `sb_review` and `section_889` since both are explicitly named after federal forms that compliance reviewers expect to receive in the standard layout.

The remaining markdown-only types should not be templated speculatively. Each new template carries an ongoing maintenance cost (placeholder map, fallback handling, test coverage) and should be justified by either a compliance auditor request or a documented operator complaint about output format.

---

**Files of record:**

- Spec: `.claude/specs/20260505-155739-plan-doc-registry-ssot-v1.md`
- Registry: `server/app/doc_registry.py`
- Prompts: `server/app/doc_prompts.py`
- Migrated consumers: `ai_document_schema.py`, `doc_type_registry.py`, `template_registry.py`, `package_store.py`, `tools/document_generation.py`, `tools/create_document_support.py`

**Validation:** `ruff check` clean across all 8 modified files. 162/162 unit tests pass (`tests/test_template_schema.py`, `test_unify_document_tracking.py`, `test_dynamic_required_docs.py`, `test_ai_document_schema.py`, `test_template_service.py`).

*Generated by EAGLE Platform Team — NCI National Cancer Institute*
