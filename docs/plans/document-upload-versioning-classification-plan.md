# Document Upload, Versioning & Classification System

## Context

User-uploaded documents in EAGLE currently go to S3 as flat files (`eagle/{tenant}/{user}/uploads/{filename}`) with **no DynamoDB metadata, no versioning, and no type classification**. Package documents (agent-generated) already have a full lifecycle via `document_store.py` + `document_service.py`. This plan unifies the two paths so user uploads get first-class treatment: tracked metadata, version history, and document type tagging.

### Design Decisions
- **Upload UI location**: Both the `/documents` page AND a chat sidebar panel
- **Classification**: Smart-suggest based on filename/content, optional (defaults to `unclassified`)
- **Document types**: Acquisition types (SOW, IGCE, etc.) + general categories (reference, correspondence, policy, other)

---

## Phase 1: Backend — Workspace Document Store

**New file: `server/app/workspace_document_store.py`**

DynamoDB entity (single-table, same `eagle` table):
```
PK:  USERDOC#{tenant_id}#{user_id}
SK:  USERDOC#{document_id}
```

Version history entity:
```
PK:  USERDOCVER#{tenant_id}#{document_id}
SK:  VERSION#{version:04d}
```

Fields on USERDOC: `document_id`, `tenant_id`, `user_id`, `title`, `doc_type` (user-selected or `unclassified`), `file_type`, `content_type`, `current_version`, `status`, `s3_key`, `s3_bucket`, `size_bytes`, `content_hash`, `created_at`, `updated_at`.

Functions:
- `create_workspace_document()` — creates USERDOC + VERSION#0001 records
- `get_workspace_document()`
- `list_workspace_documents(tenant_id, user_id, doc_type_filter=None)`
- `create_workspace_document_version()` — increments version, writes new VERSION record, updates USERDOC
- `get_workspace_document_versions()`
- `update_workspace_document_metadata()` — change doc_type, title after upload

**New S3 key pattern** (versioned):
```
eagle/{tenant}/{user}/uploads/{document_id}/v{version}/{safe_filename}
```

Follow patterns from `server/app/document_store.py` and `server/app/document_service.py`.

---

## Phase 2: Backend — Enhanced Upload Endpoint + Type Suggestion

**Modify: `server/app/main.py` (lines 1160-1198)**

Add optional form fields to `POST /api/documents/upload`:
```python
@app.post("/api/documents/upload")
async def api_upload_document(
    file: UploadFile = File(...),
    document_type: str = Form("unclassified"),
    title: str = Form(None),  # defaults to filename
    user: UserContext = Depends(get_user_from_header),
):
```

Changes:
1. Generate `document_id` (UUID) before upload
2. Upload to versioned path: `eagle/{tenant}/{user}/uploads/{document_id}/v1/{safe_name}`
3. Write DynamoDB metadata via `workspace_document_store.create_workspace_document()`
4. Write changelog entry
5. Return enriched response: `{document_id, key, filename, size_bytes, content_type, doc_type, version, title, suggested_type}`

**New: `GET /api/documents/suggest-type`** — smart type suggestion
- Query param: `filename` (required)
- Returns `{ suggested_type, confidence }` based on filename keyword matching:
  - `sow` / `statement_of_work` → `sow`
  - `igce` / `cost_estimate` → `igce`
  - `market` / `research` → `market_research`
  - `acquisition_plan` / `ap_` → `acquisition_plan`
  - `justification` / `j_and_a` → `justification`
  - `policy` / `memo` → `policy`
  - Default → `unclassified`
- Called by frontend before/during upload to pre-populate the dropdown

---

## Phase 3: Backend — New Endpoints

**`POST /api/documents/{document_id}/versions`** — binary re-upload for new version
- Accepts multipart file
- Looks up existing USERDOC, increments version
- Uploads to `v{next}` S3 path, creates VERSION record
- Writes changelog

**`GET /api/documents/{document_id}/versions`** — list version history
- Returns all versions with S3 keys, timestamps, sizes

**`PATCH /api/documents/{document_id}/metadata`** — update classification/title
- Body: `{ doc_type?, title? }`
- Updates USERDOC record

**Modify: `GET /api/documents`** (lines 918-950)
- Query `workspace_document_store.list_workspace_documents()` for DynamoDB-tracked docs
- Still scan S3 for legacy uploads without DynamoDB records
- Merge + deduplicate, return enriched metadata including `doc_type`, `version`, `document_id`

**Modify: `PUT /api/documents/{doc_key:path}`** (lines 1012-1115)
- For workspace docs with versioned path pattern: route through `workspace_document_store.create_workspace_document_version()` instead of S3 overwrite
- Keep binary rejection for now (binary re-upload uses the new POST versions endpoint)

---

## Phase 4: Frontend — Upload UI with Smart Classification

**Modify: `client/components/documents/document-upload.tsx`**

Add document type selector with smart suggestion:
1. On file selection, call `GET /api/documents/suggest-type?filename={name}` to get suggested type
2. Show a dropdown pre-populated with the suggestion (user can change or leave as-is)
3. Dropdown options: acquisition types (SOW, IGCE, Market Research, Acquisition Plan, J&A, Funding Doc, Eval Criteria, Security Checklist, Section 508, COR Cert, Contract Type Justification) + general types (Reference, Correspondence, Policy, Other, Unclassified)
4. Update `onUpload` signature: `(file: File, options: { documentType: string; title?: string }) => Promise<...>`
5. Optional title override text field (defaults to filename)

**Wire upload into both locations:**

1. **`/documents` page** (`client/app/documents/page.tsx`):
   - Add upload section/button that opens the `DocumentUpload` component
   - On successful upload, refresh the document listing

2. **Chat sidebar** (`client/components/chat-simple/simple-chat-interface.tsx`):
   - Add a file attachment button/icon in the chat input area
   - Opens a compact upload panel
   - After upload, document appears in the session's document list

**Modify: `client/app/api/documents/upload/route.ts`**
- Forward `document_type` and `title` form fields to FastAPI

**New: `client/app/api/documents/suggest-type/route.ts`**
- Proxy for the type suggestion endpoint

---

## Phase 5: Frontend — Document Browser & Detail Integration

**Modify: `client/components/documents/document-browser.tsx`**
- Use enriched response from backend (doc_type, version, document_id)
- Add general document types to filter dropdown
- Show version badge on each document card

**Modify: `client/app/documents/[id]/page.tsx`**
- Add "Version History" panel showing all versions from `GET /api/documents/{id}/versions`
- "Upload New Version" button for binary docs (calls `POST /api/documents/{id}/versions`)
- "Edit Classification" dropdown (calls `PATCH /api/documents/{id}/metadata`)
- Text document saves create new versions instead of overwriting

**New: `client/app/api/documents/[id]/versions/route.ts`**
- Proxy GET (list versions) and POST (upload new version) to FastAPI

**New: `client/app/api/documents/[id]/metadata/route.ts`**
- Proxy PATCH for metadata updates

---

## Phase 6: Migration (Deferred)

Optional script to backfill DynamoDB records for existing flat uploads. Low priority since the listing endpoint handles legacy uploads gracefully.

---

## Implementation Order

1. Phase 1 — `workspace_document_store.py` (foundation, no breaking changes)
2. Phase 2 — enhanced upload endpoint + type suggestion (backward compatible)
3. Phase 3 — new endpoints (versions, metadata, listing enhancement)
4. Phase 4 — upload UI with smart classification, wired into both locations
5. Phase 5 — browser + detail page integration (version history, classification editing)

---

## Key Files to Modify

| File | Change |
|------|--------|
| `server/app/workspace_document_store.py` | **NEW** — DynamoDB store for workspace docs |
| `server/app/main.py` | Upload, listing, suggest-type, version/metadata endpoints |
| `server/app/changelog_store.py` | Reuse existing (no changes needed) |
| `client/components/documents/document-upload.tsx` | Add type dropdown with smart suggestion |
| `client/components/documents/document-browser.tsx` | Show enriched metadata, general types in filter |
| `client/app/documents/page.tsx` | Wire upload component into documents page |
| `client/app/documents/[id]/page.tsx` | Version history panel, re-upload, edit classification |
| `client/components/chat-simple/simple-chat-interface.tsx` | Add file attachment button to chat input |
| `client/app/api/documents/upload/route.ts` | Forward new form fields |
| `client/app/api/documents/suggest-type/route.ts` | **NEW** — proxy for type suggestion |
| `client/app/api/documents/[id]/versions/route.ts` | **NEW** — proxy for version history + upload |
| `client/app/api/documents/[id]/metadata/route.ts` | **NEW** — proxy for metadata updates |
| `client/types/chat.ts` | Extend DocumentType with general categories |

---

## Verification

1. **Upload**: Upload a PDF with `document_type=sow` → verify S3 key is versioned, DynamoDB record exists
2. **Smart suggest**: Upload file named `SOW_cloud_services.docx` → dropdown pre-selects "SOW"
3. **List**: `GET /api/documents` returns uploaded doc with metadata (doc_type, version, document_id)
4. **Version**: Upload new version of same doc → verify v2 S3 key, version history has 2 entries
5. **Classify**: `PATCH /api/documents/{id}/metadata` with new doc_type → verify update
6. **UI - Documents page**: Upload via drag-and-drop with type dropdown → doc appears in browser with correct type badge
7. **UI - Chat sidebar**: Attach file from chat → upload succeeds, doc accessible
8. **Detail page**: Open doc → version history tab shows all versions, can download any, can edit classification
9. **Backend tests**: `python -m pytest tests/ -v` passes
10. **Frontend check**: `npx tsc --noEmit` passes
