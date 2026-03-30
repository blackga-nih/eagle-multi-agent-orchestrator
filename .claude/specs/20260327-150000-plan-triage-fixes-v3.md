# Plan: Triage Fixes — 2026-03-27 (Session f2d75c92)

## Task Description

Fix 9 issues identified during a live demo session on 2026-03-27 (session `f2d75c92-7095-4656-8a32-8ed1ed4ddc9f`). Cross-referenced 10 DynamoDB feedback items, 55 CloudWatch backend-dev events, 72 telemetry events, and 8 Langfuse traces.

## Objective

Resolve all P0 and P1 issues to improve document generation reliability, context persistence across disconnects, and UI polish. P2 items are backlogged with clear owners.

## Problem Statement

A ~26-minute demo session exposed critical reliability issues in the document generation pipeline. The agent repeatedly disconnected mid-generation (3 GeneratorExits at 24s, 60s, 257s), lost research context on reconnect, produced documents with confusing "linked" naming, and served empty templates instead of generated content on download. The DOCX edit flow consumed 272K input tokens loading all package documents at once, causing a hang. Cascade violations (web_search before KB lookup) occurred 6 times.

## Relevant Files

| File | Issue |
|---|---|
| `server/app/strands_agentic_service.py:4474` | GeneratorExit drops tool results — no persistence of partial work |
| `server/app/streaming_routes.py:170-221` | Keepalive exists but frontend may not handle long tool execution |
| `server/app/tools/package_document_tools.py:167` | Backfill title uses `(linked)` suffix → leaks into S3 key + display |
| `server/app/agentic_service.py:4037` | Same `(linked)` issue in legacy service |
| `server/app/document_service.py:163` | `_sanitize_filename(title)` turns `(linked)` into `-linked` in S3 key |
| `server/app/tools/knowledge_tools.py` | Checklist entries exist (line 172) but agent skips KB before web_search |
| `server/app/strands_agentic_service.py` (cascade guard) | CASCADE VIOLATION logged but not enforced — agent proceeds anyway |
| `client/components/chat-simple/simple-chat-interface.tsx` | Modal width + tool result formatting |
| `client/` (package panel) | Package name display too generic |

---

## Implementation Phases

### Phase 1: P0 Fixes (Critical)

#### 1. Persist tool results from interrupted streams

**Problem**: When `GeneratorExit` fires (line 4474), the handler returns immediately — discarding all tool results and agent text accumulated so far. On "continue", the agent has no memory of prior research and repeats everything.

**Feedback**: *"failing to see previous context where research is already done"* (13:43)

**Evidence**: CloudWatch shows agent re-issued 8 web_searches + 2 knowledge_searches on "continue" for the same topics it already researched before the disconnect.

**File**: `server/app/strands_agentic_service.py`

**Fix**:
1. In the `GeneratorExit` handler (line 4474), before returning:
   - Collect all accumulated `text` chunks and `tool_use`/`tool_result` pairs from the stream
   - Save them as a partial assistant message to the session store via `session_store.save_messages()`
   - Include a metadata flag `"interrupted": true` so the agent knows context was preserved
2. This ensures the next "continue" prompt sees the prior tool results in conversation history

**Validation**:
- Start a doc gen request, disconnect mid-stream, send "continue" — agent should not re-run research
- Check session messages in DynamoDB to confirm partial results saved

#### 2. Strip "(linked)" from backfill document titles

**Problem**: When existing standalone documents are backfilled into a package, the title is set to `f"{doc_type.replace('_', ' ').title()} (linked)"`. The `(linked)` suffix propagates into the S3 key via `_sanitize_filename()` → `Igce-linked.md`. Users see "IGCE linked" in the UI and download filenames.

**Feedback**: *"what is IGCE linked in AP? I don't think linked is official and could be a bug"* (13:57)

**Files**:
- `server/app/tools/package_document_tools.py:167`
- `server/app/agentic_service.py:4037`

**Fix**:
1. Change the backfill title from `f"{doc_type.replace('_', ' ').title()} (linked)"` to just `f"{doc_type.replace('_', ' ').title()}"` in both files
2. Set `change_source="backfill"` (already done) — this is sufficient metadata to track origin without polluting the title

**Validation**:
- `ruff check app/`
- Trigger package creation with existing documents → verify S3 key has no `-linked` suffix
- Verify DynamoDB document record title is clean

#### 3. Package download serving empty template instead of generated content

**Problem**: After document generation completes successfully (logged as `Created document igce v1 for package PKG-2026-0027`), downloading the Acquisition Plan from the package serves the blank DOCX template instead of the generated content.

**Feedback**: *"package document names are messed up. Package AP downloading template and not filled out"* (13:51)

**Evidence**:
- Backend logs confirm documents were generated and saved to S3 successfully
- The recent commit `5c7310f` ("Fix ZIP export: fetch document content from S3 before building archive") suggests this was partially addressed for ZIP exports, but individual document downloads may still have the issue

**Files**:
- `server/app/routers/packages.py` — document download endpoint
- `server/app/document_service.py` — get_latest_document / get_document_content

**Fix**:
1. Audit the package document download endpoint to ensure it fetches the latest version's S3 content, not the template
2. Verify `get_latest_document()` returns the most recent version, not v0/template
3. Cross-check with the ZIP export fix in `5c7310f` — apply the same S3 fetch pattern to individual downloads

**Validation**:
- Generate a document for a package, then download it individually — content should be populated
- Also test ZIP export still works

#### 4. DOCX edit loading 272K tokens (all package documents at once)

**Problem**: The "add Greg Black as COR" request loaded all 4 package documents into context simultaneously (272,089 input tokens per Langfuse trace `d3ea647b`). The agent then spent 257s with `tools_called=[]` before the client disconnected — it was likely reasoning over the massive context.

**Feedback**: *"edit document request stuck on 'working'"* (13:56)

**File**: `server/app/strands_agentic_service.py` (edit_docx_document tool setup / document loading logic)

**Fix**:
1. When editing documents, load only the target document — not all package documents
2. If the edit request mentions multiple documents (e.g., "edit all documents to add COR"), iterate one at a time rather than loading all into a single context
3. Add a guard: if total input tokens for loaded documents would exceed a threshold (e.g., 100K), warn and process documents sequentially

**Validation**:
- Request a multi-document edit → verify documents are loaded one at a time
- Check Langfuse trace shows reasonable token counts per generation call

---

### Phase 2: P1 Fixes (High)

#### 5. Enforce cascade violation (block web_search without prior KB lookup)

**Problem**: The cascade guard logs a WARNING but does not block the tool call — the web_search still executes. This wastes API calls and misses KB content that could answer the query.

**Evidence**: 6 CASCADE VIOLATION warnings in a single session

**File**: `server/app/strands_agentic_service.py` (cascade guard logic)

**Fix**:
1. When a cascade violation is detected, inject a `knowledge_search` call automatically before allowing the `web_search`
2. Alternatively, return the warning as the tool result instead of executing the web_search, forcing the agent to call KB first
3. Keep the WARNING log for observability

**Validation**:
- Run eval test for document generation flow
- Verify no cascade violations in the logs
- Verify agent still produces quality results (KB content used)

#### 6. Agent not surfacing KB checklists when relevant

**Problem**: The KB has extensive checklists (PMR checklists, Section 508, COR Handbook, Pre-Award File Requirements, NIH Acquisition File Checklists) but the agent doesn't reference them during document generation.

**Feedback**: *"make sure we are scanning for checklists in the KB!"* (13:57)

**Evidence**: KB S3 contents include:
- `eagle-knowledge-base/approved/supervisor-core/checklists/` — 8 files (Pre-Award, Micro-Purchase, File Reviewer's, etc.)
- `eagle-knowledge-base/approved/compliance-strategist/PMR-checklists/` — 6 files (BPA, FSS, IDIQ, SAP, etc.)
- `eagle-knowledge-base/approved/compliance-strategist/regulatory-policies/OAG_FY25_02_Section_508_Compliance.txt`
- `eagle-knowledge-base/approved/supervisor-core/core-procedures/COR Handbook Text Version.txt`

The `knowledge_tools.py` already has a built-in checklist entry (line 172) but the `knowledge_search` AI ranking may not score checklists highly enough for document generation queries.

**File**: `server/app/tools/knowledge_tools.py`

**Fix**:
1. In the document generation flow, after creating a document, automatically trigger a `knowledge_search` for related checklists (query: `"{doc_type} checklist compliance requirements"`)
2. If checklist results are found, append a "Compliance Checklist References" section to the document or include as a follow-up message
3. Consider boosting checklist results in the AI ranking when the query context involves document generation

**Validation**:
- Generate an Acquisition Plan → verify the agent references Pre-Award checklist
- Generate an IGCE → verify compliance matrix references appear

---

### Phase 3: P2 Improvements (Medium — Backlog)

#### 7. Package name on side panel too generic

**Feedback**: *"Acquisition Package Name on the right side panel too generic and should reflect detail better"* (13:53)

**File**: `client/components/` (package panel component)

**Fix**: Use the SOW title, procurement description, or first document title as the package display name instead of just `PKG-YYYY-NNNN`. Fall back to the package ID if no descriptive name exists.

#### 8. Modal width and formatting

**Feedback**: *"modals to be reduced to 80% width rather than 100%. Modals also to be formatted and standardized per tool call json or markdown structure"* (13:52)

**Files**: `client/components/` (modal components, tool result rendering)

**Fix**:
1. Set modal max-width to 80% (or `max-w-4xl` / `max-w-5xl` in Tailwind)
2. Render tool call results as formatted markdown or structured JSON in modals
3. Standardize modal layout across all tool types

---

## Step by Step Tasks

### 1. Persist interrupted stream results
- **File**: `server/app/strands_agentic_service.py:4474`
- **Problem**: GeneratorExit discards all accumulated work
- **Fix**: Save partial assistant message + tool results to session store before returning
- **Validation**: Disconnect mid-generation, send "continue", verify no duplicate research

### 2. Remove "(linked)" from backfill titles
- **Files**: `server/app/tools/package_document_tools.py:167`, `server/app/agentic_service.py:4037`
- **Problem**: `(linked)` pollutes title, S3 key, and download filename
- **Fix**: Drop `(linked)` suffix — `change_source="backfill"` already tracks provenance
- **Validation**: `ruff check app/`, create package with backfilled docs

### 3. Fix package document download content
- **File**: `server/app/routers/packages.py`
- **Problem**: Download serves template instead of generated content
- **Fix**: Ensure download endpoint fetches latest S3 version content
- **Validation**: Generate → download → verify content is populated

### 4. Limit document loading for DOCX edits
- **File**: `server/app/strands_agentic_service.py` (edit flow)
- **Problem**: All 4 docs loaded at once → 272K tokens → hang
- **Fix**: Load only the target document; iterate for multi-doc edits
- **Validation**: Multi-doc edit uses sequential loading, <100K tokens per call

### 5. Enforce cascade (KB before web_search)
- **File**: `server/app/strands_agentic_service.py` (cascade guard)
- **Problem**: Violation logged but not enforced
- **Fix**: Return violation as tool result to force KB-first behavior
- **Validation**: Run eval, verify zero cascade violations

### 6. Boost checklist surfacing in knowledge_search
- **File**: `server/app/tools/knowledge_tools.py`
- **Problem**: Checklists exist in KB but aren't surfaced during doc gen
- **Fix**: Auto-query checklists after doc generation; boost checklist ranking
- **Validation**: Generate AP → verify checklist references in output

### 7. Package name display (backlog)
- **File**: Frontend package panel
- **Fix**: Use descriptive name from SOW/description

### 8. Modal width + formatting (backlog)
- **File**: Frontend modal components
- **Fix**: 80% width, markdown/JSON rendering

### 9. Validate all fixes
- `ruff check app/`
- `npx tsc --noEmit`
- `python -m pytest tests/ -v`
- Re-run session scenario to confirm improvement

## Acceptance Criteria

- [ ] P0-1: "continue" after disconnect resumes without re-running research
- [ ] P0-2: No "(linked)" in document titles, S3 keys, or download filenames
- [ ] P0-3: Package document download serves generated content, not empty template
- [ ] P0-4: Multi-document edit loads docs sequentially, stays under 100K tokens per call
- [ ] P1-5: Zero cascade violations in eval runs
- [ ] P1-6: Document generation references KB checklists when relevant
- [ ] All validation commands pass
- [ ] No new errors introduced (re-triage shows improvement)

## Validation Commands

```bash
ruff check app/                     # Python lint
npx tsc --noEmit                    # TypeScript check
python -m pytest tests/ -v          # Unit + eval tests
```

## Notes

- Generated by triage analysis on 2026-03-27
- Session: `f2d75c92-7095-4656-8a32-8ed1ed4ddc9f`
- Package: `PKG-2026-0027` (FedRAMP High Cloud Hosting for NIH Research Data Platform)
- Cross-referenced 10 feedback items, 55 CW backend events, 72 telemetry events, 8 Langfuse traces
- Issue #6 from original triage ("/admin not working") skipped per user instruction
- Checklists confirmed present in KB — issue is surfacing, not ingestion
