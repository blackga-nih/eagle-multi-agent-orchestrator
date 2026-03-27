# Document Upload Integration Plan

## Objective

Bring document upload to a fully integrated state across:

- chat upload entry points
- upload proxy routes
- backend upload and assignment APIs
- package assignment
- workspace semantics
- documents listing and viewer flows
- automated test coverage

This plan is based on the current implementation in the `client` and `server` apps as of March 23, 2026.

## Current State Summary

The upload feature is partially implemented.

What currently exists:

- a frontend upload client in `client/lib/document-api.ts`
- a Next.js proxy for `POST /api/documents/upload`
- FastAPI endpoints for:
  - `POST /api/documents/upload`
  - `POST /api/documents/{upload_id}/assign-to-package`
- chat UI entry points for upload:
  - drag and drop in `client/components/chat-simple/simple-chat-interface.tsx`
  - upload button in `client/components/chat-simple/chat-upload-button.tsx`
- a package selector modal in `client/components/chat-simple/package-selector-modal.tsx`
- backend tests for upload and assignment in `server/tests/test_upload_endpoints.py`

What is not fully integrated:

- browser package assignment is not routed through Next.js
- upload context query params are dropped in the proxy
- workspace storage semantics are not aligned with the workspace system
- the main documents page is not using backend uploaded documents as its primary source of truth
- chat upload persistence is split across S3, DynamoDB, and browser localStorage
- end-to-end test coverage is missing

## Confirmed Gaps

### 1. Missing Next.js proxy route for assign-to-package

Severity: Critical

The frontend calls:

- `POST /api/documents/${uploadId}/assign-to-package`

That call is made from:

- `client/lib/document-api.ts`

There is no corresponding route under:

- `client/app/api/documents/...`

Impact:

- package assignment from the browser cannot work reliably
- chat upload can succeed, but assigning the uploaded file to a package fails at the web app boundary

Required fix:

- add a Next.js route at `client/app/api/documents/[id]/assign-to-package/route.ts`
- forward authorization headers
- proxy the JSON body unchanged
- preserve backend error details

### 2. Upload proxy drops query parameters

Severity: Critical

The frontend `uploadDocument()` function sends:

- `session_id`
- `package_id`

The Next.js upload route currently forwards only the multipart form body to FastAPI and does not forward the request query string.

Impact:

- backend never receives upload session context
- backend never receives package context
- modal package preselection may be wrong or absent
- uploaded package context metadata is incomplete
- downstream session linkage for audit/history is broken

Required fix:

- update `client/app/api/documents/upload/route.ts`
- preserve and forward `request.nextUrl.searchParams`

### 3. Workspace semantics are misleading and incomplete

Severity: High

The UI offers:

- "Keep as Workspace Document"

But the actual upload flow stores the object under:

- `eagle/{tenant}/{user}/uploads/...`

Meanwhile the real workspace model is a separate system backed by `workspace_store.py`.

Impact:

- "workspace document" is currently just "user-scoped uploaded file in S3"
- uploads are not associated with active workspace IDs
- documents cannot be filtered or managed by workspace
- UI language implies more than the system currently supports

Decision required:

- either make uploads truly workspace-aware
- or remove workspace-specific language and describe them as user documents or personal documents

### 4. Documents page is not backed by uploaded server documents

Severity: High

The main documents page currently uses:

- local browser storage via `getGeneratedDocuments()`
- mock documents via `MOCK_DOCUMENTS`

Impact:

- uploaded docs may not appear in the canonical documents page
- browser state can diverge from backend reality
- user sees inconsistent data across chat, viewer, and documents page

Required fix:

- decide on the authoritative documents index
- wire the documents page to backend listing APIs
- preserve local cache only as an optimization, not as source of truth

### 5. Upload persistence model is fragmented

Severity: High

Current persistence paths:

- uploaded file bytes: S3
- upload assignment metadata: DynamoDB upload record with TTL
- package documents: package document versioning flow
- chat-visible uploaded document cards: localStorage via `saveGeneratedDocument()`
- documents page: localStorage + mocks

Impact:

- different screens may show different states for the same upload
- document viewer behavior depends on whether a doc exists in sessionStorage/localStorage
- hard to reason about lifecycle, deletion, visibility, and versioning

Required fix:

- define a single canonical model for uploaded docs
- use local cache only for UX speed, never as the primary record

### 6. Legacy chat upload path is only partially implemented

Severity: Medium

There is another chat interface path in:

- `client/components/chat/chat-interface.tsx`

That flow uploads the file and stores only filename state in `uploadedDocuments`.

It does not appear to integrate with:

- package assignment
- document cards
- document viewer linkage
- backend document browsing

Impact:

- behavior differs by chat surface
- users may get inconsistent outcomes depending on which interface they use

Required fix:

- either deprecate this path
- or bring it up to parity with `chat-simple`

### 7. No browser-level tests for upload integration

Severity: Medium

Current tests cover backend APIs only.

Missing coverage:

- upload from chat UI
- drag/drop upload
- package selector flow
- save-to-workspace flow
- assign-to-package flow
- uploaded document visibility in documents page
- viewer opening uploaded documents
- query param forwarding through Next.js proxies

Impact:

- integration regressions are likely
- route wiring issues can pass unnoticed

Required fix:

- add unit/integration tests for proxy routes
- add Playwright end-to-end coverage for upload flows

## Target End State

The feature should behave as follows:

1. A user uploads a document from chat or a documents UI entry point.
2. The upload request includes auth and all relevant context:
   - session ID
   - package ID if applicable
   - workspace ID if the product is meant to support workspace-scoped uploads
3. Next.js forwards the request intact to FastAPI.
4. FastAPI stores the file, classifies it, and returns upload metadata.
5. The user can:
   - assign it to a package
   - keep it as a personal or workspace document
6. That result is reflected consistently in:
   - chat document cards
   - documents page
   - document viewer
   - package checklist and package documents
7. Tests cover both happy paths and failure paths.

## Architectural Decisions Needed

Before implementation goes too far, settle these questions.

### A. What is the source of truth for uploaded documents?

Recommended answer:

- backend-backed documents list, derived from S3 keys plus any necessary metadata

Reason:

- avoids localStorage divergence
- supports multiple browsers/sessions
- makes documents page authoritative

### B. Are uploads workspace-scoped?

Recommended answer if workspaces matter:

- yes, add `workspace_id` to upload metadata and retrieval/listing flows

Recommended answer if workspaces are not ready:

- no, remove workspace-specific copy from the upload modal and related UI

Reason:

- current UI promises workspace behavior that the model does not enforce

### C. Which chat UI is canonical?

Recommended answer:

- standardize on `chat-simple`
- deprecate or reduce feature claims in `chat-interface` unless parity is implemented

Reason:

- dual paths increase regression risk
- current upload behavior differs between interfaces

## Implementation Plan

### Phase 1. Fix critical route wiring

Goal:

- make the existing browser upload and package assignment path work end to end

Tasks:

1. Add Next.js proxy route:
   - `client/app/api/documents/[id]/assign-to-package/route.ts`

2. In that route:
   - read `id` from route params
   - forward `Authorization`
   - forward JSON request body
   - proxy to FastAPI `POST /api/documents/{id}/assign-to-package`
   - normalize error responses

3. Update `client/app/api/documents/upload/route.ts` to forward query params:
   - `session_id`
   - `package_id`
   - future-proof for `workspace_id` if adopted

4. Add route-level tests for:
   - successful upload proxying
   - query string forwarding
   - successful assign-to-package proxying
   - backend error propagation

Acceptance criteria:

- package assignment can be completed from the browser
- upload metadata includes intended context
- failures return meaningful errors in the UI

### Phase 2. Normalize upload lifecycle in chat

Goal:

- make chat upload behavior consistent and fully navigable

Tasks:

1. Review `chat-simple` flow end to end:
   - upload
   - modal
   - assign/save
   - message card
   - viewer open

2. Standardize the resulting document object shape for:
   - uploaded workspace docs
   - uploaded package docs
   - generated docs

3. Ensure chat cards contain enough data for the viewer to open reliably:
   - `s3_key`
   - `document_id` where applicable
   - `content_type`
   - `is_binary`
   - `package_id`
   - `document_type`
   - `title`

4. Decide how to handle the legacy `chat-interface` upload path:
   - either route it to the same shared upload flow
   - or remove/disable document upload there

Acceptance criteria:

- all supported chat surfaces use the same upload behavior
- uploaded docs are consistently visible and navigable from chat

### Phase 3. Unify documents page with backend state

Goal:

- stop relying on localStorage and mocks as the canonical documents source

Tasks:

1. Audit the intended backend documents contract for listing.

2. Replace local-only documents loading in:
   - `client/app/documents/page.tsx`

3. Make the documents page fetch server-backed documents first.

4. If local cache is retained:
   - use it only for optimistic or instant rendering
   - refresh from backend after mount
   - reconcile records by `s3_key` or `document_id`

5. Remove or isolate `MOCK_DOCUMENTS` usage from production documents flow.

6. Ensure uploaded documents appear on the documents page after:
   - workspace save
   - package assignment

Acceptance criteria:

- documents page reflects actual uploaded docs
- refresh/reload shows the same results without relying on browser-local artifacts

### Phase 4. Resolve workspace semantics

Goal:

- align upload UX with actual data model

Option A: True workspace integration

Tasks:

1. Add `workspace_id` to upload requests.
2. Persist `workspace_id` in upload metadata.
3. Update list/retrieval APIs to filter or annotate by workspace.
4. Expose workspace-aware browsing in the UI.
5. Make active workspace selection affect upload destination and listing.

Acceptance criteria:

- uploads are actually scoped to workspaces
- switching workspaces changes what documents are shown where appropriate

Option B: Remove workspace claims

Tasks:

1. Rename "Keep as Workspace Document" to something accurate, such as:
   - "Keep as Personal Document"
   - "Save Without Package Assignment"

2. Remove any implied connection to the workspace subsystem.

Acceptance criteria:

- UI language matches actual behavior

Recommendation:

- choose Option B unless there is an immediate product requirement for workspace-scoped uploaded files

Reason:

- Option A is materially larger and touches storage, APIs, and navigation semantics

### Phase 5. Testing and regression coverage

Goal:

- make upload integration regressions visible immediately

Tasks:

1. Add frontend route tests for:
   - upload proxy
   - assign-to-package proxy

2. Add Playwright coverage for:
   - chat upload via file picker
   - chat upload via drag/drop
   - package selector opens after upload
   - save-to-workspace path
   - assign-to-package path
   - uploaded document appears in chat
   - uploaded document opens in viewer
   - uploaded document appears in documents page

3. Add negative tests for:
   - unsupported MIME type
   - oversized file
   - backend upload failure
   - expired upload ID on assignment
   - missing package

4. Add one regression test specifically for:
   - upload proxy preserving query parameters

Acceptance criteria:

- critical upload flows have browser coverage
- route wiring bugs are caught before release

## Suggested File Changes

### Frontend

- `client/app/api/documents/upload/route.ts`
  - forward search params

- `client/app/api/documents/[id]/assign-to-package/route.ts`
  - add new proxy route

- `client/lib/document-api.ts`
  - verify client error handling remains correct
  - optionally centralize upload/assignment response parsing

- `client/components/chat-simple/simple-chat-interface.tsx`
  - keep upload flow consistent with backend route changes
  - verify chat message/document card handling after assignment

- `client/components/chat-simple/package-selector-modal.tsx`
  - update copy if workspace semantics change

- `client/components/chat/chat-interface.tsx`
  - align or deprecate legacy upload flow

- `client/app/documents/page.tsx`
  - replace mock/local-only source with backend-backed data

### Backend

Possibly no immediate FastAPI changes are required for the critical wiring fix, but review:

- `server/app/main.py`
  - upload endpoint context handling
  - assign-to-package response shape
  - document listing contract

Potential follow-up if workspace scoping is adopted:

- upload metadata schema
- documents list filtering
- workspace-aware retrieval semantics

## Risks

### 1. Documents page contract mismatch

The current documents page and document browser appear to expect different data shapes than the simple S3 listing endpoint provides.

Mitigation:

- define the target frontend document list shape before implementation
- add adapters only temporarily

### 2. Viewer identity mismatch

Some flows identify docs by:

- `s3_key`
- `document_id`
- encoded local IDs

Mitigation:

- standardize viewer navigation on a single stable identifier where possible
- always include raw `s3_key` for uploaded files

### 3. Local cache masking backend failures

Current sessionStorage/localStorage behavior can make the UI appear more integrated than it actually is.

Mitigation:

- test with hard reloads and fresh sessions
- treat local cache as optional acceleration only

### 4. Workspace scope expansion

True workspace integration is broader than a simple upload fix.

Mitigation:

- do not combine route wiring fixes with full workspace scoping in the same change unless necessary

## Recommended Delivery Order

### Milestone 1: Make current upload flow actually work

Scope:

- add assign-to-package proxy
- forward upload query params
- add focused tests

Expected outcome:

- browser upload and assignment path works end to end

### Milestone 2: Make documents consistent in the UI

Scope:

- unify chat upload result shape
- connect documents page to backend-backed uploaded docs
- reduce reliance on local-only state

Expected outcome:

- uploaded docs appear consistently across chat, viewer, and documents page

### Milestone 3: Resolve product semantics

Scope:

- either implement workspace-scoped uploads
- or remove workspace terminology from upload UX
- align legacy chat interface behavior

Expected outcome:

- no misleading UI claims
- fewer parallel code paths

### Milestone 4: Lock it down with E2E coverage

Scope:

- Playwright upload tests
- negative-path coverage
- regression tests for proxy behavior

Expected outcome:

- route and UI regressions become hard to reintroduce

## Definition of Done

The feature should be considered fully integrated only when all of the following are true:

- upload from chat works using both picker and drag/drop
- upload context reaches the backend intact
- package assignment works from the browser
- non-package save behavior is accurately represented in the UI
- uploaded docs appear in the main documents page
- uploaded docs open reliably in the document viewer
- state survives reload and browser restart through backend-backed retrieval
- there is no reliance on mocks for production upload visibility
- automated tests cover the critical happy and failure paths

## Recommended Next Implementation Slice

If implementation starts immediately, the best first slice is:

1. add the missing assign-to-package proxy route
2. fix query forwarding in the upload proxy
3. add tests for both routes

That slice is small, high-leverage, and removes the most serious integration failures before broader cleanup.
