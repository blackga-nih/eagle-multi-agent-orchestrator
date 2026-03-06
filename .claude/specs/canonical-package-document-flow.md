# Canonical Package and Document Flow Plan

Branch target: `feature/canonical-package-document-flow`
Primary scope: backend data model, tool orchestration, API contracts, and migration to a single source of truth for package artifacts.

## 1. Executive Summary

The current system has two document paths:

1. Chat tool path (`create_document`) writes timestamped files directly to S3.
2. Package API path (`/api/packages/.../documents`) writes versioned `DOCUMENT#` records to DynamoDB.

This split causes inconsistency in versioning, checklist completeness, and traceability.

This plan defines one canonical flow:

1. Package-scoped documents are always created through a package document service.
2. DynamoDB stores document metadata and application version history.
3. S3 stores document content at deterministic package/version keys.
4. Chat tool generation can still be used, but it must route into the same package document service when in package mode.

## 2. Goals and Non-Goals

### Goals

1. Single authoritative lifecycle for package artifacts.
2. Deterministic and queryable version history.
3. Clear linkage among tenant, user, session, project, package, and document versions.
4. Backward-compatible transition from existing timestamped S3 documents.
5. Preserve streaming UX while improving storage consistency.

### Non-Goals

1. Rewriting prompt logic or agent behavior semantics.
2. Replacing S3 with DynamoDB blobs.
3. Large redesign of document editor UX in this branch.

## 3. Current State

### 3.1 Chat-Driven Path

1. `/api/invoke` proxies to FastAPI `/api/chat/stream`.
2. Streaming route stores user/assistant messages in `SESSION#...` / `MSG#...`.
3. Tool `create_document` currently writes S3 objects at:
   `eagle/{tenant_id}/{user_id}/documents/{doc_type}_{timestamp}.{ext}`
4. Tool result returns `s3_key`, title, preview content.
5. Frontend stores package-like linkage in browser localStorage.

### 3.2 Package API Path

1. `PACKAGE#` entities in DynamoDB hold package lifecycle and checklist.
2. `DOCUMENT#` entities hold content, `version`, `status`, metadata.
3. New versions supersede prior versions.
4. No canonical linkage to S3 object content today in this path.

### 3.3 Problems

1. Same user action can bypass package versioning.
2. Checklist completeness can diverge from generated docs.
3. History is split across localStorage, S3 filenames, and DynamoDB.
4. No stable API-level artifact identity from chat generation.

## 4. Target Architecture

## 4.1 Canonical Principle

For package mode:

1. All generated artifacts must create a `DOCUMENT#` version record.
2. Every `DOCUMENT#` version must map to exactly one immutable S3 key.
3. Package checklist updates must be derived from `DOCUMENT#` state, not client localStorage.

For non-package mode:

1. Generated docs can be stored as workspace documents (out of package scope).
2. They must not mutate package checklist/status.

## 4.2 Storage Model

### DynamoDB (existing `eagle` single table)

Keep `PACKAGE#` and `DOCUMENT#` model, extend document item shape:

1. `project_id` (optional initially, required after Projects rollout).
2. `session_id` (source chat/session).
3. `s3_bucket`
4. `s3_key`
5. `content_hash` (sha256 of canonical content payload)
6. `change_source` (`agent_tool`, `user_edit`, `import`, `migration`)
7. `parent_version` (explicit predecessor, optional for v1)
8. `created_by_user_id`

Document key pattern remains:

1. `PK = DOCUMENT#{tenant_id}`
2. `SK = DOCUMENT#{package_id}#{doc_type}#{version}`

### S3

Canonical package key format:

`eagle/{tenant_id}/packages/{package_id}/{doc_type}/v{version}/{artifact}.{ext}`

Rules:

1. New app version always creates a new S3 key.
2. Bucket versioning remains enabled as infrastructure safety.
3. App-level version number remains source of truth for user/business logic.

## 5. API Changes

## 5.1 New/Updated Backend Contracts

### Existing Endpoint Decision

The current `/api/packages/{package_id}/documents` endpoint (main.py:2125) already creates DOCUMENT# records via `document_store.create_document()`. This plan **extends** (not replaces) that endpoint:

1. Existing endpoint remains the explicit API for package document creation.
2. Chat tool path (`create_document`) will route into the same `document_service` when in package mode.
3. Both paths converge on a shared service layer, ensuring consistent versioning and S3 storage.

### A. Package Context Resolution

1. Add `active_package_id` support in chat request context (session metadata + explicit override).
2. Add helper endpoint:
   - `POST /api/packages/resolve-context`
   - Input: `session_id`, optional `package_id`, optional `action`
   - Output: resolved package mode + package context

### B. Document Creation in Package Mode

1. New internal service method: `create_package_document_version(...)`
2. Update tool handler `create_document`:
   - If package mode is active, call canonical package document service.
   - If package mode not active, call workspace document storage path.

### C. Package Document Endpoints

Extend `/api/packages/{package_id}/documents` response fields:

1. `document_id`
2. `version`
3. `status`
4. `s3_key`
5. `change_source`
6. `session_id`
7. `created_at`, `created_by_user_id`

Add:

1. `GET /api/packages/{package_id}/documents/{doc_type}/history`
2. `GET /api/packages/{package_id}/documents/{doc_type}/versions/{version}/download-url`
3. `POST /api/packages/{package_id}/documents/{doc_type}/versions/{version}/promote-final`

### D. Workspace (Non-Package) Documents

Optional but recommended:

1. Introduce `WORKDOC#` entity family for non-package docs, or use metadata table with explicit type.
2. Keep APIs separate from package docs to avoid accidental checklist mutations.

## 5.2 SSE Tool Result Payload Changes

For package-mode `create_document`, return:

1. `mode: "package"`
2. `package_id`
3. `document_id`
4. `doc_type`
5. `version`
6. `s3_key`
7. `status`
8. `title`
9. `word_count`
10. `generated_at`

For non-package mode:

1. `mode: "workspace"`
2. workspace-specific identifiers

## 5.3 Context Flow Diagram

Package context must propagate from the initial chat request through to the tool handler:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Frontend                                                                    │
│   POST /api/chat { message, session_id, package_id? }                       │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ streaming_routes.py                                                         │
│   1. Extract package_id from request body (explicit) or session metadata    │
│   2. Call package_context_service.resolve_context(session_id, package_id)   │
│   3. Pass resolved PackageContext to sdk_query_streaming()                  │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ strands_agentic_service.py                                                  │
│   1. Receive PackageContext in sdk_query_streaming()                        │
│   2. Pass to _build_service_tools(package_context=...)                      │
│   3. Tool handler closure captures package_context                          │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ _exec_create_document (via tool dispatch)                                   │
│   1. Check package_context.active_package_id                                │
│   2. If set → call document_service.create_package_document_version()       │
│   3. If not → call workspace document storage path                          │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Session Metadata Storage

To support package context persistence across messages:

1. Add `active_package_id` field to session metadata in `session_store.py`.
2. When user starts a package workflow, store `active_package_id` in session.
3. Subsequent messages in same session inherit package context unless overridden.

## 6. Server Refactor Plan

## 6.1 New Service Modules

1. `app/document_service.py`
   - orchestrates version calculation, S3 write, DDB write, supersession.
2. `app/package_context_service.py`
   - resolves active package by session metadata and request hints.

## 6.2 Atomicity and Error Handling

S3 write and DynamoDB write are not transactional. Use the following strategy:

1. **Write order**: DynamoDB first (metadata with `status: "pending"`), then S3.
2. **On S3 success**: Update DynamoDB record to `status: "draft"`.
3. **On S3 failure**: Leave DynamoDB record as `status: "pending"` with `error_message` field.
4. **Idempotency**: Use `content_hash` as idempotency key. If same hash exists for package+doc_type, return existing record instead of creating duplicate.
5. **Cleanup job**: Background task scans for `status: "pending"` records older than 15 minutes and either retries S3 upload or marks as `status: "failed"`.

## 6.3 Existing Module Changes

1. `agentic_service.py`
   - replace direct S3-only save in `_exec_create_document` for package mode.
2. `strands_agentic_service.py`
   - pass package context into service tool execution.
3. `document_store.py`
   - store/retrieve new metadata fields.
4. `package_store.py`
   - add `active_document_map` or derive from latest `DOCUMENT#` query.
5. `main.py`
   - add new history/download endpoints.

## 7. Migration Strategy

## 7.1 Data Backfill Script

Create script:

`scripts/migrate-chat-s3-docs-to-package-records.py`

Steps:

1. Discover candidate S3 keys under legacy path `eagle/{tenant}/{user}/documents/`.
2. Infer doc_type and timestamp from filename.
3. Map to package:
   - if session has explicit package metadata, use it;
   - else apply orphan strategy (see 7.1.5).
4. Create `DOCUMENT#` versions in chronological order.
5. Write migration audit records (`AUDIT#`).

### 7.1.5 Orphan Document Strategy

Documents that cannot be reliably mapped to a package:

1. **Detection criteria**:
   - No `package_id` in session metadata
   - No package reference in surrounding chat messages
   - Ambiguous doc_type that could belong to multiple packages

2. **Handling options** (configurable per-tenant):
   - **Option A (default)**: Create as `WORKDOC#` entity (workspace document, not package-scoped)
   - **Option B**: Create placeholder package `PKG-MIGRATED-{timestamp}` and attach orphans
   - **Option C**: Skip and log for manual review

3. **Audit trail**:
   - All orphan decisions recorded in `AUDIT#` with `action: "orphan_classification"`
   - Include original S3 key, inferred doc_type, chosen option, and reason

4. **Post-migration review**:
   - Generate report of all orphaned documents
   - Provide admin UI to reassign workspace docs to packages if needed

## 7.2 Dual-Write Window

Temporary phase:

1. Package mode writes canonical records.
2. Legacy fields in tool result retained for frontend compatibility.
3. Feature flag:
   - `CANONICAL_PACKAGE_DOC_FLOW=true`

## 7.3 Cutover

1. Remove any direct package artifact reliance on localStorage.
2. Enforce package mode requirement for package checklist mutations.

## 8. Testing Plan

## 8.1 Unit Tests

1. `document_service` version increment and supersession behavior.
2. S3 key deterministic format and immutability.
3. package-mode vs workspace-mode routing.

## 8.2 Integration Tests

1. Chat `/acquisition-package` -> `create_document` -> `DOCUMENT# v1`.
2. Regeneration -> `v2` + `v1 superseded`.
3. Checklist updates reflect latest document status.
4. Download URL for exact version.

## 8.3 E2E Tests

1. Start package, create SOW, regenerate SOW, verify version chip increases.
2. Submit package blocked if required docs missing.
3. Submit succeeds when required docs complete.

## 9. Observability

Add telemetry fields on document events:

1. `tenant_id`, `user_id`, `session_id`
2. `project_id`, `package_id`
3. `document_id`, `doc_type`, `version`
4. `mode` (`package` or `workspace`)
5. `change_source`

## 10. Rollout Phases

1. Phase 1: Service + schema extension + feature flag off.
2. Phase 2: Route package-mode chat doc generation through new service.
3. Phase 3: Frontend reads canonical version metadata.
4. Phase 4: Backfill old data.
5. Phase 5: Remove legacy assumptions and tighten validation.

## 11. Acceptance Criteria

1. Every package document from chat or API is queryable as `DOCUMENT#` with version.
2. Each document version resolves to one S3 key and downloadable artifact.
3. Package checklist status is correct without localStorage dependency.
4. Regeneration always creates incremented version for same `package_id + doc_type`.
5. No regressions in streaming experience and document cards.

## 12. Risks and Mitigations

1. Risk: incorrect package auto-association.
   Mitigation: explicit confirmation when package context is ambiguous.
2. Risk: migration misclassification.
   Mitigation: dry-run mode + audit report + manual review sample.
3. Risk: frontend expecting legacy tool shape.
   Mitigation: compatibility fields retained for one release window.

## 13. Suggested Task Breakdown (Ticket-Ready)

### Task Dependency Graph

```
    ┌───┐     ┌───┐
    │ 1 │     │ 2 │     (Independent: can run in parallel)
    └─┬─┘     └─┬─┘
      │         │
      └────┬────┘
           ▼
         ┌───┐
         │ 3 │           (Depends on 1, 2)
         └─┬─┘
           │
     ┌─────┼─────┐
     ▼     ▼     ▼
   ┌───┐ ┌───┐ ┌───┐
   │ 4 │ │ 5 │ │ 7 │     (Depend on 3; can run in parallel)
   └─┬─┘ └─┬─┘ └───┘
     │     │
     └──┬──┘
        ▼
      ┌───┐
      │ 6 │              (Depends on 4, 5)
      └─┬─┘
        │
        ▼
      ┌───┐
      │ 8 │              (Depends on 6, 7)
      └─┬─┘
        │
        ▼
      ┌───┐
      │ 9 │              (Depends on 8)
      └─┬─┘
        │
        ▼
      ┌────┐
      │ 10 │             (Depends on 9)
      └────┘
```

### Tasks

| # | Task | Depends On | Estimate |
|---|------|------------|----------|
| 1 | Add package context resolver service + tests | — | 1d |
| 2 | Implement `document_service` canonical write path + tests | — | 2d |
| 3 | Wire `create_document` tool to canonical service for package mode | 1, 2 | 1d |
| 4 | Extend `DOCUMENT#` schema fields and API serializers | 3 | 1d |
| 5 | Add history/download/finalize endpoints with authorization checks | 3 | 1d |
| 6 | Update frontend document card model for `version` + `package_id` | 4, 5 | 2d |
| 7 | Add migration script and runbook | 3 | 2d |
| 8 | Add integration and E2E test coverage | 6, 7 | 2d |
| 9 | Enable feature flag in staging; compare metrics and correctness | 8 | 1d |
| 10 | Enable in prod; deprecate legacy-only package document flow | 9 | 1d |

**Critical path**: 1 → 3 → 4 → 6 → 8 → 9 → 10 (10 days)
**Total with parallelization**: ~8-9 days

---

## 14. Implementation Progress

**Last updated**: 2026-03-06

### Completed

| Task | Files Created |
|------|---------------|
| 1. Package context resolver | `server/app/package_context_service.py`, `server/tests/test_package_context_service.py` |
| 2. Document service canonical write | `server/app/document_service.py`, `server/tests/test_document_service.py` |
| 3. Wire `create_document` tool to canonical service for package mode | `server/app/streaming_routes.py`, `server/app/strands_agentic_service.py`, `server/app/agentic_service.py`, `server/app/models.py` |
| 4. Extend DOCUMENT# schema fields + API serializers | `server/app/agentic_service.py`, `server/app/main.py` |
| 5. Add history/download/finalize endpoints | `server/app/main.py` |
| 6. Update frontend document card model (`version`, `package_id`, `mode`) | `client/types/chat.ts`, `client/hooks/use-agent-stream.ts`, `client/components/chat-simple/tool-use-display.tsx`, `client/components/chat-simple/document-card.tsx`, `client/lib/document-store.ts`, `client/app/api/invoke/route.ts` |
| 7. Add migration script and runbook | `scripts/migrate-chat-s3-docs-to-package-records.py`, `docs/development/canonical-package-document-migration-runbook.md` |
| 8. Add integration wiring coverage (backend) | `server/tests/test_canonical_package_document_flow.py` |

### Remaining

| # | Task | Status |
|---|------|--------|
| 8 | End-to-end UI/flow regression coverage (Playwright + full stack) | In progress (backend wiring tests added; E2E still pending) |
| 9 | Enable feature flag in staging | Pending (operational rollout) |
| 10 | Enable in prod | Pending (operational rollout) |
