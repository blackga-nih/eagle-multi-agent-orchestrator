# Eagle QA Session — Meeting Summary

**Recording ID**: 20260306_103818
**Date**: March 6, 2026, 3:38 PM EST
**Duration**: 2h 16m 11s
**Transcription started by**: Valisetty, Srichaitra (NIH/NCI) [C]

---

## Executive Summary

The team conducted a live QA session comparing Eagle's acquisition assistant against the Research Optimizer baseline, running structured knowledge-base and reasoning questions to evaluate agent response quality. Ryan Hash (evaluator/CO) provided domain expert judgment on correctness and completeness while Jitong Li ran the same prompts in Eagle and logged results to a shared Excel tracker. Key findings: KB retrieval and multi-agent routing are functioning well; document generation (SOW, market research report, acquisition plan) produces usable but not fully templatized output that requires user review before progressing; the stage environment KB access was broken during the session, forcing workarounds.

---

## Attendees

| Name | Organization | Role |
|------|-------------|------|
| Hash, Ryan | NIH/NCI | Contracting Officer / Domain Evaluator [E] |
| Black, Gregory | NIH/NCI | Lead Developer / Tech Lead [C] |
| Li, Jitong (Ingrid) | NIH/NCI | QA Tester / Analyst [C] |
| Valisetty, Srichaitra | NIH/NCI | Scribe / Participant [C] |

`[C]` = Contractor `[E]` = Evaluator

---

## Key Discussion Points

### 1. QA Methodology Setup (0:00 – 2:00)

- Team agreed to record Research Optimizer answers in Column C of an existing Excel tracker alongside Eagle answers, using fresh browser sessions for each question set.
- Ryan committed to asking his Research Optimizer model the exact same questions in brand-new chats to ensure a clean comparison baseline.
- Greg emphasized saving chat snapshots via the feedback mechanism so the team can reference responses without manual copy-paste.

### 2. Stage Environment KB Access Broken (2:00 – 5:00)

- Ryan opened Eagle in the stage environment and immediately discovered KB access was non-functional: "stage KB access is broken in my prototype."
- He attempted Firefox as a third isolated browser environment to avoid clearing his dev workspace, which had live acquisition work in progress.
- Firefox failed to load the site entirely.
- Jitong ran the questions in Eagle (dev environment) instead, which Ryan confirmed was equivalent for these tests.

### 3. First Baseline Questions — KB Retrieval Tests (5:00 – 18:00)

- **Question 1 (compliance/threshold)**: Eagle invoked Financial and Legal specialist agents. Ryan rated the agent routing correct; compliance specialist is expected to activate on nearly all acquisitions.
- **Question 2 (FAR 16.505 fair opportunity exceptions)**: Eagle returned a comprehensive answer covering all six exceptions (urgency, logical follow-on, minimum guarantee, etc.) plus documentation requirements, approval levels, posting requirements, and protest exposure. Ryan noted the response was "more than it needs to be" but content was correct; Research Optimizer gave a simpler enumerated answer.
- Ryan explained the domain context: fair opportunity exceptions apply to IDIQ task orders and govern when a single-award is permissible.
- Team agreed that showing KB source documents in-line (as Research Optimizer does) is not necessary — users can ask follow-up questions to drill into sources.

### 4. Agent Routing Behavior and Supervisor Design (8:00 – 12:00)

- Compliance specialist was observed activating on all questions, which Ryan assessed as expected ("Compliance is pretty much gonna get called on everything").
- Ryan articulated the supervisor-as-orchestrator design rationale: the supervisor manages the CO as one node in a workflow, calling specialists (small business, legal, IT, etc.) only when needed, analogous to how a CO coordinates SMEs on a real acquisition.
- Greg confirmed this approach is correct and noted growing model context windows reduce compaction concerns.

### 5. Complex Cross-Document Reasoning Question — SBIR Debriefing Scenario (18:00 – 23:00)

- Ryan introduced a question that crosses three FAR sections: pre-award vs. post-award debriefing election, SBIR-specific rules, and protest window mechanics.
- Eagle invoked Legal → Compliance → Legal (multiple passes), then produced a structured answer covering: problem analysis, pre/post-award choice mechanics, window expiration logic, and procedure sequence.
- Ryan rated the response correct. He noted SBIR contracts are Phase I fixed-price with potential Phase II follow-on and represent an area with limited CO familiarity — good test of KB depth.
- Result: **PASS**. No documents generated for this Q&A question.

### 6. Full Acquisition Package — Cloud Hosting Use Case (28:00 – 55:00)

- Jitong ran Ronnie Olpes' use case: "I am a CO at NCI responsible for the acquisition of cloud hosting services. Value is $750K."
- Eagle produced a comprehensive initial assessment including: no subcontracting plan needed (commercial item), no certified cost/pricing data required, GSA cloud computing vehicle recommended, NITAC noted but flagged as going away with protest history, cloud-specific IT requirements invoked, FedRAMP/data classification questions raised.
- Ryan rated the routing and content **correct**, calling the cloud scenario "a really good example" for hitting multiple specialist domains simultaneously.
- Eagle flagged a contradiction in Jitong's test inputs: "no incumbent" + mention of Amazon triggered the system to ask for clarification on continuation vs. novel contract — Ryan praised this as correct behavior.
- Eagle then generated a draft SOW in `.docx` format using the KB template, without being explicitly prompted to do so.

### 7. Generated SOW Review (34:00 – 47:00)

- Ryan reviewed the downloaded `.docx`: structure and headings broadly correct; "Personal Qualifications" section included but marked "Not Applicable" (unnecessary); delivery schedule table format mixed up contract schedule vs. delivery schedule.
- Assessment: "Not bad. Not robust but using the correct baseline." Rated as a usable starting point for an experienced CO.
- Two SOW templates exist in the KB: v1 and v2. Ryan confirmed v2 is canonical (added key personnel placeholders); v1 should be archived.
- Team agreed the KB needs a cleanup pass to remove duplicate/conflicting template versions.

### 8. Document Validation and Workflow Loop (43:00 – 1:07:00)

- Ryan raised a gap: Eagle generated the SOW without prompting the user to verify it before moving to the next document. He stated that every generated document should include a confirmation checkpoint: "Here is my draft SOW. Do you want to accept this and move on, or do you have changes?"
- Greg agreed and proposed adding a validation step at the end of the `generate_sow` command.
- The team discussed the iterative document loop: SOW drives IGCE; if IGCE exceeds budget, the SOW must be revised — the "CarMax balloon" problem. Documents must be treated as coupled drafts, not sequential outputs.
- Ryan articulated the core acquisition workflow constraint: Eagle must capture the "three walls of the box" before generating any document — budget ceiling, delivery timeline, and must-haves vs. nice-to-haves. Greg identified this as a candidate for the system prompt.
- Greg summarized the design principle: "A little more direction and context is needed before we're generating documents. Keep the front-end questions short but sweet."

### 9. Market Research Report and Acquisition Plan Review (1:07:00 – 1:27:00)

- Eagle generated both the market research report and acquisition plan in the same pass (streamlined flow), which Ryan confirmed was correct behavior given the information already provided.
- Jitong compared the market research output to the FY26 streamlined market research report template. Formatting issues identified: sub-bullets flattened, checkbox/table fields not populated correctly, some sections blank.
- Ryan: content accuracy is more important than formatting at this stage; template templatization (double-brace variable injection) is the long-term solution but is a separate effort.
- Research Optimizer uses double-brace variable syntax (e.g., `{{acquisition_title}}`) with a separate definition block; Ryan identified this as the pattern to adopt for Eagle document generation.
- Ryan flagged that all template documents are under active sweeping revision by NIH policy teams due to administration-mandated regulation reduction. Templatizing documents that may be eliminated in two weeks is low priority.

### 10. KB Governance and Template Management (54:00 – 1:02:00)

- Discussion on who can and cannot modify KB templates. Ryan's position: COs should be able to see all KB files (transparency) but only admins should modify shared templates. Personal workspace customizations (e.g., a user's own SOW variant) are acceptable.
- Certain documents (acquisition plan, sole source justification structured per FAR 7.105) are regulatory in nature and cannot be modified regardless of user preference — the form follows the FAR section directly.
- Ryan is engaging NCI policy teams to use Eagle as a tool for consolidating and cleaning up their own policy library, which would give Eagle first access to authoritative templates.
- Greg proposed a future feature: visual KB browser so users can inspect what documents exist in the knowledge base.

### 11. Plain Language and "Shall vs. Must" (38:00 – 39:30)

- Sidebar on a mandatory plain language training Ryan completed that morning. He noted a critical acquisition knowledge point at risk as the workforce turns over: "shall" in a contract means the contractor is absolutely bound; "must" does not carry the same legal weight. Models that silently swap these terms create liability.
- Ryan generated a Lambda-based plain language checker from the training transcript as a concept for a post-generation tool call.

### 12. VPN / Access Status (1:18:00 – 1:19:00)

- VPN access for the contractor team was confirmed as submitted, pending AO approval.
- Ryan confirmed the approver was showing as active/online, indicating quick turnaround was possible.

### 13. Meeting Cadence (1:27:00 – 1:29:00)

- Greg proposed moving from weekly requirements calls to daily or at least 3x/week QA sessions.
- Ryan confirmed full availability; flagged telework Wed–Thu next week, out Friday.
- Greg will update the calendar invite; one-on-ones also offered.

---

## Decisions Made

- Research Optimizer answers will be captured in Column C of the shared Excel QA tracker alongside Eagle answers for side-by-side comparison.
- SOW template v2 is canonical; v1 should be archived.
- Every document generation flow must include a user confirmation checkpoint before advancing to the next document.
- The "three walls of the box" constraint capture (budget ceiling, delivery timeline, must-haves) will be added to the system prompt or early workflow before document generation begins.
- Template templatization (double-brace variable injection matching Research Optimizer's pattern) is the target approach for document formatting, but is deferred pending KB template stabilization.
- All KB template changes must follow a governed process; personal workspace customizations are acceptable without process overhead.
- Formatting defects in generated documents (checkbox fields, table layout) are acceptable at this stage; content accuracy is the priority.
- Meeting cadence will increase to approximately 3x/week; Greg will reschedule the recurring invite.

---

## Action Items

| Item | Owner | Priority | Status |
|------|-------|----------|--------|
| Share QA Excel tracker to SharePoint for team collaboration | Jitong Li | High | Open |
| Add user confirmation/validation checkpoint to `generate_sow` command | Greg Black | High | Open |
| Add "three walls of the box" constraint capture to system prompt or early workflow | Greg Black | High | Open |
| Investigate and fix stage environment KB access (KB unreachable) | Greg Black | High | Open |
| Archive SOW template v1; confirm v2 as the single canonical template | Ryan Hash | Medium | Open |
| Full review of all document templates to confirm correct population behavior | Jitong Li / Greg Black | Medium | Open |
| Improve chat UI to match Research Optimizer output quality; push deployment to QA app | Greg Black | High | In Progress |
| Investigate document generation tool (double-brace variable injection); coordinate with Alvi | Greg Black | Medium | Open |
| Research Optimizer "three walls" prompt text shared to team chat for system prompt consideration | Ryan Hash | Medium | Done |
| KB cleanup: identify and remove duplicate/conflicting template files | Ryan Hash | Medium | Open |
| Engage NIH policy teams to present Eagle for KB consolidation effort | Ryan Hash | Medium | In Progress |
| Update recurring meeting calendar invite to 3x/week cadence | Greg Black | Low | Open |
| VPN access AO approval follow-up | Ryan Hash | High | Pending AO |

---

## QA Test Results

| # | Question / Scenario | Agents Invoked | KB Hit? | Ryan's Assessment |
|---|--------------------|-----------------|---------|--------------------|
| 1 | Threshold/compliance screening question | Financial, Legal, Compliance | Yes | PASS — correct routing |
| 2 | FAR 16.505 fair opportunity exceptions | Compliance, Financial | Yes | PASS — comprehensive; slightly over-explained vs. Research Optimizer |
| 3 | Pre/post-award debriefing election; SBIR-specific rules; protest window (cross-document) | Legal, Compliance (multiple passes) | Yes | PASS — correct analysis; window expiration and procedure sequence accurate |
| 4 | Cloud hosting acquisition ($750K): full package (SOW, market research, AP) | Financial, Compliance, IT/Cloud domain reasoning | Yes | PASS on content; PARTIAL on document output — SOW usable; market research report and AP have formatting/population gaps |

**Note**: Stage environment KB was non-functional during the session; all tests run against dev environment.

---

## Technical Notes

### Architecture Observations

- The Compliance specialist activates on nearly all acquisitions by design — mirrors the role of a CO who always involves legal/compliance SMEs. This is expected behavior, not an over-triggering bug.
- Multi-pass agent routing (Legal → Compliance → Legal) for complex questions reflects the supervisor correctly delegating iterative reasoning across specialists.
- The supervisor-as-orchestrator pattern (as opposed to a "chatty CO" model) was validated by Ryan as the correct design. The CO agent acting as a generalist produced verbose, unfocused output; the supervisor calling specialists on demand produces better workflow results.

### Model Behavior Observations

- Ryan noted a change in Anthropic Claude behavior compared to prior sessions — tool call display changed, web access appeared disabled. Greg confirmed Anthropic pushed a backend change; same was visible in his coding terminal.
- Model occasionally produces reasoning output without a final answer (appears to finish but produces no visible response). Workaround: user types "you forgot the output" and the model completes the response. This is a UX gap to address.
- Eagle correctly flagged a user input contradiction (no incumbent + Amazon mentioned) and requested clarification — this is the desired proactive behavior.

### Document Generation

- Eagle generated a `.docx` SOW without being prompted, using the v2 template from the KB. Formatting was approximately correct; content was directionally right but required review.
- Market research report had checkbox and table population failures — sections 5–8 (market research findings) appeared blank or incorrectly structured.
- Research Optimizer uses a double-brace variable injection pattern for document templates (e.g., `{{acquisition_title}}` with a companion definition block). This is the target pattern for Eagle to adopt.
- Plain language filtering (e.g., "shall" vs. "must" enforcement) was identified as a candidate post-generation tool call.

### Deep Research / Reasoning Toggle

- Greg is investigating what "deep research mode" toggles under the hood; current plan is to enable it by default.
- Proposal: admin users see full reasoning chain; standard CO users see final response only. This is implementable.

---

## Comparison with Research Optimizer

| Dimension | Eagle (current) | Research Optimizer |
|-----------|----------------|-------------------|
| KB retrieval | Working; multi-agent routing correct | Working |
| Answer comprehensiveness | Comparable; sometimes more detailed | Concise enumerated answers |
| Source document display | Not shown inline | Shows source document chunks |
| Document generation format | `.docx`; structure correct; population gaps | `.docx`; better variable injection via double-brace |
| Document confirmation checkpoint | Missing — jumps to next step | Not observed |
| Stage environment stability | KB broken during session | N/A |
| Clarification / contradiction detection | Active (caught incumbent/Amazon conflict) | Not directly compared |

Research Optimizer generates market research reports and acquisition plans with cleaner template population. The content crafter tool uses double-brace placeholder syntax with a definition layer that instructs the model how to fill each field. Eagle's document output quality is the primary gap relative to Research Optimizer at this point.

---

## Risks and Blockers

| Risk / Blocker | Severity | Notes |
|----------------|----------|-------|
| Stage environment KB access broken | High | All QA defaulted to dev; stage must be fixed before broader testing |
| Document templates under sweeping NIH-wide revision | Medium | Investing heavily in current template templatization may be wasted work; coordinate with Ryan on timeline |
| Missing user confirmation checkpoint in document flow | High | Risk of CO accepting incorrect documents without review; must be added before user-facing demos |
| No constraint capture before document generation | High | Eagle currently jumps to document output without knowing budget ceiling, timeline, must-haves; produces rescoping loops |
| VPN access not yet approved | Medium | Blocks some contractor access to shared environments; pending AO approval |
| Duplicate/conflicting KB template files | Medium | Model may pull wrong template version; v1/v2 SOW conflict unresolved until archived |
| Knowledge attrition risk (shall vs. must, etc.) | Low/Long-term | Legal terminology nuances will not be caught if neither the model nor the user knows them; noted as a systemic risk for the profession |

---

## Next Steps

1. **Greg (today)**: Full dev day focused on improving chat UI to match Research Optimizer output quality; push stable deployment to QA app for team testing.
2. **Greg (this sprint)**: Add "three walls of the box" constraint capture to early workflow; add SOW confirmation checkpoint; investigate document generation tool with Alvi.
3. **Jitong**: Share QA Excel tracker to SharePoint; continue running use case questions and logging results.
4. **Ryan**: Archive SOW v1; share Research Optimizer "three walls" prompt to team chat; continue engaging NIH policy teams on KB consolidation.
5. **Team**: Target for end of next week — full acquisition package (SOW + market research report + acquisition plan) with clarifying questions, downloadable documents, formatted correctly.
6. **Greg**: Reschedule recurring call to avoid standup conflict; increase cadence to ~3x/week.

---

*Scribe | 2026-03-09T05:16:31Z | Format: MARKDOWN | Type: meeting-notes*
