# Continue Review Eagle Req — Meeting Summary

**Recording ID**: 20260305_140222
**Date**: March 5, 2026, 7:02 PM
**Duration**: 1h 3m 20s
**Format**: Markdown | **Type**: meeting-notes

---

## Executive Summary

This session continued the Eagle requirements review, combining a live KB metadata walkthrough by Jitong Li with a local demo of the new Eagle application by Gregory Black. Ryan Hash provided authoritative acquisition domain feedback on the simplified acquisition decision tree complexity, shared news about outreach to the NIH simplified acquisitions team, and validated the direction of MVP-1 scope: acquisition package document generation. The demo revealed gaps in knowledge base invocation and clarifying-question behavior that are now tracked through an in-app feedback mechanism.

---

## Attendees

| Name | Organization | Role |
|------|-------------|------|
| Black, Gregory | NIH/NCI | Developer [C] |
| Li, Jitong | NIH/NCI | Developer / KB lead [C] |
| Valisetty, Srichaitra | NIH/NCI | Developer (started transcription) [C] |
| Hoque, Mohammed | NIH/NCI | Developer [C] |
| Hash, Ryan | NIH/NCI | Acquisition SME / Evaluator [E] |
| Liang, Shan | NIH/NCI | Evaluator [E] |

> [C] = Contractor | [E] = Evaluator (Government)

---

## Key Discussion Points

### KB Metadata Review (`0:01 – 5:10`)

Jitong Li walked through the KB file metadata schema prepared for Eagle. Key structure:

- Top-level category fields: acquisition type, folder path, file pointer
- Tags drive search retrieval — examples: `macro purchase`, `purchase card`, `13 simplified`, `low dollar`, `FAR 13`, `SAT`, `350K threshold`, `competition`, `small business set-aside`, `RFQ`, `JSA schedule`, `federal supply schedule`, `BPA`
- Ryan Hash confirmed the tag associations were correct in concept. His concern: the system must understand *why* to route to a given acquisition vehicle (Part 13 vs. GSA Schedule 8(a) vs. Part 16.5 vs. Part 19.5), not just what tags exist.

### Simplified Acquisition Decision Tree Complexity (`5:00 – 7:30`)

Ryan Hash emphasized that simplified acquisition is deceptively complex:

- Below the Simplified Acquisition Threshold (SAT), a contracting officer can go Part 13, GSA Schedule 8(a), Part 16.5, Part 19.5, and others — there is no single correct answer.
- Part 10 (market research) is not an acquisition authority.
- The system needs to surface the *reasoning* behind vehicle selection, not just the destination.
- Hash's key observation: "Simplified is actually complex. It's the decision tree stuff that really gets to be a mess."
- Consensus: providing too many rigid rules may degrade LLM performance. The speed and accuracy gains of Eagle outweigh suboptimal vehicle selection.

### NIH Simplified Acquisitions Team Outreach (`7:15 – 14:40`)

Ryan Hash shared significant strategic news:

- He connected with the NIH individual who handles most non-IT simplified acquisitions, who then introduced him to colleagues working on AI tooling and portfolio management.
- The simplified acquisitions team is independently exploring AI for: routing requests to the correct staff member, and identifying savings opportunities across their acquisition portfolio.
- Hash demonstrated Eagle's value directly: after receiving an email that bid boards are being sunset in the new FAR, he asked Eagle's Librarian agent how many documents needed updating — Eagle identified **6 documents and 7 instances** requiring remediation.
- Hash's strategic framing: "I want them living in our space" — a shared knowledge base eliminates the current dual-maintenance problem where policy changes must be propagated separately into Eagle.
- Shan Liang noted this creates an opportunity to sell Eagle to the simplified acquisitions team and potentially have Eagle post policy updates directly to their systems as a later-phase enhancement.

### Bid Boards Being Sunset in New FAR (`9:45 – 11:00`)

- Ryan Hash confirmed that bid boards are being eliminated in the rewrite of the FAR.
- This was used as a live demonstration of Eagle's librarian/policy analysis capability.
- Eagle (research optimizer version) successfully identified all documents containing bid board references needing remediation — without the user having to search manually.

### Live Eagle Demo (`15:20 – 38:00`)

Gregory Black shared a local build of the new Eagle application. Key observations:

| Observation | Status | Owner |
|------------|--------|-------|
| App running locally (no VPN) | Workaround used | Greg |
| Knowledge base not invoked on policy question (bid boards) | Bug — not routing to KB | Greg |
| Feedback button implemented; feedback logged to backend | Working | Greg |
| Prompts should ask more clarifying questions before generating | Needs tuning | Greg |
| KB reference test: IDIQ guaranteed minimum / GAO cases B-302358 and B-308969 | Partial — legal agent not invoked; only compliance check ran | Greg |
| Admin panel: live prompt editing (skills, agent system prompts) | Working | Greg |
| Prompt rollback to base supported | Working | Greg |
| Workspaces concept (different prompt sets per user type) | Prototype shown | Greg |
| Documents panel — inline editing and export | Export button not wired to modal | Greg |
| Notifications panel — document generation events | Working | Greg |
| IGCE for microscope — generated without clarifying questions | Needs fix; should ask type, scope, budget | Greg |

Research optimizer (old Eagle) comparison for IGCE microscope request:
- Immediately asked 3 targeted questions: microscope type (brightfield/fluorescent), quantity, and scope (instrument only vs. accessories/software/training).
- New Eagle did not ask these questions and generated output immediately.
- Greg confirmed: will tune prompts to match this behavior.

### Agent Architecture Discussion (`34:00 – 36:20`)

- Ryan Hash noted that the current structure calls subagents as tools via the supervisor, rather than as a true multiagent handoff.
- Greg confirmed: Bedrock is required for model-agnostic operation; the Strands/BedrockModel approach trades some handoff elegance for flexibility and cost competition.
- Hash agreed this is the right architectural call: "When someone comes in and says Claude's too expensive, Nova's too expensive — I can compete the model and the pricing independent of the actual item."

### Use Case Walkthrough — 15K Microscope (GSA Schedule) (`52:43 – 58:45`)

Jitong Li walked through a test case she ran in the deployed Eagle instance:

- Scenario: $15K microscope, urgent need, GSA schedule available, purchase card holder.
- Eagle asked appropriate clarifying questions (microscope type, quantity, scope).
- Gaps identified:
  - Li's vague GSA answer ("from GSA") caused the system to loop politely — needs better handling of non-specific user input.
  - "Budget line" prompt confused Li — the system expects an accounting string (fund account number), not a dollar amount.
  - Receiving official must differ from requester (purchase card control check) — the system correctly enforced this.
- Ryan Hash's assessment: "An actual purchase card holder who knows how to answer these questions should do better. It's on the right track. This is workable."

### VETS 4212 Compliance Document in Decision Matrix (`40:40 – 50:25`)

Jitong Li flagged that a VETS 4212 compliance document appeared in the decision matrix output for a $170K fixed-price contract. Discussion:

- Hash queried Eagle about VETS 4212 — Eagle retrieved the answer from the HHSPMR Common Requirements document (found in one location in the KB).
- VETS 4212 is a Department of Labor form (contractor responsibility); from a CO perspective it manifests as FAR clauses checked in the solicitation matrix.
- Hash's assessment: the document appearing in the CO-facing matrix is likely an error in the PMR (peer audit checklist) — someone added it without understanding the audience.
- Hash then asked Eagle's policy analyst agent to review the PMR for the VETS thresholds — Eagle returned two specific recommended modifications based on updated threshold policy and notification routing.

### PMR / Knowledge Base Caching Discussion (`50:25 – 52:30`)

- Ryan Hash confirmed he intentionally runs Eagle in a separate browser to avoid session caching against itself.
- The system does maintain a conversation cache within sessions; Hash does not want the system learning from individual user conversations — the KB must be the single source of truth.
- Hash's principle: "The 95% of COs at NIH that only know how to use the hammer — I just don't need the average rank and file private trying to drive the bus."

---

## Decisions Made

- MVP-1 scope remains: acquisition package document generation (SOW, IGCE, AP). No scope expansion.
- Any additional features beyond MVP-1 must align to documentation and justification (e.g., traceability, reports of merit).
- Eagle will use Bedrock for model-agnostic operation; agents are called as tools via the supervisor. This is a deliberate architectural decision.
- Feedback button will surface issues daily to the dev team; QA poking holes is the primary improvement mechanism for the near term.
- Model will be upgraded from lightweight (Haiku) to Sonnet when pushed to the live environment.
- The system will NOT learn from individual conversations — knowledge base updates are the controlled update path.
- A Teams QA chat group ("Eagle QA") will be created to surface GitHub push notifications and QA status.

---

## Action Items

| Item | Owner | Priority | Status |
|------|-------|----------|--------|
| Fix knowledge base invocation — ensure all questions check KB before responding | Greg Black | High | Open |
| Tune system prompts so Eagle asks clarifying questions before generating documents | Greg Black | High | Open |
| Ensure legal agent (not just compliance check) is invoked for legal/case-law questions | Greg Black | High | Open |
| Upgrade live deployment model from Haiku to Sonnet | Greg Black | High | Open |
| Wire export button to document modal | Greg Black | Medium | Open |
| Share live Eagle link with Ryan Hash for independent testing and analysis | Greg Black / Jitong Li | High | Open |
| Create "Eagle QA" Teams chat and connect GitHub push notifications | Greg Black | Medium | Open |
| Send Ryan Hash a calendar link for follow-up meeting (March 6) | Greg Black | Medium | Open |
| Compare MVP-1 use case outputs between old Eagle (research optimizer) and new Eagle | Jitong Li | High | Open |
| Screenshot any old Eagle features that should be replicated in new Eagle and create Jira tickets | Ryan Hash | Medium | Open |
| Share Jitong's 15K microscope test conversation link with Ryan Hash | Jitong Li | Low | Open |
| Ryan Hash to share policy analyst PMR review output with dev team | Ryan Hash | Medium | Open |
| Resolve Greg Black VPN access issue | (IT/Greg) | High | Open |

---

## Technical Notes

### KB Metadata Schema

The Eagle KB uses a two-level metadata structure:
1. **General metadata**: acquisition category, folder path, file pointer
2. **Tags**: drive RAG retrieval — keyed on FAR part numbers, acquisition type names, dollar thresholds, competition types

Tag examples confirmed correct by Ryan Hash:
- Macro purchase: `purchase card`, `13 simplified`, `low dollar`
- Simplified acquisition: `FAR 13`, `SAT`, `350K`, `competition`, `small business set-aside`, `RFQ`
- GSA: `JSA schedule`, `federal supply schedule`, `BPA`

### Architecture: Subagent-as-Tool Pattern

- Strands SDK supervisor calls specialist agents (legal, policy analyst, compliance, document writer, etc.) as discrete tool calls
- This differs from a persistent multiagent handoff but is required for Bedrock model-agnostic operation
- Tradeoff: slightly less elegant handoff, but enables model competition and future cost optimization
- KB access confirmed: no web search in current build; all retrieval is from S3-backed Bedrock Knowledge Base

### KB Reference Test — IDIQ Guaranteed Minimum

Ryan Hash proposed a canonical KB validation test:

> "When must an agency obligate the guaranteed minimum on an IDIQ contract?"

Expected KB-grounded answer cites GAO cases **B-302358** and **B-308969**. In the demo, Eagle invoked only the compliance check subagent and did not call the legal analysis agent. This is a prompt-tuning issue, not a KB content issue.

### HHSPMR Common Requirements Document

Found in Eagle KB; cited for VETS 4212 thresholds. Ryan Hash's policy analyst agent found two recommended modifications:
1. Update threshold values per recent policy changes
2. Adjust notification routing so the correct staff are flagged for specific checklist items

### Web Search / GSA Advantage

- Current build: no web access; all retrieval from KB
- Planned: add web search capability; domains to include `.gov` and `.us`
- Specific use case: GSA Advantage vendor lookup during micro-purchase workflow

---

## MVP Scope Discussion

MVP-1 is defined and confirmed:

**In scope**: Acquisition package document generation
- Statement of Work (SOW)
- IGCE
- Acquisition Plan (AP)
- Supporting justification and traceability documents

**Out of scope for MVP-1**:
- Portfolio management / savings analysis (NIH simplified acquisitions team use case — later phase)
- Policy change propagation to external systems
- KB synchronization with other NIH teams' knowledge bases
- Shared knowledge base with simplified acquisitions team (strategic goal, post-MVP)

**Demo readiness**: Jitong Li will run all MVP-1 use cases (marked in pink in the use case matrix) through old Eagle and compare results with new Eagle to validate parity before demo.

---

## Risks and Blockers

| Risk / Blocker | Description | Severity |
|----------------|-------------|----------|
| Greg Black has no VPN access | Cannot access internal tools (research optimizer, Eagle prod) from local machine | High |
| KB not consistently invoked | Eagle answers general questions from training data rather than KB — produces incorrect or shallow responses | High |
| Insufficient clarifying questions | System generates documents from minimal input rather than gathering required data first | High |
| Lightweight model (Haiku) in demo | Performance gap vs. research optimizer (Sonnet/Opus) misleading during demos | Medium |
| Legal agent not routing correctly | IDIQ guaranteed minimum question did not invoke legal subagent | Medium |
| VETS 4212 in CO-facing decision matrix | Likely an error in PMR checklist — document is a contractor-responsibility form, not a CO deliverable | Medium |
| Session cache conflation | Ryan Hash uses separate browser to avoid KB/conversation cache contamination — risk if other evaluators do not follow same pattern | Low |
| NIH Security Office friction | Ryan Hash's link to Eagle timed out — Craig in the Security office flagged it | Medium |

---

## Next Steps

1. Greg Black to fix KB invocation so all queries route through KB before generating a response.
2. Greg Black to tune system prompts for clarifying-question behavior; use research optimizer behavior as the benchmark (3 targeted questions for IGCE microscope).
3. Greg Black to push live build with Sonnet model and share link with Ryan Hash and Jitong Li.
4. Greg Black to create "Eagle QA" Teams chat; connect GitHub push notifications for build status.
5. Jitong Li to run all MVP-1 use cases (pink items in use case matrix) in both Eagle versions and document delta.
6. Ryan Hash to continue outreach to NIH simplified acquisitions team; target a demo once KB invocation is stable.
7. Ryan Hash to begin drafting agent instructions and prompt improvements; Greg to review and sanity-check.
8. Greg Black to schedule follow-up 1:1 with Ryan Hash on March 6 (morning window, before Ryan's 2 PM meeting).
9. Jitong Li to share 15K microscope test conversation link with Ryan Hash for further analysis.
10. Team to create Jira tickets for any old Eagle features identified by Ryan Hash as missing from new Eagle.

---

*Scribe | 2026-03-09T00:00:00Z | Format: markdown | Type: meeting-notes*
