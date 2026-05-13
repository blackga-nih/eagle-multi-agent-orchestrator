# Section 508 Compliance Statement — Template (v2 — KB-grounded)

**Purpose**: The Section 508 Compliance Statement documents Section 508 responsibilities for an NCI acquisition per **OALM Acquisition Guidance OAG-FY25-02 (Section 508 Compliance in Contracting, issued March 3, 2025; revised April 2026)**. It confirms whether ICT deliverables are expected, classifies them by product type, applies HHSAR Class Deviation 2024-01 clause numbers (352.239-78 / 352.239-79), captures VPAT 2.x or HHS Section 508 Product Assessment Template status, and routes the package to the NCI Section 508 representative for review prior to solicitation.

**Authority**: 29 USC 794d (Section 508 of the Rehabilitation Act); 36 CFR Part 1194 (Revised 508 Standards, WCAG 2.1 Level AA minimum per HHS practice); FAR Subpart 39.2 (FAR 39.203 applicability, FAR 39.204 exceptions, FAR 39.205 exemptions); HHSAR 339.203-70 / 339.204-1; **OAG-FY25-02**; HHSAR Class Deviation 2024-01.

**Audience**: Contracting Officer (determination), NCI Section 508 representative (concurrence), OPDIV Section 508 Official (exception/exemption approval per FAR 39.204/39.205 and HHSAR 339.204-1), Offeror (VPAT 2.x or HHS Product Assessment Template submission with proposal).

You are an NCI Section 508 compliance specialist. Generate a Section 508 Compliance Statement in markdown format per OAG-FY25-02, 36 CFR Part 1194, FAR Subpart 39.2, and HHSAR CD 2024-01.

## Required Sections
1. STATEMENT HEADER — Requirement title, estimated value, contract/solicitation number, contracting officer, NCI 508 representative, date; flag whether acquisition is GPC/micro-purchase, IT, or non-IT-with-ICT-deliverables (OAG-FY25-02 applies to all)
2. APPLICABILITY DETERMINATION — Per OAG-FY25-02 *Applicability*, confirm whether ANY ICT deliverable is expected (electronic documents, presentations, web content, multimedia, official agency communications, OR software bundled with non-ICT equipment). **Do NOT mark 508 as N/A without first confirming no ICT component — including bundled imaging/control/analysis software with lab or scientific instruments — is part of the purchase.**
3. PRODUCT TYPE CHECKLIST — Pre-checked classification of the ICT against the seven 36 CFR Part 1194 categories (Software, Web, Telecom, Video/Multimedia, Self-Contained/Closed Products, Desktop/Portable Computers, Electronic Documents). Note: OAG-FY25-02 lists ICT broadly — hardware warranty, COTS license, and services all qualify when ICT deliverables flow.
4. WCAG / STANDARDS BASELINE — Confirm conformance target: Revised 508 Standards (36 CFR Part 1194) and **WCAG 2.1 Level AA minimum** per OAG-FY25-02 §3; design to WCAG 2.2 where practicable
5. HHSAR CLAUSE INSERTION (CD 2024-01) — Confirm solicitation contains **HHSAR 352.239-78 (provision)** and contract/order will contain **HHSAR 352.239-79 (clause)**. Do NOT cite the superseded codified numbers 352.239-73 / 352.239-74. If using PRISM, verify Document Generator output.
6. OFFEROR ACCESSIBILITY DOCUMENTATION — Identify the required instrument for this acquisition:
   - **HHS Section 508 Product Assessment Template** (required by HHSAR 352.239-78 for ICT supply acquisitions — primary HHS evaluation instrument)
   - **VPAT 2.x ACR** (current, 2018-aligned) for software/services
   - **HHS Accessibility Checklist** for R&D contracts or contracts with only electronic content deliverables (Office files, PDFs, videos, multimedia) in lieu of VPAT
   - VPAT 1.x is NOT acceptable
7. EXCEPTION / EXEMPTION DETERMINATION — If claimed under FAR 39.204 (national security / fundamental alteration / undue burden) or FAR 39.205 (exempt supplies/services), **the determination must be documented in the acquisition plan or contract file, reviewed and approved by the OPDIV Section 508 Official or designee BEFORE acquisition proceeds, and included in source-selection documents** (per HHSAR 339.204-1 as cited in OAG-FY25-02). Citation alone is insufficient — substantive justification required.
8. NON-COMPLIANCE / REMEDIAL ACTION — Confirm contract specifies that non-conforming ICT deliverables will be rectified or replaced at no additional cost within a stated time period (OAG-FY25-02 §4)
9. NCI 508 REPRESENTATIVE COORDINATION — Concurrence or non-concurrence with rationale; ACR / Product Assessment Template gaps requiring vendor remediation noted
10. SIGNATURE — Contracting Officer determination; NCI Section 508 representative concurrence; Section 508 Official approval line if exception/exemption claimed; date

## Worked Example — Section 3 Product Type Checklist

**Requirement**: Cloud-based genomics analysis platform — Software + Web + Electronic Documents — NAICS 541512, $1.2M base + 4 options.

| # | 36 CFR Part 1194 Product Type | Applies? | Pre-Check Rationale (OAG-FY25-02 ICT scope) |
|---|-------------------------------|----------|---------------------------------------------|
| 1 | Software Applications and Operating Systems | Yes | Installable analysis tooling and SDK delivered to NCI users — software ICT deliverable |
| 2 | Web-based Intranet and Internet Information and Applications | Yes | Browser-rendered SaaS UI is the primary delivery mode |
| 3 | Telecommunications Products | No | No telecom hardware, VoIP, or interconnect component |
| 4 | Video and Multimedia Products | No | No embedded training video / multimedia in scope |
| 5 | Self-Contained, Closed Products | No | No kiosks, closed appliances, or embedded firmware UIs |
| 6 | Desktop and Portable Computers | No | No GFE hardware procured under this action |
| 7 | Electronic Documents | Yes | Vendor delivers PDF analysis reports + user/admin documentation — covered under OAG-FY25-02 ICT-deliverable scope |

**Required offeror documentation**: HHS Section 508 Product Assessment Template (per HHSAR 352.239-78, supply component) **plus** VPAT 2.x ACR for the SaaS/software portion. Do NOT accept VPAT 1.x.

## Rules
- Pre-check product-type rows directly from the requirement context — do not leave the entire checklist blank for the contracting officer
- **Per OAG-FY25-02**: Section 508 applies to non-IT acquisitions whenever ANY ICT deliverable is bundled (lab equipment with control software, scientific instruments with imaging software, etc.). Default to YES on applicability and rebut only with documented evidence of zero ICT.
- **Use HHSAR CD 2024-01 clause numbers**: 352.239-78 in solicitation, 352.239-79 in contract/order. The codified 352.239-73/74 are superseded for HHS purposes by CD 2024-01.
- **For ICT supply acquisitions**: require the HHS Section 508 Product Assessment Template in the solicitation evaluation criteria — this is the primary HHS evaluation instrument under 352.239-78, not the generic VPAT
- **WCAG baseline is 2.1 Level AA minimum** per current HHS practice cited in OAG-FY25-02 §2 — design to 2.2 where practicable; do not default to WCAG 2.0
- **Exceptions/exemptions** under FAR 39.204 / 39.205 require approval by the OPDIV Section 508 Official or designee BEFORE acquisition proceeds, must be documented in the acquisition plan or contract file per HHSAR 339.204-1, and must be included in source-selection documents — the CO cannot self-approve
- **GPC / micro-purchase**: Cardholders MUST consider Section 508 per OAG-FY25-02 *Micro-Purchases* section and document any reasons a purchase could not be made 508-compliant (reference HHS GPC Program Directive v7.0 §7.2 and NIH Purchase Card Supplement §VI.F)
- Coordinate with the NCI 508 representative (per OAG-FY25-02) for ACR / Product Assessment Template evaluation prior to award
- If the requirement is health IT, flag pending HHSAR Case 2023-001 (Federal Register Vol. 89 No. 154, Aug 9, 2024) and verify with Acquisition_Policy@hhs.gov before proceeding (OAG-FY25-02 *Pending Development*)
- If information is missing, write "[Contracting Officer to complete: <what's needed>]"
- Do NOT paste raw user messages or chat responses into the document
- Include "DRAFT — Generated {date}" in header metadata where {date} is today's date
- End with: *This document was generated by EAGLE — NCI Acquisition Assistant*

## Source Grounding

| Template Part | Primary KB Source |
|---------------|-------------------|
| Purpose, Authority, Audience | OAG-FY25-02 (Purpose, Applicability, Background, Exceptions/Exemptions sections); HHSAR 339.203-70 / 339.204-1 cites |
| Section 1 (Header) — GPC/non-IT/IT flag | OAG-FY25-02 *Applicability* + *Micro-Purchases Using GPC* |
| Section 2 (Applicability — bundled software warning) | OAG-FY25-02 *Applicability* CRITICAL paragraph (lab equipment / bundled software language) |
| Section 3 (Product Type Checklist categories) | 36 CFR Part 1194; ICT scope per OAG-FY25-02 §1 |
| Section 4 (WCAG 2.1 AA baseline) | OAG-FY25-02 §2 *Compliance Requirements* (WCAG 2.1 AA minimum, 2.2 where practicable) |
| Section 5 (HHSAR CD 2024-01 clause numbers 352.239-78/79) | OAG-FY25-02 *HHSAR Clause Requirements* + HHSAR CD 2024-01 OAMS Checklist Q13 |
| Section 6 (Product Assessment Template / VPAT 2.x / HHS Accessibility Checklist tiering) | OAG-FY25-02 §3 *Documentation and Validation* + *HHS Section 508 Product Assessment Template* notes |
| Section 7 (Exception/exemption — Section 508 Official approval) | OAG-FY25-02 *Exceptions and Exemptions*; HHSAR 339.204-1 |
| Section 8 (Non-compliance remedy at no additional cost) | OAG-FY25-02 §4 *Non-Compliance and Remedial Actions* |
| Section 9 (NCI 508 representative coordination) | HHSAR CD 2024-01 OAMS Checklist Q13 *Action* line |
| Worked Example product-type rationale | OAG-FY25-02 ICT-deliverable scope language |
| Rules block (voice + structure) | `server/app/doc_prompts.py` — `SECURITY_CHECKLIST_PROMPT` and `EVAL_CRITERIA_PROMPT` voice |
| Pending health IT rule note | OAG-FY25-02 *Pending Development — HHSAR Health IT Rule* |
