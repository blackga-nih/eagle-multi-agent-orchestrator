# New EAGLE Jira Items — 2026-03-10

> Prepared for sprint planning. Covers completed work from `feat/observability-tabs`, `feat/intake-live-compliance`, and `fix/fast-path-kb-tools` branches, plus new stories from the March 10 QA session with Ryan Hash (COR/SME).

---

## Completed Stories (Done 2026-03-10)

### EAGLE-{42}: SSE Streaming Migration to Strands stream_async()

- **Type**: Story
- **Epic**: [EAGLE-22] Technical Configuration
- **Summary**: Migrated SSE pipeline to Strands stream_async(), eliminated two-queue architecture
- **Status**: Done
- **Assignee**: `assignee:greg`
- **Expert Domain**: `sse`, `backend`, `strands-sdk`
- **PR**: [CBIIT/sm_eagle#21](https://github.com/CBIIT/sm_eagle/pull/21) (`fix/fast-path-kb-tools`)
- **Commits**: `74616de`, `e08cc09`, `de33e01`, `fda8a17`, `a4a2025`
- **Description**: Replaced the legacy two-queue SSE architecture with direct `stream_async()` consumption from Strands Agents SDK. Added full tool observability — every tool_use and tool_result now emits SSE events. Converted standalone tools (load_data, compliance, skills) to factory pattern for proper tool_result emission. Added fast-path routing for knowledge base tools and fixed threshold logic.
- **Acceptance Criteria**:
  - [x] stream_async() yields text, tool_use, and tool_result events
  - [x] All standalone tools emit tool_result SSE events
  - [x] Fast-path routing works for knowledge tools
  - [x] No regression in streaming chat behavior

---

### EAGLE-{43}: Full Tool Observability — Activity Panel, Tool Cards, Streaming Enhancements

- **Type**: Story
- **Epic**: [EAGLE-22] Technical Configuration
- **Summary**: Added activity panel with agent logs, tool-use cards, and streaming telemetry to chat UI
- **Status**: Done
- **Assignee**: `assignee:greg`
- **Expert Domain**: `frontend`, `sse`
- **Commits**: `6c31925`, `bb3ef3d`
- **Description**: Built the right-side activity panel with five tabs: Documents, Notifications, Agent Logs, Bedrock, CloudWatch. Each tab shows real-time events from the SSE stream. Agent Logs show tool_use/tool_result cards with formatted detail modals (90vw wide). Added E2E test specs for greeting fast-path, acquisition package flow, and SSE metadata events. Created dev process scripts for zombie management.
- **Acceptance Criteria**:
  - [x] Activity panel renders with 5 tabs
  - [x] Agent Logs show tool_use and tool_result events
  - [x] Click-to-expand modal works (Escape to close)
  - [x] E2E tests pass for greeting fast-path

---

### EAGLE-{44}: Raw Bedrock Trace Events + CloudWatch Logs Tab

- **Type**: Story
- **Epic**: [EAGLE-22] Technical Configuration
- **Summary**: Added bedrock_trace SSE event type and CloudWatch logs tab with user-scoped filtering
- **Status**: In Progress
- **Assignee**: `assignee:greg`
- **Expert Domain**: `sse`, `frontend`, `backend`, `cloudwatch`
- **Branch**: `feat/observability-tabs`
- **Description**: Added `BEDROCK_TRACE` event type to the stream protocol. Backend now yields raw Bedrock ConverseStream events (contentBlockStart, contentBlockDelta, messageStop, metadata/usage) through the SSE pipeline via `_sanitize_event()`. Frontend Bedrock tab classifies and renders raw events with category badges. CloudWatch tab fetches logs filtered by session_id and user_id via `/api/logs/cloudwatch` Next.js route. Fixed CloudWatch auth by adding `AWS_PROFILE=eagle` to `.env.local`.
- **Acceptance Criteria**:
  - [x] bedrock_trace events emitted from backend
  - [x] Bedrock tab classifies raw ConverseStream events
  - [x] CloudWatch tab fetches and displays logs
  - [ ] CloudWatch auth works after frontend restart
  - [ ] Browser validation of full pipeline

---

### EAGLE-{45}: Live Compliance Check on Every Intake Turn

- **Type**: Story
- **Epic**: [EAGLE-3] UC-1 Create an acquisition package
- **Summary**: Mandated live compliance check on every intake turn via supervisor prompt
- **Status**: Done
- **Assignee**: `assignee:greg`
- **Expert Domain**: `backend`, `strands-sdk`
- **PR**: (`feat/intake-live-compliance`)
- **Commits**: `f7c1d55`
- **Description**: Updated supervisor agent prompt to run compliance validation on every intake turn, not just when explicitly requested. This ensures the checklist stays current as new information is gathered, catching issues early rather than at package assembly time.
- **Acceptance Criteria**:
  - [x] Compliance check fires on every intake turn
  - [x] Checklist state updates in real-time
  - [x] No regression in response time (< 30s overhead)

---

### EAGLE-{46}: Feedback System with Teams Integration

- **Type**: Story
- **Epic**: [EAGLE-22] Technical Configuration
- **Summary**: Added Ctrl+J feedback modal with conversation snapshot capture
- **Status**: Done
- **Assignee**: `assignee:greg`
- **Expert Domain**: `frontend`, `backend`
- **Commits**: `b6f4bc5`
- **Description**: Built feedback modal (Ctrl+J) that captures conversation snapshot, current page, and message ID. Notifications appear in the activity panel. Teams webhook integration configured for the feedback channel.
- **Acceptance Criteria**:
  - [x] Ctrl+J opens feedback modal
  - [x] Feedback captures conversation context
  - [x] Notification appears in activity panel

---

## New Epic

### EAGLE-54: Intake Flow Optimization (QA Session 2026-03-10)

- **Type**: Epic
- **Summary**: Improve intake flow based on QA comparison with legacy Eagle — staging, recommendations, output quality
- **Status**: To Do
- **Assignee**: `assignee:greg`
- **Description**: From the March 10 QA session, Ryan Hash (COR/SME) and Ingrid Li (QA) compared legacy Eagle against new EAGLE across two use cases (micro purchase, $750K negotiated contract). Legacy Eagle outperformed on: vehicle recommendations, output conciseness, and post-purchase guidance. This epic tracks all intake flow improvements needed to close the gap. Source: `docs/development/meeting-transcripts/20260310-eagle-qa/20260310-180400-meeting-eagle-qa-v1.md`

---

## New Stories

### EAGLE-55: Staged Checklist — Pizza Tracker Model

- **Type**: Story
- **Epic**: [EAGLE-54] Intake Flow Optimization
- **Summary**: Break intake checklist into three progressive stages instead of showing all items at once
- **Status**: To Do
- **Priority**: P1
- **Effort**: L
- **Assignee**: `assignee:greg`
- **Expert Domain**: `backend`, `frontend`
- **Description**: Ryan's "pizza tracker" analogy — users need a sense of accomplishment and progression. Stage 1: basic intake (pathway determination). Stage 2: required documents for confirmed path. Stage 3: special/late-emerging documents. Never show 1,000 items. Only surface what's relevant to the current stage. Each stage gates on completion of the prior one.
- **Acceptance Criteria**:
  - [ ] Checklist renders in 3 distinct stages
  - [ ] Stage 2 only appears after pathway is confirmed
  - [ ] Stage 3 items emerge based on document generation / milestone triggers
  - [ ] Users see progress indicator (X/Y complete per stage)

---

### EAGLE-56: Ranked Vehicle/Mechanism Recommendations

- **Type**: Story
- **Epic**: [EAGLE-54] Intake Flow Optimization
- **Summary**: Show ranked acquisition vehicle recommendations with reasoning, matching legacy Eagle
- **Status**: To Do
- **Priority**: P1
- **Effort**: M
- **Assignee**: `assignee:greg`
- **Expert Domain**: `backend`, `strands-sdk`
- **Description**: Legacy Eagle shows top recommendation plus alternatives with pros/cons. New EAGLE currently defaults to a single path (e.g., Part 15 open market for a $750K cloud purchase when GSA/NITAAC would be better). Must present: (1) recommended vehicle with reasoning, (2) 2-3 alternatives with brief pros/cons, (3) allow user to select before proceeding. Ryan: "Giving them a 'this is what I think is my recommended solution and why' and 'these are other applicable solutions to consider and why.'"
- **Acceptance Criteria**:
  - [ ] Response includes top recommendation with reasoning
  - [ ] 2-3 alternatives listed with brief pros/cons
  - [ ] User can select preferred vehicle before doc generation begins
  - [ ] Micro purchases skip this (direct path)

---

### EAGLE-57: Fix Micro Purchase Document Output

- **Type**: Bug
- **Epic**: [EAGLE-54] Intake Flow Optimization
- **Summary**: Micro purchase flow generates SOW incorrectly — should produce purchase card transaction form
- **Status**: To Do
- **Priority**: P1
- **Effort**: M
- **Assignee**: `assignee:greg`
- **Expert Domain**: `backend`, `strands-sdk`
- **Description**: QA found that micro purchases ($14K microscope) incorrectly generate a SOW with scope sections. For micro purchases, the only required output is: (1) statement of need, (2) price reasonableness determination, (3) purchase card transaction documentation. Also missing: priority sources check (BPA/mandatory sources), post-purchase steps (delivery verification, property accountability). Ryan confirmed: "For micro purchases you do not need a SOW. You just need to say why you need it."
- **Acceptance Criteria**:
  - [ ] Micro purchases produce purchase card transaction form, not SOW
  - [ ] Price reasonableness determination generated correctly
  - [ ] Priority sources check included (BPA, mandatory sources)
  - [ ] Post-purchase steps listed (delivery, accountability)

---

### EAGLE-58: Reduce Response Verbosity — Show Only What Matters Now

- **Type**: Story
- **Epic**: [EAGLE-54] Intake Flow Optimization
- **Summary**: Only show "what was accomplished" and "what to do next" — suppress noise like FAR 8.8
- **Status**: To Do
- **Priority**: P1
- **Effort**: M
- **Assignee**: `assignee:greg`
- **Expert Domain**: `backend`, `strands-sdk`
- **Description**: Ryan: "What I just figured out is important. What you need to do right now is important. Less important is where we think we're gonna go after that." Every response should include: (1) confirmation of what was just resolved/checked off, (2) next required action. Must suppress: full compliance flag lists, noise clauses (FAR 8.8 printing services, Kaspersky/Huawei checks for irrelevant purchases), CPARS at intake stage, timeline estimates that will be overridden by CO.
- **Acceptance Criteria**:
  - [ ] Each response includes "what was accomplished" section
  - [ ] Each response includes clear "next step" action
  - [ ] Compliance noise suppressed (only show relevant flags)
  - [ ] No fabricated timeline dates

---

### EAGLE-59: Baseline Intake Questions — Ask Upfront Before AI Analysis

- **Type**: Story
- **Epic**: [EAGLE-54] Intake Flow Optimization
- **Summary**: Always ask 4-6 baseline questions at start: new vs existing, baseline docs, role, budget range
- **Status**: To Do
- **Priority**: P1
- **Effort**: S
- **Assignee**: `assignee:greg`
- **Expert Domain**: `backend`, `strands-sdk`
- **Description**: Ryan: "Those are the basic questions that you want to get at." Before any AI analysis, gather: (1) Is this new, follow-on, or recompete? (2) Do you have current drafts or baseline documents? (3) What is your role (COR, requester, purchase card holder)? (4) Budget range / rough order of magnitude. (5) Timeline constraints (end of FY, etc.). These answers determine the acquisition pathway before any document generation begins.
- **Acceptance Criteria**:
  - [ ] First response always includes baseline questions
  - [ ] Pathway determination fires after baseline answers received
  - [ ] "Purchase card holder" doesn't trigger irrelevant budget line questions
  - [ ] Existing docs can be uploaded as starting point

---

### EAGLE-60: Fix Document Template Routing

- **Type**: Bug
- **Epic**: [EAGLE-54] Intake Flow Optimization
- **Summary**: Ensure correct document template is pulled per acquisition type — currently outputs wrong formats
- **Status**: To Do
- **Priority**: P1
- **Effort**: M
- **Assignee**: `assignee:greg`
- **Expert Domain**: `backend`, `strands-sdk`
- **Description**: QA found that document generation pulls incorrect templates or fabricates form layouts instead of using stored templates. The system should: (1) identify which template is needed based on acquisition type, (2) pull the actual template from the knowledge base, (3) populate atomic-level fields from conversation context, (4) not invent sections that don't exist in the real form. Ryan: "It definitely tries to take shortcuts all the time and just make up what it thinks the form should look like instead of trying to fill out the form."
- **Acceptance Criteria**:
  - [ ] create_document tool maps to correct KB template per doc type
  - [ ] Generated doc matches template structure (not fabricated)
  - [ ] Atomic fields populated from session context
  - [ ] PWS template available when needed (Ryan to source)

---

### EAGLE-61: Quick Form Cards in Chat for Intake Questions

- **Type**: Story
- **Epic**: [EAGLE-54] Intake Flow Optimization
- **Summary**: Add clickable form cards in chat for structured intake questions — faster than free-text
- **Status**: To Do
- **Priority**: P2
- **Effort**: L
- **Assignee**: `assignee:greg`
- **Expert Domain**: `frontend`, `backend`
- **Description**: Greg: "I love being able to click through really fast instead of typing it all out." Render structured form cards in the chat stream for yes/no, multiple choice, and short-answer intake questions. User clicks through 5-13 questions, AI analyzes answers to determine starting pathway. Ryan: "A few clicks, then they kind of get a starting point." This replaces multi-turn back-and-forth with a compact, guided experience.
- **Acceptance Criteria**:
  - [ ] Form cards render in chat stream (not a separate page)
  - [ ] Support: radio buttons, checkboxes, short text, dropdowns
  - [ ] Submit triggers pathway analysis
  - [ ] Experienced users can skip and type freely instead

---

### EAGLE-62: Defer Document Generation Until Path Confirmed

- **Type**: Story
- **Epic**: [EAGLE-54] Intake Flow Optimization
- **Summary**: Collect atomic-level information first, assemble documents only on user request
- **Status**: To Do
- **Priority**: P2
- **Effort**: M
- **Assignee**: `assignee:greg`
- **Expert Domain**: `backend`, `strands-sdk`
- **Description**: Don't auto-generate documents mid-conversation. Collect all required data points (atomic fields) through the intake flow, store them as structured metadata, and only assemble documents when the user explicitly requests them or when the acquisition path is confirmed. Ryan: "Keep going and then when they wanna see the files or assemble the package at the end, then they can review it."
- **Acceptance Criteria**:
  - [ ] No auto-generation of docs during intake
  - [ ] Atomic data stored as session metadata
  - [ ] User can request doc generation at any point
  - [ ] Package assembly uses stored atomic data

---

### EAGLE-63: Upgrade Backend Model

- **Type**: Task
- **Epic**: [EAGLE-22] Technical Configuration
- **Summary**: Upgrade Bedrock model to latest available Claude version
- **Status**: To Do
- **Priority**: P1
- **Effort**: S
- **Assignee**: `assignee:greg`
- **Expert Domain**: `backend`, `aws`
- **Description**: Ryan requested model upgrade during QA session. Greg approved. Update `MODEL` constant in `strands_agentic_service.py` and verify Bedrock access for the new model ID. Test with both micro purchase and large contract use cases to confirm quality improvement.
- **Acceptance Criteria**:
  - [ ] Model upgraded in backend config
  - [ ] Bedrock access confirmed for new model
  - [ ] QA re-run on both use cases shows improvement

---

### EAGLE-64: Add PWS Template to Knowledge Base

- **Type**: Task
- **Epic**: [EAGLE-54] Intake Flow Optimization
- **Summary**: Source or create a Performance Work Statement template for the knowledge base
- **Status**: To Do
- **Priority**: P2
- **Effort**: S
- **Assignee**: `assignee:greg`
- **Expert Domain**: `backend`
- **Description**: Ryan noted: "I don't think I have a specific PWS template. I might need to find one of those." Currently the KB has SOW templates but no PWS template, which caused incorrect doc generation when PWS was selected. Ryan will source/create the template; Greg will add it to the S3 knowledge base and verify it's retrievable by the document generation tool.
- **Acceptance Criteria**:
  - [ ] PWS template uploaded to S3 knowledge base
  - [ ] Template retrievable by create_document tool
  - [ ] PWS generation produces correct structure

---

## Summary

### Completed This Sprint

| Key | Summary | Status | Commits |
|-----|---------|--------|---------|
| EAGLE-{42} | SSE streaming migration to Strands stream_async() | Done | `74616de` `e08cc09` `de33e01` `fda8a17` `a4a2025` |
| EAGLE-{43} | Activity panel + tool observability | Done | `6c31925` `bb3ef3d` |
| EAGLE-{44} | Bedrock traces + CloudWatch logs tab | In Progress | (feat/observability-tabs) |
| EAGLE-{45} | Live compliance check on every intake turn | Done | `f7c1d55` |
| EAGLE-{46} | Feedback system + Teams integration | Done | `b6f4bc5` |

### Open — Priority Order

| Priority | Key | Summary | Effort |
|----------|-----|---------|--------|
| P1 | EAGLE-55 | Staged checklist (pizza tracker) | L |
| P1 | EAGLE-56 | Ranked vehicle recommendations | M |
| P1 | EAGLE-57 | Fix micro purchase document output | M |
| P1 | EAGLE-58 | Reduce response verbosity | M |
| P1 | EAGLE-59 | Baseline intake questions upfront | S |
| P1 | EAGLE-60 | Fix document template routing | M |
| P1 | EAGLE-63 | Upgrade backend model | S |
| P2 | EAGLE-61 | Quick form cards in chat | L |
| P2 | EAGLE-62 | Defer doc generation until confirmed | M |
| P2 | EAGLE-64 | Add PWS template to KB | S |

**S** = small (< 1 day), **M** = medium (1-2 days), **L** = large (3-5 days)

---

*Generated: 2026-03-10 · Source: QA session transcript + git log (7 days) · Branch: feat/observability-tabs*
