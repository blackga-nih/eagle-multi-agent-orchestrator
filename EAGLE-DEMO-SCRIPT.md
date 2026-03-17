# EAGLE Acquisition Package Demo Script

**Date:** Friday, March 21, 2026
**Duration:** ~20 minutes
**Frontend URL:** http://localhost:3000
**Backend URL:** http://localhost:8000
**Model:** Claude Haiku 4.5 via Bedrock (configurable in `.env`)

---

## MVP1 Success Criteria

The demo is successful if the following end-to-end capabilities are demonstrated:

1. **Intelligent Intake** -- EAGLE asks clarifying questions and collects all required acquisition details (value, contract type, competition strategy, period of performance) through natural conversation via the Strands SDK supervisor agent
2. **Specialist Agent Routing** -- Supervisor delegates to specialist subagents (OA Intake, Legal Counsel, Market Intelligence, Compliance Strategist, Tech Translator, Document Generator) based on request context
3. **Compliance Matrix** -- Deterministic FAR/DFARS threshold detection, required documents list, and compliance flags auto-determined from intake data (no hallucinated thresholds)
4. **Document Generation** -- All 4 required documents (SOW, IGCE, Market Research, Acquisition Plan) are generated as NCI-branded PDF/DOCX with DRAFT watermarks
5. **Document Revision** -- A previously generated document can be revised with new requirements, producing a new version (v2) while preserving the original
6. **Package Export** -- The complete package downloads as a ZIP containing all documents (3 formats each: .md, .pdf, .docx) plus a manifest.json
7. **Admin Observability** -- Dashboard, skills, templates, Langfuse traces, and cost tracking pages all render with live data from the demo session
8. **Session Persistence** -- Conversation history persists in DynamoDB; closing and reopening the browser resumes the session

---

## Use Cases Covered (Excel MVP1 Cross-Reference)

| Demo Step | Excel UC | Jira | Description | Agent Role |
|-----------|----------|------|-------------|------------|
| Steps 2-4 | UC-1 | EAGLE-16 | New IT Services Acquisition -- $750K full package | SUPERVISOR |
| Steps 5-6 | UC-1 | EAGLE-8 | Document generation (SOW, IGCE, MR, AP) as NCI-branded PDF/DOCX | DOCUMENT GENERATOR |
| Step 7 | UC-1 | EAGLE-8 | Package card with pathway badge and progress tracking | WORKFLOWS |
| Step 8 | UC-1 | EAGLE-8 | Document revision -- SOW v2 with new requirements | DOCUMENT GENERATOR |
| Step 9 | UC-1 | EAGLE-10 | Package export as ZIP (12 files + manifest.json) | EXPORT |
| Steps 10-12 | -- | EAGLE-22, EAGLE-44 | Admin dashboard, Langfuse traces, skills, templates | ADMIN |
| Step 13 (optional) | UC-2.1 | EAGLE-15 | Micro purchase -- $14K lab supplies fast path | SUPERVISOR |
| Step 14 (optional) | UC-3 | EAGLE-27 | Sole source -- $280K software maintenance | SUPERVISOR |

---

## Pre-Demo Checklist

### 1. Refresh AWS credentials
```bash
aws sso login --profile eagle
```

### 2. Start backend (if not running)
```bash
cd ~/Desktop/eagle/sm_eagle/server
AWS_PROFILE=eagle uvicorn app.main:app --reload --port 8000
```

### 3. Start frontend (if not running)
```bash
cd ~/Desktop/eagle/sm_eagle/client
npm run dev
```

### 4. Verify health
```bash
curl -s http://localhost:8000/api/tools | python -m json.tool | head -5
```
Expected: JSON with tool definitions (compliance_query, search_far, create_document, etc.)

### 5. Verify Langfuse connectivity
```bash
curl -s -u "pk-lf-...:sk-lf-..." https://us.cloud.langfuse.com/api/public/traces?limit=1
```
Expected: `{"data":[...],"meta":{...}}`

---

## Demo Flow (14 steps)

### Act 1: Intelligent Intake (UC-1, EAGLE-16)

#### Step 1: Open Chat UI

- Navigate to **http://localhost:3000/chat**
- Show the clean interface: message input, activity panel (right side with Agent Logs, Documents, Notifications tabs)
- Note: No login required in dev mode (`REQUIRE_AUTH=false`)

#### Step 2: Start Acquisition Intake

Type this prompt:

> I need to procure cloud hosting services for our research data platform. Estimated value around $750,000.

**Expected behavior:**
- Strands supervisor agent loads the **oa-intake** skill via `load_data` tool
- SSE stream shows `tool_use` events in the Activity Panel > Agent Logs tab
- EAGLE asks 2-3 clarifying questions (period of performance, existing vehicles, data sensitivity, competition strategy)
- Does NOT jump straight to document generation
- **Talking point:** "EAGLE uses progressive disclosure -- it loads specialist skills on demand, not all at once. Right now only the intake skill is active."

#### Step 3: Answer Clarifying Questions

Type this response:

> 3-year base period plus 2 option years, starting October 2026. No existing vehicles -- new standalone contract. We need FedRAMP High for PII and genomics research data. Full and open competition preferred. Fixed-price.

**Expected behavior:**
- EAGLE determines pathway: **Full Competition** (>$350K SAT threshold)
- Runs **compliance_query** tool to identify required documents and thresholds
- Shows compliance checklist: SOW, IGCE, Market Research, Acquisition Plan (4 docs minimum)
- Identifies TINA threshold ($750K triggers certified cost/pricing data awareness)
- Identifies subcontracting plan requirement (>$750K)
- Suggests generating the Statement of Work first
- **Talking point:** "The compliance matrix is deterministic -- thresholds come from a lookup table, not the LLM. No hallucinated dollar amounts."

#### Step 4: Show Activity Panel

- Click the **Agent Logs** tab in the right panel
- Show the tool_use and tool_result cards for:
  - `load_data` (oa-intake skill loaded)
  - `compliance_query` (thresholds evaluated)
- Click a card to expand and see full input/output JSON
- **Talking point:** "Every tool call is visible in real-time. This is the same data that flows to Langfuse for persistent trace analysis."

### Act 2: Document Generation (UC-1, EAGLE-8)

#### Step 5: Generate the Statement of Work

Back in chat, type:

> Generate the Statement of Work for this cloud hosting acquisition.

**Expected behavior:**
- EAGLE loads the **document-generator** skill
- Calls `create_document` tool with context from the intake conversation
- Document stored to S3 (`eagle-documents-695681773636-dev/eagle/dev-tenant/...`)
- Shows tool result card with NCI-branded PDF download link
- Note the **DRAFT watermark** visible in the PDF output
- Activity panel shows `create_document` tool result with S3 key
- **Talking point:** "Documents are stored in S3 with version tracking. The SOW pulls all the details we just discussed -- no re-entering data."

#### Step 6: Generate Remaining Documents

Type this prompt:

> Now generate the IGCE, Market Research Report, and Acquisition Plan.

**Expected behavior:**
- EAGLE calls `create_document` three times in sequence
- Each call shows a tool result card with its own download link
- Each document generated as NCI-branded PDF/DOCX (blue headers/footers, Calibri font, DRAFT watermark)
- Activity panel shows three sequential tool_use/tool_result pairs
- **Talking point:** "One conversation generates an entire acquisition package. No switching between tools, no copy-pasting between systems."

#### Step 7: Show Packages Page

- Open **http://localhost:3000/workflows** in a new tab
- The new package card should appear with:
  - Title: "Cloud Hosting Services..."
  - Pathway badge: full_competition
  - Status: in_progress
  - Document checklist with progress indicator
- **Talking point:** "Every package is tracked as a workflow. CORs see their progress at a glance."

### Act 3: Review & Revise

#### Step 8: Revise a Document

Back in chat, type:

> The SOW needs a Section 508 accessibility requirement added under the technical requirements. Also add FedRAMP High authorization as a mandatory contractor qualification. Please regenerate it.

**Expected behavior:**
- EAGLE calls `create_document` again with updated requirements
- SOW version increments to v2
- Old v1 still accessible in S3 version history
- Download link points to the new v2 PDF
- **Talking point:** "Documents are living artifacts -- versioned, editable, never locked until finalized."

### Act 4: Package Export

#### Step 9: Export Package as ZIP

- Switch to the Packages page (`/workflows`)
- Click the package card to open the detail modal
- Click the **Export** button
- Open the downloaded ZIP and show:
  - `manifest.json` -- package metadata snapshot
  - `/sow/` folder -- .md, .pdf, .docx (NCI-branded, DRAFT watermark)
  - `/igce/`, `/market_research/`, `/acquisition_plan/` -- same three formats each
  - Total: **12 files** (4 doc types x 3 formats) + manifest
- **Talking point:** "Entire package exported in one click. PDF/DOCX branded with NCI headers/footers. Ready for submission or further review."

### Act 6: Admin & Observability (EAGLE-22, EAGLE-44)

#### Step 10: Show Admin Dashboard

- Open **http://localhost:3000/admin** in a new tab
- Highlight:
  - System health card
  - Total packages count
  - Total requests and cost
  - Active users

#### Step 11: Show Langfuse Traces

- Navigate to **http://localhost:3000/admin/traces**
- Show the traces list from the demo session
- Click on the most recent trace to expand:
  - Metadata grid (session ID, user ID, environment, model)
  - Tags
  - Observations list: GENERATION spans with token counts, TOOL spans with input/output
  - Latency for each span
- Click **"View in Langfuse"** to deep-link to the full trace in Langfuse Cloud
- **Talking point:** "Every conversation is traced end-to-end via OpenTelemetry. Langfuse gives us cost per session, latency percentiles, and error rates across all tenants."

#### Step 12: Show Skills & Templates Pages

- Navigate to **http://localhost:3000/admin/skills**
  - 7+ specialist agents listed: oa-intake, legal-counsel, market-intelligence, tech-translator, public-interest, document-generator, compliance
  - Point out: each skill has description, version, and usage stats
- Navigate to **http://localhost:3000/admin/templates**
  - 5 document templates: SOW, IGCE, Acquisition Plan, J&A, Market Research
  - Each shows Handlebars placeholders for dynamic field injection

### Act 7: Additional Use Cases (Optional -- Time Permitting)

#### Step 13: Micro Purchase Fast Path (UC-2.1, EAGLE-15)

Open a new chat session. Type:

> I have a quote for $13,800 from Fisher Scientific for lab supplies -- centrifuge tubes, pipette tips, and reagents. Grant-funded, deliver to Building 37 Room 204. I want to use the purchase card.

**Expected behavior:**
- EAGLE detects micro-purchase threshold (<$15K MPT)
- Streamlined flow: no full SOW required, purchase card transaction form
- Minimal questions -- should identify priority sources check, price reasonableness
- **Talking point:** "Micro purchases skip the full package workflow. EAGLE knows the $15K threshold and routes to the simplified path automatically."

#### Step 14: Sole Source Justification (UC-3, EAGLE-27)

Open a new chat session. Type:

> I need to sole-source a $280,000 annual software maintenance contract to Illumina Inc. for our BaseSpace Sequence Hub platform. Only Illumina can maintain this proprietary genomic analysis software. Current contract expires in 60 days.

**Expected behavior:**
- EAGLE identifies sole-source pathway, FAR Part 6 authority (6.302-1, only one responsible source)
- Identifies J&A (Justification & Approval) requirement
- Identifies protest mitigation strategies (SAM.gov posting, market research documentation)
- Below SAT ($350K) so simplified J&A format
- **Talking point:** "Sole source is one of the highest-risk pathways. EAGLE identifies the correct FAR authority, required documentation, and protest mitigation -- all from the first message."

---

## Key Talking Points

**Architecture:**
- Strands Agents SDK (boto3-native Bedrock) -- supervisor orchestrates specialist subagents via tool dispatch
- 7 specialist agents, only 1-2 loaded per conversation via progressive skill loading
- Deterministic compliance matrix (FAR/DFARS/HHSAR lookup -- no hallucinated thresholds)
- S3-backed document storage with version tracking
- DynamoDB single-table for sessions, messages, usage, costs

**Document Pipeline:**
- Markdown -> PDF + DOCX generated in parallel on the server (`document_export.py`)
- NCI branding: blue headers/footers (#003366), DRAFT watermarks, Calibri font
- Versioned in S3 with full history (v1, v2, ...)
- ZIP export includes manifest.json for package reconstruction
- Export API: `POST /api/documents/export` (single doc) and `GET /api/documents/export/{session_id}` (session)

**Lifecycle:**
- Intake -> Generate -> Review/Edit -> Export -> Submit
- All within one conversation thread
- Package status auto-advances as documents complete

**Key Thresholds (FAC 2025-06):**
- Micro-purchase: <$15K (purchase card, streamlined)
- Simplified Acquisition: $15K-$350K (FAR Part 13)
- Full Competition: >$350K (FAR Part 15)
- TINA: >$750K (certified cost/pricing data)
- Subcontracting Plan: >$750K (FAR 19.702)

**Eval Suite Coverage:**

| Tier | Tests | What it validates |
|------|-------|-------------------|
| Tier 1 -- Unit | ~60 | Compliance matrix, KB flow, document pipeline |
| Tier 2 -- Integration | 6 | Live Bedrock: supervisor routing, subagent orchestration |
| Tier 3 -- Full Eval | 42 | All MVP1 use cases, AWS tools, specialist agents, observability |

**MVP1 Use Case Coverage (Excel):**

| UC | Name | Eval Test | Status |
|----|------|-----------|--------|
| UC-1 | New IT Services Acquisition ($750K) | test_35 | Covered |
| UC-2 | GSA Schedule Purchase ($45K) | test_36 | Covered |
| UC-2.1 | Micro Purchase ($14K) | test_21 | Covered |
| UC-3 | Sole Source Justification ($280K) | test_37 | Covered |
| UC-4 | Competitive Range Advisory | test_38 | Covered |
| UC-10 | IGCE Development | test_39 | Covered |
| UC-13 | Small Business Set-Aside ($450K) | test_40 | Covered |
| UC-16 | Tech Requirements to Contract Language | test_41 | Covered |
| UC-29 | End-to-End Acquisition ($3.5M) | test_42 | Covered |

**Model:** Claude Haiku 4.5 via Bedrock cross-region inference (configurable to Sonnet 4.6)

---

## Fallback: If Bedrock is Slow or Creds Expire

- The Packages page (`/workflows`) always shows pre-existing packages (seeded mock data + localStorage)
- Admin pages are data-driven from DynamoDB/Langfuse -- always render even without Bedrock
- Langfuse traces page shows historical traces from prior sessions
- If model is unresponsive, show the admin pages and workflows page, explain the chat flow verbally
- Re-authenticate: `aws sso login --profile eagle`, then restart the backend

---

## Key Metrics to Quote

- **9 MVP1 use cases** with full eval test coverage (Excel-aligned)
- **42 eval tests** across 3 tiers (unit, integration, full eval)
- **7 specialist agents**, 5+ document templates, 256+ knowledge base documents
- **5 acquisition pathways** (micro, simplified, full competition, sole source, IDIQ)
- **Deterministic compliance**: FAR/DFARS/HHSAR threshold matrix (no hallucination)
- **Full observability**: Langfuse OTEL tracing, CloudWatch metrics, per-session cost tracking
- **Multi-tenant**: DynamoDB single-table, tenant-scoped sessions, tier-gated tools
