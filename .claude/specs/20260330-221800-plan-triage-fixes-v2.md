# Plan: Triage Fixes — 2026-03-30 (Broad Sweep, 7 Feedback Items)

## Task Description
Fix 7 issues from manual feedback cross-referenced against 50+ CloudWatch events, 50 DynamoDB feedback items, and 30 Langfuse traces across 10 sessions (dev environment, tenant `dev-tenant`).

## Objective
Resolve all P0 and P1 issues (6 bugs). P2 enhancement backlogged with design notes.

## Problem Statement
Live demo workflow ("procure cloud hosting services, $750K") exhibits multiple UX-breaking bugs: side panel falsely marks documents as completed before generation, document cards don't render in chat after tool calls, and cold-start causes 45s+ delays on first message. Additionally, recurring bugs persist: generic document titles, feedback button stops working mid-session, and ZIP export includes raw DOCX templates instead of generated content.

## Relevant Files
| File | Issue |
|---|---|
| `server/app/tools/package_document_tools.py:114-183` | Backfill marks orphan docs as completed |
| `server/app/document_service.py:575-618` | Checklist auto-completes on dynamic expansion |
| `client/hooks/use-agent-stream.ts` | Document card events not reaching message list |
| `client/components/chat-simple/simple-message-list.tsx:478` | Cards need documents[messageId] |
| `server/app/strands_agentic_service.py:422-438` | Model chain includes 2 AccessDenied models |
| `server/app/strands_agentic_service.py:494-528` | Startup probe timeouts too aggressive |
| `server/app/strands_agentic_service.py:3049-3056` | Title fallback → "Untitled Acquisition" |
| `client/components/feedback/feedback-modal.tsx:69-139` | No fetch timeout, silent failures |
| `server/app/routers/packages.py:290-304` | Binary flag on DOCX bypasses conversion |
| `server/app/document_export.py:1078-1083` | ZIP includes raw template for binary docs |

---

## Implementation Phases

### Phase 1: P0 Fixes (Critical)

#### 1. Side Panel Premature Document Completion
- **Feedback**: "acquisition package side panel shows 3 completed docs. 2 of which have not been created yet. IGCE and SOW. now it shows 6 completed"
- **Evidence**: CW logs show `Backfilled sow from legacy path into PKG-2026-0033` and `Backfilled igce from legacy path into PKG-2026-0033` at package creation time. DDB feedback: "AP panel adding documents and crossing them off before generating" (session 27c1090e), "ap checklist on the right should not cross documents off the list until they are actually generated" (session 2745ef8e)
- **Root cause**: Two paths: (A) `_backfill_completed_docs()` scans S3 for orphan files from prior sessions and auto-links them. (B) `_update_package_checklist()` at line 604-609 adds new doc types to both `required` AND `completed` simultaneously.
- **File**: `server/app/tools/package_document_tools.py:114-183`, `server/app/document_service.py:575-618`
- **Fix**: (A) Filter backfill to current session only. (B) Remove auto-complete on dynamic expansion — only add to `required`, not `completed`.
- **Validation**: Create package in fresh session → checklist shows 0/N. Generate SOW → 1/N. Generate IGCE → 2/N.

#### 2. Document Cards Not Rendering in Chat
- **Feedback**: "documents on the checklist on side panel but the document cards arent rendering in the chat"
- **Evidence**: DDB feedback: "SOW document card not showing after package update and doc generation" (session 27c1090e). Langfuse trace shows SOW creation succeeded but frontend shows checklist update only.
- **Root cause**: `PackageChecklist` only contains string arrays. Chat cards require `DocumentInfo` keyed by message ID. SSE stream may not emit document_card events tied to message IDs.
- **File**: `client/hooks/use-agent-stream.ts`, `client/components/chat-simple/simple-message-list.tsx:478`, `server/app/stream_protocol.py`
- **Fix**: Ensure `create_document_tool` emits SSE metadata with DocumentInfo payload. Frontend must capture and key by message ID.
- **Validation**: Full intake flow → all 4 docs show as cards in chat.

### Phase 2: P1 Fixes (High)

#### 3. Chat Cold-Start / TTFT Timeout
- **Feedback**: "Chat cold-start issue persists. Eventually starts working. Is it using backup model Nova?"
- **Evidence**: CW: 3 TTFT timeouts today (sessions 9c5573e4, 85c03ec9, c44a4559). `claude-sonnet-4` and `claude-sonnet-4-5` consistently fail with AccessDeniedException. Session 9c5573e4: "all models exhausted". Nova is NOT in fallback chain (defined but unused at line 320).
- **Root cause**: Chain has 4 models but only 2 are accessible. Aggressive 8s startup probe fails cold models. 45s TTFT timeout cascades through dead models.
- **File**: `server/app/strands_agentic_service.py:422-438,494-528,5099`
- **Fix**: Remove inaccessible models from chain. Increase startup probe timeout. Consider adding Nova Pro as final fallback.
- **Validation**: Restart backend → all probe models pass. First message completes within 45s.

#### 4. Generic Document Title Bug
- **Feedback**: "Generic document title bug persists", "Acquisition Package Name on the right side panel too generic"
- **Evidence**: DDB: "document title generation bug persists" (session 27c1090e). Code confirms fallback chain ends at "Untitled Acquisition".
- **Root cause**: `strands_agentic_service.py:3049-3056` — title lookup on `_DOC_TYPE_LABELS` fails when `dt` is not normalized.
- **File**: `server/app/strands_agentic_service.py:3049-3056,738-749`
- **Fix**: Normalize `dt` before `_DOC_TYPE_LABELS` lookup. Replace "Untitled Acquisition" with dynamic `dt.replace('_',' ').title()`.
- **Validation**: Generate each doc type → titles match type-specific labels.

#### 5. Feedback Button Stops Submitting
- **Feedback**: "Feedback button was working but at a certain point stops submitting", "Feedback button bug persists"
- **Evidence**: CW shows successful feedback POSTs in session f2d75c92 (8 items between 13:36-13:59), then silence. No 500 errors logged for feedback endpoint.
- **Root cause**: No `AbortController` timeout on fetch. If proxy or backend hangs, `submitting` state stays true and button appears permanently disabled.
- **File**: `client/components/feedback/feedback-modal.tsx:69-139`, `client/contexts/feedback-context.tsx`
- **Fix**: Add AbortController with 10s timeout. Add error logging. Verify `finally` block runs on abort.
- **Validation**: Submit feedback 5+ times. Simulate timeout → button recovers.

#### 6. AP ZIP Template Leak for Market Research
- **Feedback**: "AP zip download for market research is showing docx template"
- **Evidence**: Code confirms: `packages.py:293-297` marks `file_type!="md"` as binary → `document_export.py:1079` includes raw blob → template included instead of generated content.
- **Root cause**: Documents stored as `file_type="docx"` (via AI edit service) get binary treatment in ZIP export, bypassing conversion.
- **File**: `server/app/routers/packages.py:290-304`, `server/app/document_export.py:1078-1083`
- **Fix**: For `file_type="docx"` documents, include directly in ZIP as DOCX (they ARE real content). Only skip conversion, don't skip inclusion. OR ensure `create_document_tool` stores as markdown and only converts to DOCX at export time.
- **Validation**: Generate market research → download ZIP → open DOCX → verify real content.

### Phase 3: P2 Enhancements (Backlog)

#### 7. Clickable Documents in Side Panel
- **Feedback**: "plan an enhancement to the right side panel so you can actually click on the documents in the checklist and open them up. The window that pops open should have a tab at the top for each document"
- **Root cause**: Feature not implemented. Checklist items are display-only.
- **File**: `client/components/chat-simple/checklist-panel.tsx`
- **Fix**: Add click handlers to completed items. Create `DocumentViewerModal` with tabbed interface (one tab per doc + package info tab). Fetch content via `GET /api/packages/{id}/documents/{type}`. Check `client/app/workflows/` for existing patterns.
- **Validation**: Click completed doc in checklist → modal opens → tab through documents.

---

## Additional Issues Discovered

| Issue | Sev | File | Fix |
|-------|-----|------|-----|
| OTEL export 401 Unauthorized (25+ errors) | P1 | OTEL config / env vars | Rotate OTEL auth token |
| `knowledge_search` pickle error | P1 | KB search tool | Fix thread-lock serialization |
| Template `_index.json` missing | P2 | Docker build / eagle-plugin | Add _index.json to image |
| Langfuse list_traces 400 | P2 | Langfuse client config | Fix query params |

---

## Acceptance Criteria
- [ ] New package starts with 0/N completed documents
- [ ] Document cards render in chat after tool call completes
- [ ] First message responds within 45s after cold restart
- [ ] All generated documents have type-specific titles
- [ ] Feedback button works for 5+ consecutive submissions
- [ ] Market research ZIP contains generated content, not template
- [ ] All validation commands pass

## Validation Commands
```bash
cd server && ruff check app/
cd client && npx tsc --noEmit
cd server && python -m pytest tests/ -v
```

## Notes
- Generated by /triage skill on 2026-03-30
- Sources: 50 DDB feedback, 50+ CW events, 30 LF traces across 10 sessions
- Environment: dev, tenant: dev-tenant, user: dev-user
- Prior triage specs: v1 (20260330-091000)
