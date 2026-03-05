---
description: Test EAGLE specialist agent skills — legal counsel (J&A), market intelligence (vendor research), tech review (SOW translation), public interest (fairness) — verifies each specialist routes correctly and responds with domain-appropriate content
argument-hint: [url]
---

# EAGLE Specialist Skills Test

Tests 4 specialist agents by sending domain-specific prompts through the EAGLE chat UI and verifying each agent responds with the correct domain language, FAR citations, and specialist-level analysis. Mirrors SDK eval tests 10–13.

## Variables

| Variable | Value | Description |
| -------- | ----- | ----------- |
| SKILL | `agent-browser` | Headless, Linux-compatible |
| MODE | `headless` | No Chrome DevTools required |
| URL | `{PROMPT}` or `http://localhost:3000` | Base URL |

If {PROMPT} contains a URL use it, otherwise default to `http://localhost:3000`.

---

## Part 1: Legal Counsel — Sole Source J&A Review (SDK Test 10)

### Phase 1: Load Chat and Start Fresh

1. Navigate to `{URL}/chat`
2. Wait up to 10 seconds for the page to load
3. If a login page appears, report **FAIL — Not authenticated** and stop
4. Click "New Chat" in the sidebar to ensure a clean session
5. Wait for the welcome screen to appear
6. Take a screenshot — save as `specialist-legal-start.png`

### Phase 2: Send Legal Counsel Query

7. Click the chat textarea and type exactly:
   `I need to sole source a $985K Illumina NovaSeq X Plus genome sequencer. Only Illumina makes this instrument. Assess the protest risk and tell me what FAR authority applies. What case precedents support this?`
8. Press Enter and wait up to 60 seconds for EAGLE to respond
9. Take a screenshot after response — save as `specialist-legal-response.png`
10. Verify the response contains **at least 3** of the following:
    - FAR citation: `FAR 6.302`, `6.302-1`, or `one responsible source`
    - Protest risk: words `protest`, `risk`, `GAO`, or `vulnerability`
    - Case law: words `B-4`, `decision`, `precedent`, `sustained`, or `denied`
    - Proprietary analysis: words `proprietary`, `sole source`, `only one`, or `sole vendor`
    - Recommendation: words `recommend`, `document`, `justif`, or `market research`

---

## Part 2: Market Intelligence — Vendor Research (SDK Test 11)

### Phase 3: New Chat for Market Intelligence

11. Click "New Chat" in the sidebar
12. Wait for welcome screen
13. Click the chat textarea and type exactly:
    `We need IT modernization services for approximately $500K over 3 years. Cloud migration and agile development. What does the market look like? Any small business set-aside opportunities? What about GSA vehicles?`
14. Press Enter and wait up to 60 seconds for EAGLE to respond
15. Take a screenshot — save as `specialist-market-response.png`
16. Verify the response contains **at least 3** of the following:
    - Small business: words `small business`, `8(a)`, `HUBZone`, `WOSB`, `SDVOSB`, or `set-aside`
    - GSA vehicles: words `GSA`, `schedule`, `GWAC`, `Alliant`, `CIO-SP`, or `IT Schedule`
    - Pricing analysis: words `rate`, `pricing`, `cost`, `benchmark`, or `labor`
    - Vendor landscape: words `vendor`, `contractor`, `provider`, `firm`, or `company`
    - Competition: words `competit`, `market`, `availab`, or `capabil`

---

## Part 3: Tech Review — SOW Requirements Translation (SDK Test 12)

### Phase 4: New Chat for Tech Review

17. Click "New Chat" in the sidebar
18. Wait for welcome screen
19. Click the chat textarea and type exactly:
    `I need to write SOW requirements for an agile cloud migration project. The team will use 2-week sprints, AWS GovCloud, and need FedRAMP compliance. How should I express these technical requirements in contract language? What evaluation criteria would you recommend?`
20. Press Enter and wait up to 60 seconds for EAGLE to respond
21. Take a screenshot — save as `specialist-tech-response.png`
22. Verify the response contains **at least 3** of the following:
    - SOW language: words `SOW`, `statement of work`, `deliverable`, or `performance`
    - Agile terms: words `sprint`, `agile`, `iteration`, `scrum`, or `backlog`
    - Evaluation criteria: words `evaluat`, `criteria`, `factor`, `technical approach`, or `past performance`
    - Compliance language: words `FedRAMP`, `508`, `security`, `compliance`, or `GovCloud`
    - Measurable requirements: words `measur`, `accept`, `milestone`, `definition of done`, or `metric`

---

## Part 4: Public Interest — Fairness & Transparency Review (SDK Test 13)

### Phase 5: New Chat for Public Interest

23. Click "New Chat" in the sidebar
24. Wait for welcome screen
25. Click the chat textarea and type exactly:
    `Review this for public interest concerns: We're doing a sole source award for $2.1M in IT services to the same vendor who had the previous contract. No sources sought was posted on SAM.gov. Only 2 vendors were contacted during market research. This is a congressional interest area.`
26. Press Enter and wait up to 60 seconds for EAGLE to respond
27. Take a screenshot — save as `specialist-public-response.png`
28. Verify the response contains **at least 3** of the following:
    - Fairness concern: words `fair`, `equit`, `appearance`, `vendor lock`, or `incumbent`
    - Transparency: words `transparen`, `SAM.gov`, `sources sought`, `public`, or `notice`
    - Protest risk: words `protest`, `risk`, `vulnerab`, `challenge`, or `GAO`
    - Congressional scrutiny: words `congress`, `oversight`, `media`, `scrutin`, or `political`
    - Recommendations: words `recommend`, `mitigat`, `broader`, `expand`, or `post`

---

## Part 5: Report Results

Report **PASS** or **FAIL** for each check:

| Check | Expected | Actual | Result |
|-------|----------|--------|--------|
| Legal: FAR citation | `FAR 6.302` or `6.302-1` in response | | |
| Legal: Protest risk | `protest`, `risk`, or `GAO` in response | | |
| Legal: Case law reference | `precedent`, `sustained`, `denied`, or `B-4` | | |
| Legal: 3+ indicators met | At least 3 of 5 legal indicators | | |
| Market: Small business options | `small business`, `8(a)`, or `set-aside` | | |
| Market: GSA vehicle mention | `GSA`, `schedule`, `GWAC`, or `Alliant` | | |
| Market: 3+ indicators met | At least 3 of 5 market indicators | | |
| Tech: SOW contract language | `SOW`, `deliverable`, or `performance` | | |
| Tech: Agile terms | `sprint`, `agile`, or `iteration` | | |
| Tech: 3+ indicators met | At least 3 of 5 tech indicators | | |
| Public: Transparency concern | `SAM.gov`, `sources sought`, or `transparen` | | |
| Public: Protest risk flagged | `protest`, `risk`, or `vulnerab` | | |
| Public: 3+ indicators met | At least 3 of 5 public interest indicators | | |

**Overall result**: PASS only if ALL 13 checks pass.

If any check fails, include:
- Which specialist skill failed (legal/market/tech/public)
- Whether the response was empty, generic, or domain-specific
- Whether EAGLE routed to the correct agent (check for agent name in response header)
- Any console errors relating to agent routing
