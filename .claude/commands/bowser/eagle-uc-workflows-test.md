---
description: Test EAGLE Unified Contracting (UC) workflows — 7 acquisition lifecycle scenarios including micro-purchase, option exercise, contract modification, CO package review, closeout, shutdown notification, and score consolidation. Mirrors SDK eval tests 21–27.
argument-hint: [url]
---

# EAGLE UC Workflows Test

Tests 7 Unified Contracting workflow scenarios through the EAGLE chat UI. Each scenario sends a full acquisition prompt and verifies the response contains correct lifecycle guidance, FAR references, and domain-specific analysis. Mirrors SDK eval tests 21–27.

## Variables

| Variable | Value | Description |
| -------- | ----- | ----------- |
| SKILL | `agent-browser` | Headless, Linux-compatible |
| MODE | `headless` | No Chrome DevTools required |
| URL | `{PROMPT}` or `http://localhost:3000` | Base URL |

If {PROMPT} contains a URL use it, otherwise default to `http://localhost:3000`.

---

## Pre-flight

1. Open `{URL}/chat`
2. Wait up to 10 seconds for the page to load
3. If a login page appears, report **FAIL — Not authenticated** and stop
4. Take a screenshot — save as `uc-preflight.png`

---

## UC-02: Micro-Purchase Fast Path (SDK Test 21)

### Phase 1: New Chat

5. Click "New Chat" in the sidebar — wait for the welcome screen
6. Click the chat textarea and type exactly:
   `I have a quote for $13,800 from Fisher Scientific for lab supplies — centrifuge tubes, pipette tips, and reagents. Grant-funded, deliver to Building 37 Room 204. I want to use the purchase card. What's the fastest way to process this?`
7. Press Enter and wait up to 60 seconds for EAGLE to respond
8. Take a screenshot — save as `uc-02-micro-purchase.png`
9. Verify the response contains **at least 3** of the following:
   - Micro-purchase threshold: words `micro-purchase`, `micro purchase`, `micropurchase`, or `simplified`
   - Threshold amount: words `$15,000`, `15k`, `threshold`, `below`, or `under`
   - Purchase card: words `purchase card`, `p-card`, `card holder`, or `government purchase`
   - Streamlined path: words `streamlined`, `fast`, `quick`, `expedit`, or `minimal`
   - FAR reference: words `FAR 13`, `Part 13`, `FAR Part`, or `simplified acquisition`

---

## UC-03: Option Exercise Package (SDK Test 22)

### Phase 2: New Chat

10. Click "New Chat" — wait for the welcome screen
11. Click the chat textarea and type exactly:
    `I need to exercise Option Year 3 on contract HHSN261201500003I. The base value was $1.2M, same scope continuing, new COR replacing Dr. Smith, 3% cost escalation per the contract terms, no performance issues. Option period would be 10/1/2028 through 9/30/2029. What documents do I need to prepare?`
12. Press Enter and wait up to 60 seconds for EAGLE to respond
13. Take a screenshot — save as `uc-03-option-exercise.png`
14. Verify the response contains **at least 3** of the following:
    - Option exercise: words `option`, `exercise`, `option year`, or `option period`
    - Cost escalation: words `escalat`, `3%`, `cost increase`, or `price adjust`
    - COR change: words `COR`, `contracting officer representative`, `nomination`, or `new COR`
    - Package docs: words `acquisition plan`, `SOW`, `IGCE`, or `statement of work`
    - Option letter: words `option letter`, `exercise letter`, `modification`, or `bilateral`

---

## UC-04: Contract Modification (SDK Test 23)

### Phase 3: New Chat

15. Click "New Chat" — wait for the welcome screen
16. Click the chat textarea and type exactly:
    `I need to modify contract HHSN261201500003I. Adding $150K in FY2026 funding and extending the period of performance by 6 months to September 30, 2027. Same scope of work, just continuing the existing effort. Is this within scope? What type of modification is this? What documents do I need?`
17. Press Enter and wait up to 60 seconds for EAGLE to respond
18. Take a screenshot — save as `uc-04-contract-mod.png`
19. Verify the response contains **at least 3** of the following:
    - Modification type: words `modif`, `mod `, `SF-30`, or `amendment`
    - Funding: words `fund`, `$150`, `FY2026`, `incremental`, or `additional`
    - PoP extension: words `period of performance`, `PoP`, `extend`, `extension`, or `September`
    - Scope determination: words `within scope`, `in-scope`, `no J&A`, `same work`, or `bilateral`
    - FAR compliance: words `FAR`, `compliance`, `justif`, `clause`, or `unilateral`

---

## UC-05: CO Package Review & Findings (SDK Test 24)

### Phase 4: New Chat

20. Click "New Chat" — wait for the welcome screen
21. Click the chat textarea and type exactly:
    `Review this acquisition package for a $487,500 IT services contract: The AP says competitive full and open, but the IGCE total is $495,000 — cost mismatch. The SOW mentions a 3-year PoP but the AP says 2 years. Market research is 14 months old. No FAR 52.219 small business clause. Task 3 deliverable in the SOW has no acceptance criteria. Identify all findings and categorize by severity (critical/moderate/minor).`
22. Press Enter and wait up to 60 seconds for EAGLE to respond
23. Take a screenshot — save as `uc-05-co-review.png`
24. Verify the response contains **at least 3** of the following:
    - Cost mismatch finding: words `cost mismatch`, `IGCE`, `inconsisten`, `$487`, or `$495`
    - PoP inconsistency: words `period of performance`, `PoP`, `mismatch`, `3-year`, or `2-year`
    - FAR clause gap: words `FAR 52`, `clause`, `52.219`, or `small business`
    - Severity categories: words `critical`, `moderate`, `minor`, `severity`, or `finding`
    - Stale market research: words `market research`, `outdated`, `14 month`, or `stale`

---

## UC-07: Contract Close-Out (SDK Test 25)

### Phase 5: New Chat

25. Click "New Chat" — wait for the welcome screen
26. Click the chat textarea and type exactly:
    `I need to close out contract HHSN261200900045C. It's a firm-fixed-price contract, all options were exercised, final invoice has been paid, and all deliverables have been accepted. What's the FAR 4.804 close-out checklist? What documents do I still need — release of claims letter, patent report, property report? Draft a COR final assessment outline.`
27. Press Enter and wait up to 60 seconds for EAGLE to respond
28. Take a screenshot — save as `uc-07-closeout.png`
29. Verify the response contains **at least 3** of the following:
    - FAR 4.804 reference: words `FAR 4.804`, `4.804`, `close-out`, or `closeout`
    - Release of claims: words `release of claims`, `release`, or `claims letter`
    - Patent report: words `patent`, `intellectual property`, or `invention`
    - Property report: words `property`, `GFP`, `government furnished`, or `disposition`
    - COR final assessment: words `COR`, `final assessment`, `performance assessment`, or `completion`

---

## UC-08: Government Shutdown Notification (SDK Test 26)

### Phase 6: New Chat

30. Click "New Chat" — wait for the welcome screen
31. Click the chat textarea and type exactly:
    `Government shutdown is imminent — 4 hours away. I have 200+ active contracts. How should I classify them? I know some are fully funded FFP (should continue), some are incrementally funded (stop at limit), some are cost-reimbursement (stop work immediately), and some support excepted life/safety activities. What notification categories do I need? What should each email say? Draft the four notification templates.`
32. Press Enter and wait up to 60 seconds for EAGLE to respond
33. Take a screenshot — save as `uc-08-shutdown.png`
34. Verify the response contains **at least 3** of the following:
    - Shutdown context: words `shutdown`, `lapse`, `appropriation`, or `continuing resolution`
    - FFP continues: words `firm-fixed`, `FFP`, `continue`, or `fully funded`
    - Stop work: words `stop work`, `cease`, `stop-work`, or `suspend`
    - Excepted activities: words `excepted`, `life`, `safety`, `essential`, or `emergency`
    - Notification templates: words `notif`, `email`, `letter`, `template`, or `contractor`

---

## UC-09: Technical Score Sheet Consolidation (SDK Test 27)

### Phase 7: New Chat

35. Click "New Chat" — wait for the welcome screen
36. Click the chat textarea and type exactly:
    `I have 180 score sheets from 9 technical reviewers evaluating 20 proposals. Each reviewer scored 5 evaluation factors: Technical Approach, Management Plan, Past Performance, Key Personnel, and Cost Realism. Three proposals have significant reviewer divergence. The reviewers also submitted 847 total questions — many are duplicates. How should I consolidate the scores? What analysis should I run for reviewer variance? How do I deduplicate and categorize the questions?`
37. Press Enter and wait up to 60 seconds for EAGLE to respond
38. Take a screenshot — save as `uc-09-score-consolidation.png`
39. Verify the response contains **at least 3** of the following:
    - Score consolidation: words `score`, `matrix`, `consensus`, or `consolidat`
    - Evaluation factors: words `technical approach`, `management`, `past performance`, or `key personnel`
    - Variance analysis: words `variance`, `divergen`, `outlier`, `disagree`, or `spread`
    - Deduplication: words `dedup`, `duplicate`, `unique`, `cluster`, or `categoriz`
    - Evaluation report: words `report`, `summary`, `per-contractor`, or `question sheet`

---

## Part 8: Report Results

Report **PASS** or **FAIL** for each check:

| Check | Expected | Actual | Result |
|-------|----------|--------|--------|
| UC-02: Micro-purchase threshold identified | `micro-purchase` or `$15,000` | | |
| UC-02: Purchase card guidance | `p-card` or `purchase card` | | |
| UC-02: 3+ indicators met | At least 3 of 5 | | |
| UC-03: Option exercise guidance | `option year` or `exercise letter` | | |
| UC-03: COR change addressed | `COR` or `nomination` | | |
| UC-03: 3+ indicators met | At least 3 of 5 | | |
| UC-04: Modification type classified | `SF-30`, `bilateral`, or `mod` | | |
| UC-04: Within-scope determination | `within scope` or `no J&A` | | |
| UC-04: 3+ indicators met | At least 3 of 5 | | |
| UC-05: All 5 findings identified | `critical`, `moderate`, `minor` severity | | |
| UC-05: IGCE mismatch flagged | `IGCE`, `cost mismatch`, or `$495` | | |
| UC-05: 3+ indicators met | At least 3 of 5 | | |
| UC-07: FAR 4.804 checklist | `FAR 4.804` or `closeout` | | |
| UC-07: Release of claims | `release of claims` | | |
| UC-07: 3+ indicators met | At least 3 of 5 | | |
| UC-08: 4 contract categories | `FFP`, `stop work`, `excepted` | | |
| UC-08: Notification templates | `template` or `email` | | |
| UC-08: 3+ indicators met | At least 3 of 5 | | |
| UC-09: Variance analysis guidance | `variance` or `divergen` | | |
| UC-09: Deduplication approach | `dedup` or `duplicate` | | |
| UC-09: 3+ indicators met | At least 3 of 5 | | |

**Overall result**: PASS only if ALL 21 checks pass.

If any check fails, include:
- Which UC workflow failed and what the response contained
- Whether EAGLE routed to the correct specialist agent
- Whether the response was generic vs domain-specific
- Any console errors relating to agent routing or skill loading
