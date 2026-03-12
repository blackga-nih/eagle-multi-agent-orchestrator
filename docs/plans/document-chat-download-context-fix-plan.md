# Document Tracking, Viewer Context, Streaming, and Download Fix Plan

Date: 2026-03-09
Owner: EAGLE engineering
Status: Reviewed and adjusted — ready for implementation
Audience: Engineers who are new to this codebase
Last reviewed: 2026-03-09

## 1. Purpose
This plan explains how to fix four user-facing problems in EAGLE:

1. Generated documents appear in the right activity pane, but do not reliably appear inline in the chat thread.
2. Clicking document entries can open the viewer with missing or incorrect content.
3. The document assistant chat stream in the viewer is visually broken (chunked messages append as many separate bubbles).
4. Downloading as Word or PDF is unreliable.

It also includes a context upgrade so the document assistant can use the originating conversation and current document state when helping the user edit/fill sections.

The plan is intentionally detailed for engineers with no prior familiarity with this repository.

## 2. Scope
### In scope
- Chat document event wiring and message-to-document association.
- Document open routing/proxy correctness.
- Document viewer assistant stream rendering correctness.
- Document assistant context enrichment (origin session + document content + package context).
- Download pipeline hardening and validation.
- Test additions (unit/integration/e2e where practical).

### Out of scope
- Redesigning document templates.
- Replacing the full document export engine.
- Large schema migrations in DynamoDB.

## 3. Problem Summary and Root Causes

## 3.1 Symptom A: documents show in activity pane but not in chat
Observed behavior:
- The activity pane "Documents" tab shows generated docs.
- The assistant message in chat often has no document card.

Primary root cause:
- `documents` state is keyed by message ID in frontend chat state.
- Generated docs can be attached to a temporary streaming key that is never re-keyed to the final committed assistant message ID.
- The activity panel flattens all docs regardless of message key, so it still shows them.

Secondary factor:
- Tool call results and document cards use separate render paths.

Affected files:
- `client/components/chat-simple/simple-chat-interface.tsx`
- `client/components/chat-simple/simple-message-list.tsx`
- `client/components/chat-simple/activity-panel.tsx`

## 3.2 Symptom B: clicking document can open wrong/empty content
Observed behavior:
- Viewer opens with fallback/template/no content instead of the generated content.

Primary root causes:
- Viewer API route is stale and points to an old AgentCore backend/mocks:
  - `client/app/api/documents/[id]/route.ts` uses `AGENTCORE_URL` (localhost:8081).
- Open target prioritizes `document_id` over `s3_key`, while current server retrieval path is S3-key based.

Secondary factors:
- Session storage handoff is tab-scoped and not reliable for new tab recovery.
- localStorage backup works only if doc save event occurred and the key matches route ID.

Affected files:
- `client/app/api/documents/[id]/route.ts`
- `client/components/chat-simple/tool-use-display.tsx`
- `client/components/chat-simple/document-card.tsx`
- `client/lib/document-store.ts`
- `client/app/documents/[id]/page.tsx`

## 3.3 Symptom C: document assistant stream is visually broken
Observed behavior:
- Each text chunk is appended as a new assistant message bubble.
- Stream appears noisy/jittery and hard to follow.

Root cause:
- Viewer chat page appends on every `onMessage` callback rather than upserting one in-flight message and committing on complete.

Affected file:
- `client/app/documents/[id]/page.tsx`

## 3.4 Symptom D: Word/PDF download unreliable
Observed behavior:
- Download errors or non-working files in local/dev environments.

Root causes:
- Backend URL defaults are inconsistent (`localhost` vs `127.0.0.1`), while stream route already documents IPv6/localhost mismatch risk.
- Export success validation is weak in tests and UI.

Affected files:
- `client/app/api/documents/route.ts`
- `client/app/api/documents/upload/route.ts` (consistency hardening)
- `server/app/main.py` (`/api/documents/export`)
- `server/app/document_export.py`
- tests in `server/tests/test_document_pipeline.py`

## 3.5 Symptom E: document assistant lacks enough origin context
Observed behavior:
- Viewer assistant responses are generic and not strongly tied to original intake/chat details.

Root causes:
- Viewer sends raw chat prompt without structured context envelope.
- Viewer does not always pass `package_id` when invoking stream.
- `session` query context is available only when links include it.

Affected files:
- `client/app/documents/[id]/page.tsx`
- `client/hooks/use-agent-stream.ts`
- `client/types/chat.ts` (if metadata fields are expanded)
- potentially `server/app/streaming_routes.py` for extra metadata propagation

## 4. Architecture Primer (for new engineers)

## 4.1 Generation path
1. User asks for a doc in chat UI.
2. Frontend sends request via Next route:
   - `client/hooks/use-agent-stream.ts` -> `POST /api/invoke`
   - `client/app/api/invoke/route.ts` -> FastAPI `/api/chat/stream`
3. FastAPI stream route:
   - `server/app/streaming_routes.py` -> `sdk_query_streaming(...)`
4. Strands service emits:
   - `tool_use`, `tool_result`, `text`, `complete` chunks from `server/app/strands_agentic_service.py`
5. `create_document` tool implementation:
   - `server/app/agentic_service.py::_exec_create_document`
   - saves workspace doc to S3 path or canonical package record through `server/app/document_service.py`

## 4.2 Viewer path
1. User opens `/documents/[id]`.
2. Viewer attempts content load order:
   - sessionStorage key
   - localStorage generated-doc store
   - API fallback (`/api/documents/[id]?content=true`)
   - local template fallback
3. Viewer assistant uses same stream hook (`useAgentStream`) for chat.

## 4.3 Download path
1. Viewer calls `POST /api/documents` with markdown content + format.
2. Next proxy route forwards to FastAPI `/api/documents/export`.
3. FastAPI calls `export_document` and returns file stream.

## 5. Implementation Plan (phased)

## Phase 0: Baseline and safety checks
Goal: Create reproducible baseline before changes.

Steps:
1. Run lint/typecheck/test subset before edits.
2. Capture baseline behavior for each symptom with screenshots/logs.
3. Confirm environment vars used by Next routes and backend.

Suggested commands:
```bash
cd /Users/hoquemi/Desktop/sm_eagle
npm --prefix client run test -- --help >/dev/null 2>&1 || true
pytest -q server/tests/test_document_pipeline.py -k "export or stream" || true
```

Output artifact to keep:
- Short markdown log with baseline failures in `docs/plans/` or issue tracker.

## Phase 0.5: Verify existing backend document-by-key endpoint behavior
Goal: Confirm FastAPI endpoint behavior and response shape before wiring the Next proxy.

The endpoint already exists in `server/app/main.py` as `GET /api/documents/{doc_key:path}`.

Steps:
1. Verify route behavior and security constraints in `server/app/main.py`:
   - Requires key prefix `eagle/{tenant_id}/{user_id}/...`
   - Returns JSON fields currently available (`key`, `content`, `content_type`, `size_bytes`, `last_modified`)
2. Confirm with a realistic encoded key path:
   - Example key pattern: `eagle/dev-tenant/dev-user/documents/sow_20260309_120000.md`
   - Example curl:
     `curl -H "Authorization: Bearer <token>" "http://127.0.0.1:8000/api/documents/eagle%2Fdev-tenant%2Fdev-user%2Fdocuments%2Fsow_20260309_120000.md"`
3. Decide whether `title` and `document_type` should be derived in the Next proxy or viewer layer (not required from backend for initial fix).

Acceptance criteria:
- GET `/api/documents/{encoded_s3_key}` returns content for valid user-scoped keys.
- 403 returned for out-of-scope keys.
- 404 returned for missing keys.
- Auth header validated (or bypassed in DEV_MODE).

## Phase 1: Fix message-document association in chat
Goal: Ensure generated docs render in the same assistant message bubble.

Files:
- `client/components/chat-simple/simple-chat-interface.tsx`
- `client/components/chat-simple/simple-message-list.tsx`

Tasks:
1. Add document re-key migration during `onComplete`, analogous to existing tool-call migration.
2. Merge docs from temporary stream key into `completedMsg.id`.
3. Deduplicate merged docs using stable key order:
   - `s3_key`
   - `document_id`
   - fallback `title + generated_at`
4. Do not remove existing activity-panel behavior.
5. Handle race condition where same doc arrives twice (via tool_result and complete event).

Implementation notes:
- Keep migration idempotent.
- Avoid mutating previous state in-place.
- Dedupe helper must be deterministic — use `s3_key` as primary identity when present.

Pseudo-code pattern:
```ts
// Dedupe helper — use s3_key as primary identity
const dedupe = (docs: DocumentInfo[]): DocumentInfo[] => {
  const seen = new Set<string>();
  return docs.filter(doc => {
    const key = doc.s3_key || doc.document_id || `${doc.title}-${doc.generated_at}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
};

setDocuments(prev => {
  const streamId = streamingMsgIdRef.current;
  const streamDocs = prev[streamId] ?? [];
  const finalDocs = prev[completedMsg.id] ?? [];
  const merged = dedupe([...finalDocs, ...streamDocs]);
  const next = { ...prev, [completedMsg.id]: merged };
  delete next[streamId];
  return next;
});
```

Acceptance criteria:
- After doc generation, chat message contains document card.
- Activity pane still contains same document.
- No duplicate cards after refresh/stream completion.
- Same doc arriving twice (race condition) does not produce duplicates.

## Phase 2: Normalize open target identity and persistence keys
Goal: Ensure links use retrievable identifiers.

Files:
- `client/components/chat-simple/tool-use-display.tsx`
- `client/components/chat-simple/document-card.tsx`
- `client/lib/document-store.ts`

Tasks:
1. Change open ID priority to prefer `s3_key` before `document_id`.
2. Align `saveGeneratedDocument` keying strategy to same priority for consistency.
3. Preserve backwards compatibility when existing docs are keyed by old IDs.

Compatibility strategy:
- For reads, continue checking current ID directly.
- Optionally add secondary lookup by alternate encoded key.

Acceptance criteria:
- Clicking chat document opens viewer with retrievable backend key path.
- Previously saved docs still open from document list.

## Phase 3: Replace stale document-by-id API proxy
Goal: Route viewer document fetches to the real FastAPI backend.

**Scope clarification:**
- **FIX**: `client/app/api/documents/[id]/route.ts` — uses stale `AGENTCORE_URL` (port 8081)
- **DO NOT TOUCH**: `client/app/api/documents/route.ts` — already correct, uses `FASTAPI_URL` (port 8000)

File:
- `client/app/api/documents/[id]/route.ts`

Tasks:
1. Replace `AGENTCORE_URL` with `FASTAPI_URL` (same pattern as `/api/documents/route.ts`).
2. Proxy GET to FastAPI endpoint verified in Phase 0.5:
   - `/api/documents/{doc_key:path}`
3. Forward `Authorization` header.
4. Keep `content`, `version`, and query passthrough behavior if needed.
5. Remove legacy mock payload fallback for production path (keep only for explicit DEV_MODE).
6. Return backend error payload transparently for debugging.

Important details:
- Preserve encoded key handling; do not double-decode or double-encode.
- Keep browser-only fallback logic in the viewer layer (`sessionStorage`/`localStorage`), not in this Next API route.

Acceptance criteria:
- Viewer content fetch works against real FastAPI route.
- 403/404 behavior reflects backend auth/key checks.
- Previously saved docs with old key format still retrievable via viewer fallback path.

## Phase 4: Fix viewer assistant streaming UX
Goal: Render a single coherent in-flight assistant message.

File:
- `client/app/documents/[id]/page.tsx`

Tasks:
1. Introduce local `streamingMsg` state and refs similar to main chat implementation.
2. In `onMessage`, upsert/update in-flight assistant message instead of pushing new entry each chunk.
3. In `onComplete`, commit once to `chatMessages` and clear in-flight state.
4. In `onError`, clear in-flight state safely.

Acceptance criteria:
- During stream, only one assistant bubble grows.
- On completion, exactly one final assistant message is stored.

## Phase 5: Add document-origin context envelope for viewer assistant
Goal: Ensure assistant can help fill/edit based on origin conversation and current document.

File:
- `client/app/documents/[id]/page.tsx`

Tasks:
1. Build a context envelope before `sendQuery`:
   - Document title/type.
   - Current document excerpt (token/character bounded).
   - Session-derived user context (from `loadSession(sessionId)`).
   - Clear user intent section.
2. Pass `package_id` when available using `sendQuery(query, sessionId, packageId)`.
3. If no `session` query param exists, attempt fallback from stored document metadata.

Suggested envelope format:
```text
[DOCUMENT CONTEXT]
Title: ...
Type: ...
Current Content (excerpt): ...

[ORIGIN SESSION CONTEXT]
- user requirement summary ...
- key constraints ...

[USER REQUEST]
...raw user input...

Instruction: If user requests direct edits, use create_document and return updated draft.
```

Token budget guardrails:
- **Document excerpt**: Max 2000 characters (~500 tokens). Prefer first 1000 + last 1000 chars for long docs.
- **Session context**: Max 1500 characters (~375 tokens). Extract only user messages, summarize if needed.
- **Total context overhead**: Target < 1000 tokens per request.
- Implement a `truncateWithEllipsis(text, maxChars)` helper.
- Consider making context inclusion opt-in via a "Use conversation context" toggle for power users.

Security guardrails:
- Never include secrets/tokens.
- Strip any `Authorization`, `Bearer`, or `AWS` patterns from session messages.

Acceptance criteria:
- Viewer assistant responses reference document + session context.
- Edit requests more consistently produce actionable draft updates.
- Context envelope adds < 1000 tokens overhead.
- No sensitive data leaks into context.

## Phase 6: Complete event metadata passthrough
Goal: Preserve `tools_called` and usage metadata at SSE complete event.

Files:
- `server/app/streaming_routes.py` — stream generator
- `server/app/stream_protocol.py` — `MultiAgentStreamWriter.write_complete()` method
- `client/hooks/use-agent-stream.ts` — consumer

Tasks:
1. Confirm `strands_agentic_service.py` continues emitting complete chunks with:
   - `tools_called`
   - `usage`
2. In `stream_protocol.py`, extend `MultiAgentStreamWriter.write_complete()` to accept optional metadata:
   ```python
   async def write_complete(self, queue, metadata: Optional[Dict[str, Any]] = None):
       event = self._create_event(StreamEventType.COMPLETE, metadata=metadata or None)
       await queue.put(event.to_sse())
   ```
3. In `streaming_routes.py`, pass through metadata in `stream_generator` when handling chunk type `complete`:
   - `tools_called`
   - `usage` (token counts if available)
4. In `use-agent-stream.ts`, verify complete-event metadata is consumed by existing fallback logic (`event.metadata?.tools_called`).
5. Keep existing fallback complete behavior for abnormal terminations.

Why this matters:
- Frontend fallback logic for document recovery relies on `tools_called` when tool_result is absent.

Acceptance criteria:
- Complete events include metadata consistently.
- Fallback doc-recovery path can trigger when needed.
- `tools_called` array contains tool names invoked during the turn.

## Phase 7: Download pipeline hardening
Goal: Make Word/PDF export reliable and diagnosable.

**Scope clarification:**
- `/api/documents/route.ts` (export proxy) is already correct — uses `FASTAPI_URL:8000`.
- Focus hardening on backend export logic and error surfacing, not URL changes.

Files:
- `client/app/api/documents/upload/route.ts` (ensure uses `FASTAPI_URL` if not already)
- `client/app/documents/[id]/page.tsx` (improve error display)
- `server/app/main.py` (`/api/documents/export` endpoint)
- `server/app/document_export.py`
- tests in `server/tests/test_document_pipeline.py`

Tasks:
1. Audit `upload/route.ts` for URL consistency — should use `FASTAPI_URL`, not `AGENTCORE_URL`.
2. Improve client error surface in viewer so users see meaningful export failure cause:
   - Show backend error message, not just "Export failed: 500".
   - Add retry button for transient failures.
3. Add backend validation in `document_export.py`:
   - Validate runtime availability of `python-docx` (docx) and `reportlab` (pdf) in target environments.
   - Decide policy explicitly:
     - keep current text-fallback behavior, or
     - switch to strict 503 responses for missing dependencies.
4. Add test assertions for file signatures:
   - DOCX starts with ZIP signature `PK`.
   - PDF starts with `%PDF`.
5. Keep markdown export unchanged.

Optional stronger hardening:
- If strict mode is chosen, return explicit 503 instead of fallback payloads when dependencies are missing.
- Add health check endpoint: `GET /api/documents/export/health` returns dependency status.

Acceptance criteria:
- Downloads succeed in both docx and pdf formats.
- Files open in native apps (Word/PDF reader).
- Missing dependency returns clear 503 error, not corrupt file.

## Phase 8: Test plan (must complete before merge)

## 8.1 Backend tests
Files:
- `server/tests/test_document_pipeline.py` — exists, add new test cases
- `server/tests/test_canonical_package_document_flow.py` — exists, extend with additional cases

Tests to add to `test_document_pipeline.py`:
1. SSE complete metadata includes tools_called when create_document used.
2. Export docx/pdf content signature validation (PK for docx, %PDF for pdf).
3. Stream emits `tool_result` for successful create_document path.
4. GET `/api/documents/{s3_key}` returns correct content (for Phase 0.5 endpoint).

Extend `test_canonical_package_document_flow.py` with:
1. End-to-end test: chat request → document generation → S3 storage → retrieval.
2. Package-scoped document listing.
3. Version increment on document update.

## 8.2 Frontend tests (Playwright)
File:
- `client/tests/document-pipeline.spec.ts` — exists, extend with additional scenarios

Tests to add:
1. After generation, document card appears inline in chat message (not only activity panel).
2. Clicking chat card opens viewer with expected document title/content.
3. Viewer assistant streaming shows one evolving assistant bubble (not multiple).
4. Download requests for docx/pdf return non-empty blobs and no visible error.
5. Document re-key migration: same doc doesn't duplicate after stream completion.

## 8.3 Manual QA matrix
Run in local dev and deployed dev environment.

Scenario list:
1. Generate SOW from chat.
2. Confirm pane + chat both show doc.
3. Open from chat and from pane.
4. Use viewer assistant to edit section.
5. Download as docx and pdf.
6. Reopen same document later and confirm content load.

Record:
- Browser, environment, timestamp, pass/fail, issue link.

## 9. Rollout Strategy
1. Merge in small PRs by phase group:
   - PR0: Phase 0.5 (backend endpoint prerequisite)
   - PR1: Phase 1 + Phase 2 (document association fixes)
   - PR2: Phase 3 + Phase 4 (viewer routing + streaming UX)
   - PR3: Phase 5 + Phase 6 (context envelope + metadata passthrough)
   - PR4: Phase 7 + Phase 8 (hardening + tests)
2. Use feature flags only if needed for high-risk context envelope changes (Phase 5).
3. Deploy to dev first and run manual QA matrix after each PR.
4. Monitor logs for export and stream errors for 24 hours after PR2+.

## 10. Risks and Mitigations
1. Risk: Re-key migration may duplicate docs.
   - Mitigation: deterministic dedupe helper using `s3_key` as primary identity, with test coverage.
2. Risk: Route changes can break existing mock-based workflows.
   - Mitigation: preserve fallback behavior only where required and gate by env.
3. Risk: Context envelope inflates token usage.
   - Mitigation: strict token budget (< 1000 tokens), truncation helpers, and opt-in toggle for power users.
4. Risk: Export dependency mismatch across environments.
   - Mitigation: startup diagnostics, explicit 503 errors, and health check endpoint.
5. Risk: Backend endpoint response/prefix assumptions differ from viewer expectations.
   - Mitigation: verify exact route behavior in Phase 0.5 and adapt proxy/viewer mapping.
6. Risk: Old localStorage keys become unretrievable after Phase 3.
   - Mitigation: backward-compat fallback lookup in viewer before returning 404.

## 11. Definition of Done
All conditions must be true:
1. Generated docs reliably appear in both activity pane and chat bubble.
2. Chat card click opens viewer with retrievable content.
3. Viewer assistant stream renders as one coherent in-flight message.
4. Viewer assistant uses origin context well enough to produce relevant edits.
5. Word/PDF downloads succeed and open correctly.
6. Automated tests pass for changed behavior.
7. Manual QA matrix completed in dev.

## 12. Quick Start for New Engineer
1. Read this file fully.
2. Reproduce baseline symptoms first.
3. Implement Phase 1 and Phase 2 before touching viewer context.
4. Keep PRs small and test after each phase.
5. Do not refactor unrelated code in same PR.

## 13. File Checklist
Use this checklist when implementing:

**Frontend — Edit existing:**
- [ ] `client/components/chat-simple/simple-chat-interface.tsx` (Phase 1)
- [ ] `client/components/chat-simple/simple-message-list.tsx` (Phase 1)
- [ ] `client/components/chat-simple/tool-use-display.tsx` (Phase 2)
- [ ] `client/components/chat-simple/document-card.tsx` (Phase 2)
- [ ] `client/lib/document-store.ts` (Phase 2)
- [ ] `client/app/api/documents/[id]/route.ts` (Phase 3 — main fix)
- [ ] `client/app/documents/[id]/page.tsx` (Phase 4, 5)
- [ ] `client/app/api/documents/upload/route.ts` (Phase 7 — audit only)
- [ ] `client/hooks/use-agent-stream.ts` (Phase 6)

**Frontend — DO NOT TOUCH:**
- [ ] ~~`client/app/api/documents/route.ts`~~ — already correct, uses FASTAPI_URL

**Backend — Edit existing:**
- [ ] `server/app/streaming_routes.py` (Phase 6)
- [ ] `server/app/stream_protocol.py` (Phase 6)
- [ ] `server/app/main.py` (Phase 0.5 — verify existing GET endpoint behavior)
- [ ] `server/app/document_export.py` (Phase 7)
- [ ] `server/tests/test_document_pipeline.py` (Phase 8 — add cases)
- [ ] `server/tests/test_canonical_package_document_flow.py` (Phase 8 — extend existing file)

**Tests to extend (already exist):**
- [ ] `client/tests/document-pipeline.spec.ts` (Phase 8)
