# KB vs Codebase Agent Prompt Comparison

Date: 2026-04-17

## Scope

This compares:

- KB baseline: `/Users/hoquemi/Desktop/KB/rh-eagle-2/agents`
- Codebase prompts: `/Users/hoquemi/Desktop/sm_eagle/eagle-plugin/agents`
- Codebase agent registration: `/Users/hoquemi/Desktop/sm_eagle/eagle-plugin/plugin.json`

`rh-eagle-2` was used as the primary KB baseline because it is the fuller prompt set. It includes all `rh-eagle-1` agents plus two additional specialists.

## Executive Summary

- `rh-eagle-2` defines 10 agent prompts.
- The codebase defines 8 prompt files: `supervisor` plus 7 specialists.
- The codebase does not currently have prompt files for the KB's `COMPLIANCE` or `FINANCIAL` agents.
- KB prompts are more explicit about exactly which source documents and folders agents should consult.
- The codebase supervisor moved much of that logic into tools and checklist-driven retrieval: `research`, `manage_package(...checklist)`, and `query_compliance_matrix`.
- Several codebase specialist prompts are materially shorter than the KB versions, especially `legal`, `tech`, `market`, and `public`.
- The codebase supervisor still references missing specialist identities such as `@RH-complianceAgent` and `@RH-financialAgent`, even though those prompt files are not present in `eagle-plugin/agents`.

## Agent Count

| Source | Agent count | Notes |
|---|---:|---|
| `Desktop/KB/rh-eagle-1/agents` | 8 | Older baseline |
| `Desktop/KB/rh-eagle-2/agents` | 10 | Adds `08-COMPLIANCE.txt` and `09-FINANCIAL.txt` |
| `sm_eagle/eagle-plugin/agents` | 8 | `supervisor` plus 7 specialists |

## Agent Mapping

| KB agent | Codebase match | Status |
|---|---|---|
| `00-supervisor` | `supervisor` | Present |
| `01-policy-supervisor` | `policy-supervisor` | Present |
| `02-legal` | `legal-counsel` | Present, renamed |
| `03-tech` | `tech-translator` | Present, renamed |
| `04-market` | `market-intelligence` | Present |
| `05-public` | `public-interest` | Present, renamed |
| `06-policy-librarian` | `policy-librarian` | Present |
| `07-policy-analyst` | `policy-analyst` | Present |
| `08-COMPLIANCE` | none | Missing from codebase prompts |
| `09-FINANCIAL` | none | Missing from codebase prompts |

## Prompt Comparison Matrix

| KB agent | Codebase match | KB prompt says to reference | Codebase prompt says to reference | Named work products |
|---|---|---|---|---|
| `00-supervisor` | `supervisor` | `agents/*.txt`; specialist KB folders; `supervisor-core` only when acting as supervisor; explicit template and guide paths such as `supervisor-core/essential-templates/HHSAR_CD_2024_01_OAMS_Security_Checklist_Template.txt` and `compliance-strategist/HHSAR-guidance/HHSAR_CD_2024_01_OAMS_Security_Checklist_Guide.txt` | Mostly tool-driven retrieval: `manage_package(...checklist)`, `research(...include_checklist=true)`, `query_compliance_matrix`, and returned `eagle-knowledge-base/approved/...` paths; also states supervisor should access only `supervisor-core-kb` directly and use specialist agents for specialist knowledge | `son_products`, `price_reasonableness`, `required_sources`, `purchase_request`, Market Research, IGCE, SOW, PWS, SOO, Streamlined AP, Full AP, SSP, D&Fs, JOFOC, task order package, OAMS Security Checklist |
| `01-policy-supervisor` | `policy-supervisor` | `agents/06-policy-librarian.txt`, `agents/07-policy-analyst.txt`, plus all KB folders as needed for context | Mostly route and delegate behavior; no strong hardcoded source-document list beyond routing to librarian and analyst | Synthesis output, readiness assessment, update plans, training recommendations, compliance and update action items |
| `02-legal` | `legal-counsel` | Explicit `KB references:` blocks including `NIH_Source_Selection_Guidance_2018.txt` and `legal-counselor/GAO-decisions/` | No explicit named source files in the code prompt | Legal risk analysis, protest analysis, solicitation review, appropriations and fiscal-law analysis |
| `03-tech` | `tech-translator` | `NIH_SOW_Best_Practices_Guide.txt`, `technical-translator/SOW-examples/`, `technical-translator/PWS-examples/`, and technical evaluation template references | No explicit named source files in the code prompt | SOW, PWS, SOO, evaluation criteria, requirement rewrites |
| `04-market` | `market-intelligence` | `HHS_Market_Research_Report_Template.txt`, `market-intelligence/small-business/`, `market-intelligence/pricing-data/`, `NCI_BPA_Portfolio_GSA_Summary.txt` | KB-first retrieval through `knowledge_search` and `knowledge_fetch`, then web-verified vendor, pricing, and vehicle sources | Market Research Report, vendor and vehicle assessment, price benchmarking, small-business analysis |
| `05-public` | `public-interest` | No strong explicit source-file list; mostly ethics, transparency, OCI, and fairness principles | No explicit named source files in the code prompt | Ethics analysis, OCI analysis, public-interest review |
| `06-policy-librarian` | `policy-librarian` | All KB folders; example source files such as `supervisor-core/checklists/Threshold_Quick_Reference.txt`, plus files in `financial-advisor` and `compliance-strategist` | Own reference KB files such as `rh-policy-librarian/audit-checklists.txt`; also cites specific KB files in examples like `supervisor-core/checklists/Threshold_Quick_Reference.txt` | Audit reports, validation reports, change logs, contradiction and gap findings |
| `07-policy-analyst` | `policy-analyst` | All KB folders for coverage review and pattern analysis | `knowledge_search`, `knowledge_fetch`, `search_far`, then web sources for recent changes | Strategic analysis, regulatory impact analysis, training-gap analysis, improvement recommendations |
| `08-COMPLIANCE` | none | Strong explicit list including `HHS_Acquisition_Plan_Template_2024.txt`, `GSA_Schedules_vs_Open_Market_Guide.txt`, `FAR_52212-5_Enhanced_Cheat_Sheet_2025.md`, `NIH_Source_Selection_Guidance_2018.txt`, `NIH Policy 6307-3`, `NIH Policy 6325-1`, and `NIH Policy 6035` | No dedicated code prompt exists | Acquisition-strategy review, solicitation compliance review, source-selection review, J&A and limited-source review, cross-document consistency review |
| `09-FINANCIAL` | none | Strong explicit list including `NIH_IGCE_IDIQ_Research_2017.txt`, `NIH Policy 6015-1`, `FAR 15.404-1`, `FAR 52.222-46`, and `ECP_Evaluation_Master_Guide.txt` | No dedicated code prompt exists | IGCE analysis, cost and price analysis, cost realism, LCAT analysis, appropriations and budget review |

## Key Differences

### 1. KB prompts are more explicit about source material

The KB prompts often name exact files, folders, and templates the agent should rely on. This is especially true for:

- `00-supervisor`
- `02-legal`
- `03-tech`
- `04-market`
- `08-COMPLIANCE`
- `09-FINANCIAL`

### 2. Codebase prompts are more tool-oriented

The codebase supervisor in particular has shifted from "read these files" to:

- determine required documents from package checklists
- use `research(...)` for KB retrieval
- use `query_compliance_matrix` for threshold and vehicle logic
- cite returned `eagle-knowledge-base/approved/...` paths

This makes the codebase prompt less explicit on exact source files, but more explicit on retrieval workflow.

### 3. Two KB specialists are missing as codebase prompt files

The clearest gap is:

- `08-COMPLIANCE.txt`
- `09-FINANCIAL.txt`

These are fully defined KB specialists with explicit source-document guidance, but they do not exist as dedicated prompt files in `eagle-plugin/agents`.

### 4. The codebase supervisor still references missing specialists

The current codebase supervisor prompt still references:

- `@RH-complianceAgent`
- `@RH-financialAgent`

That indicates the migration is incomplete or partially refactored.

## Practical Takeaway

If the goal is to preserve prompt-level guidance about which source documents agents should use, the KB baseline is still richer than the current codebase prompt set.

If the goal is runtime behavior, the codebase has replaced part of that prompt guidance with retrieval and checklist tools, especially in the supervisor workflow.

The largest prompt-level content gaps are the missing `COMPLIANCE` and `FINANCIAL` specialist prompts and the loss of explicit source-document references in several renamed specialist prompts.

## Suggested Follow-Ups

1. Add dedicated codebase prompt files for compliance and financial specialists, or intentionally remove those roles everywhere they are still referenced.
2. Decide whether explicit source-document lists should remain in prompts or live entirely behind retrieval tools.
3. Reconcile supervisor routing language with the actual registered agent set in `eagle-plugin/plugin.json`.
4. If desired, produce a second report that lists exact named source documents present in KB prompts but absent from codebase prompts.
