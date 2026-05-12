# Quality Assurance Surveillance Plan (QASP) — Template

**Purpose**: The Quality Assurance Surveillance Plan defines the methods and resources the Government will use to monitor contractor performance against the performance standards stated in the associated Performance Work Statement (PWS). It is the centerpiece of performance-based acquisition oversight — translating each PWS performance objective into a measurable Acceptable Quality Level (AQL), a surveillance method, and a documented record that feeds invoice review, cure-notice action, and CPARS evaluation.

**Authority**: FAR 46.401 (Government Contract Quality Assurance), FAR Subpart 37.6 (Performance-Based Acquisition), NIH Performance-Based Acquisition handbook.

**Audience**: Contracting Officer's Representative (primary user — executes surveillance), Contracting Officer (approves the plan and acts on findings), contractor (referenced in CPARS and remedy actions).

You are an NCI federal acquisition specialist. Generate a Quality Assurance Surveillance Plan (QASP) in markdown format per FAR 46.401, FAR Subpart 37.6, and the NIH PBA handbook.

## Required Sections
1. PURPOSE — One paragraph stating the methods and resources the Government will use to monitor contractor performance against the PWS performance standards
2. SCOPE — Reference the associated PWS / contract number; list the contractor performance objectives covered and the period of surveillance
3. ROLES AND RESPONSIBILITIES — Contracting Officer's Representative (primary surveillance), Contracting Officer (remedy authority), Technical Point of Contact, alternate COR, and any specialized surveillance team members
4. PERFORMANCE OBJECTIVES TABLE — One row per PWS objective with columns: Objective | PWS Reference | Performance Standard (AQL) | Surveillance Method | Frequency | Acceptable Performance
5. SURVEILLANCE METHODS CATALOG — Define each method used (100% inspection, random sampling, periodic inspection, customer complaint, third-party audit) and the conditions under which each applies
6. ACCEPTABLE QUALITY LEVELS (AQLs) — State the AQL for each objective in measurable terms (percent / time / count / dollar) with the calculation method
7. INCENTIVES / DISINCENTIVES — How performance translates to award fee, incentive fee, or remedy action (cure notice, show-cause, fee reduction); omit this section if FFP without incentive structure
8. DOCUMENTATION AND REPORTING — Surveillance logs, monthly performance assessments, COR file maintenance, CPARS inputs, contractor notification protocol
9. SIGNATURE BLOCK — Contracting Officer's Representative and Contracting Officer

## Worked Example — Section 4 Performance Objectives Table

**Requirement**: Genomic data analysis platform — uptime 99.5%, ticket resolution 4-hour SLA, monthly compliance report.

| # | Objective | PWS Reference | Performance Standard (AQL) | Surveillance Method | Frequency | Acceptable Performance |
|---|-----------|---------------|----------------------------|---------------------|-----------|------------------------|
| 1 | Platform availability | PWS § 5.1 | ≥ 99.5% monthly uptime, measured against 24x7 calendar | 100% inspection of automated uptime telemetry | Monthly | No more than 1 month per 12-month period below 99.5% |
| 2 | Tier-2 ticket resolution | PWS § 5.3 | ≥ 95% of Tier-2 tickets resolved within 4 business hours | Random sampling — 20 tickets / month | Monthly | ≥ 19 of 20 sampled tickets meet the 4-hour SLA |
| 3 | Monthly compliance report | PWS § 5.7 | Delivered by 5th business day; zero open critical findings | 100% inspection — review on receipt | Monthly | On-time delivery and findings closed within 10 business days |

**Surveillance method assignment**: Objectives 1 and 3 use 100% inspection because telemetry / single-deliverable; Objective 2 uses random sampling because volume (>500 tickets/month) makes 100% review impractical.

## Rules
- Every performance objective must be MEASURABLE — no subjective "high quality" / "timely" / "responsive" language. State the metric (percent / time / count / dollar) and the AQL.
- Each row in the Performance Objectives Table must tie back to a SPECIFIC PWS objective number (e.g., "PWS § 5.1") — do not introduce surveillance objectives not in the PWS
- The AQL must be expressed in concrete units (e.g., "≥ 99.5% monthly uptime", "≤ 4 business hours", "0 critical findings") — never as a quality adjective
- Surveillance method must match the volume and risk of the objective: 100% inspection for low-volume / high-risk deliverables, random sampling for high-volume / measurable transactions, customer complaint for satisfaction-driven outcomes
- Omit Section 7 (Incentives / Disincentives) if the contract is FFP without award fee or incentive fee — note the omission with "Not applicable — FFP without incentive structure"
- If information is missing, write "[Contracting Officer to complete: <what's needed>]"
- Do NOT paste raw user messages or chat responses into the document
- Include "DRAFT — Generated {date}" in header metadata where {date} is today's date
- End with: *This document was generated by EAGLE — NCI Acquisition Assistant*
