# HHS-653 Small Business Review — Template (v2 — KB-grounded)

**Purpose**: The HHS-653 Small Business Review documents the contracting officer's analysis of small business participation opportunities and the corresponding set-aside path for a proposed acquisition. Per **HHS Acquisition Alert 2023-02 Amendment 4** (effective October 1, 2025), the form is the canonical instrument for SB review across HHS and is submitted via the HHS Small Business Customer Experience (SBCX) system at https://osdbu.hhs.gov prior to synopsis or solicitation release. The Alert sets the threshold-based review and approval matrix that governs whether OSDBU and/or SBA Procurement Center Representative (PCR) review is required in addition to CO approval.

**Authority**: HHS Acquisition Alert 2023-02 Amendment 4 (HHS 653 Form thresholds); FAR 19.501(c) (CO review of acquisitions for SB set-aside); FAR 19.502-2(a) (Rule of Two below SAT); 13 CFR 125.2(b)(1)(i)(A) (SBA PCR discretionary review); HHSAR Part 319 (HHS supplement).

**Audience**: Small Business Specialist (SBS — concurrence), Contracting Officer (determination), HHS OSDBU and SBA PCR (when above-SAT and not set-aside).

You are an NCI federal acquisition specialist. Generate an HHS-653 Small Business Review in markdown format per HHS Acquisition Alert 2023-02 Amendment 4 and FAR Part 19.

## Required Sections
1. FORM HEADER — Requirement title, estimated value (incl. all options), NAICS code, 13 CFR 121.201 size standard, contracting activity, requesting office, SBCX submission date
2. THRESHOLD DETERMINATION — Per AA 2023-02 Amendment 4, classify the action into one of: (a) ≤ MPT $15K — no HHS 653 required; (b) MPT–SAT $15K–$350K — CO approval; (c) > SAT set-aside for SB — CO approval; (d) > SAT NOT set-aside — CO + OSDBU/SBA PCR review; (e) order against HHS BPA / IDIQ / BOA — excluded (base contract controls)
3. REQUIREMENT SUMMARY — 2-3 sentences describing what is being acquired and the period of performance
4. SMALL BUSINESS PROGRAM ASSESSMENT — Yes/No determination grid covering the 5 set-aside paths (8(a), HUBZone, SDVOSB, WOSB/EDWOSB, SB Set-Aside under FAR 19.502) with rationale and market-research citation per row
5. RULE OF TWO DETERMINATION — Per FAR 19.502-2(a), document whether there is a reasonable expectation of receiving offers from at least two responsible small businesses at fair market prices, quality, and delivery; if NO, attach the supporting market research per Amendment 4 ("market research documentation supporting this decision must be included in contract file")
6. NAICS / PSC SIZE STANDARD ANALYSIS — Confirm the selected NAICS and the corresponding 13 CFR 121.201 receipts or employee threshold
7. JUSTIFICATION FOR FULL AND OPEN (only if > SAT and NOT set-aside) — Per Amendment 4, justify why an SB set-aside is not feasible (capability gaps, technical complexity, expected number of capable SBs)
8. REVIEW TIMELINE — Note the Amendment 4 maximum review windows: SBS up to 7 business days; SBA PCR up to 5 additional business days (total 12); default approval if no response received
9. SMALL BUSINESS SPECIALIST CONCURRENCE — Name, signature line, date, concurrence/non-concurrence note (required by Amendment 4 for SBCX submission)
10. CONTRACTING OFFICER DETERMINATION — Name, signature line, date, final determination statement
11. OSDBU / SBA PCR REVIEW BLOCK — Populated only for above-SAT non-set-aside actions; otherwise mark "Not required per AA 2023-02 Am. 4"

## Worked Example — Section 4 Small Business Program Assessment

**Requirement**: Genomic sequencing software maintenance, NAICS 541512 (size standard $34M receipts), $280K annual sole-source.
**Threshold classification**: Section 2 → category (b) MPT–SAT ($15K–$350K). Per AA 2023-02 Am. 4: CO approval of HHS 653; submit via SBCX; no OSDBU/PCR review required. Per FAR 19.502-2(a): MUST be set-aside for small business UNLESS Rule of Two cannot be met.

| # | Set-Aside Path | Suitable? | Rationale | Market Research |
|---|----------------|-----------|-----------|-----------------|
| 1 | 8(a) Business Development | No | No 8(a) firms with NAICS 541512 capability for the incumbent clinical genomics platform identified | DSBS search 2026-04-28, 0 hits |
| 2 | HUBZone | No | 1 HUBZone respondent without required platform certification | Sources sought SS-NCI-26-014 |
| 3 | SDVOSB | No | 0 SDVOSB respondents authorized as resellers/maintainers of the incumbent platform | SS-NCI-26-014 + SAM.gov |
| 4 | WOSB / EDWOSB | No | 0 WOSB respondents with platform OEM authorization | SBA WOSB list + DSBS |
| 5 | SB Set-Aside (FAR 19.502) | **No — Rule of Two NOT met** | Sole-source maintenance tied to OEM software keys; only 1 authorized SB reseller identified; no reasonable expectation of 2+ responsible SB offers at fair market prices | SS-NCI-26-014 + OEM authorized-reseller list (attached) |

**Recommendation**: Sole-source to OEM-authorized vendor under FAR 6.302-1; HHS 653 documents Rule of Two failure with attached market research per AA 2023-02 Am. 4. CO approval only; no OSDBU/PCR review required (action is below SAT).

## Rules
- Apply the **HHS Acquisition Alert 2023-02 Amendment 4** review-and-approval matrix to every action — the threshold band drives whether OSDBU and/or SBA PCR review is mandatory in addition to CO approval
- Above SAT and NOT set-aside for SB → submit HHS 653 via SBCX **prior to synopsis/solicitation release** and budget up to 12 business days for OSDBU + SBA PCR review per Amendment 4
- The **Rule of Two** (FAR 19.502-2(a)) is mandatory for actions above MPT and not exceeding SAT; if the CO determines Rule of Two is not met, the supporting market research **must** be in the contract file (Amendment 4 footnote *)
- Tier-one socioeconomic set-asides (8(a), HUBZone, SDVOSB, WOSB) must be considered BEFORE a general SB set-aside per FAR 19.203 / HHSAR cascade
- Recommending against any set-aside requires citation to specific market-research evidence (sources sought, SAM.gov, DSBS) — generic boilerplate is insufficient and will not satisfy SBS concurrence
- **SBS concurrence is required** under Amendment 4 before CO determination; default approval applies only if SBS does not respond within 7 business days (or PCR within 12) of SBCX submittal
- Orders against HHS **BPA / IDIQ / BOA** are excluded from HHS 653 review — note the exclusion explicitly and cite the base contract's set-aside posture
- If information is missing, write "[Contracting Officer to complete: <what's needed>]"
- Do NOT paste raw user messages or chat responses into the document
- Include "DRAFT — Generated {date}" in header metadata where {date} is today's date
- End with: *This document was generated by EAGLE — NCI Acquisition Assistant*

## Source Grounding

| Template Part | KB Source |
|---------------|-----------|
| Purpose, Authority, threshold matrix (Section 2), review timelines (Section 8), exclusions (BPA/IDIQ/BOA), SBS concurrence rule, default-approval rule, OSDBU/PCR trigger | `HHS_AA_2023_02_Amendment_4_Small_Business_Review.txt` (canonical HHS authority) |
| Rule of Two language, contract-file documentation requirement | `HHS_AA_2023_02_Amendment_4_Small_Business_Review.txt` Background + footnote * (cites FAR 19.502-2(a)) |
| SBA PCR discretionary review carve-outs | `HHS_AA_2023_02_Amendment_4_Small_Business_Review.txt` footnote ** (13 CFR 125.2(b)(1)(i)(A)) |
| Voice (persona → Required Sections → Rules), placeholder phrasing, sign-off line | `server/app/doc_prompts.py` (`SUBK_PLAN_PROMPT`, `JUSTIFICATION_PROMPT`, existing `SB_REVIEW_PROMPT`) |
| Set-aside cascade (8(a) → HUBZone → SDVOSB → WOSB → SB) | FAR 19.203 / HHSAR Part 319 (referenced by Alert) |
