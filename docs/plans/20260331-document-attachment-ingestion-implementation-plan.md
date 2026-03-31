# Document Attachment Ingestion Implementation Plan

## Goal

Implement first-class document attachments that can be uploaded to a workspace or attached to a package, stored in S3, normalized into markdown-compatible text for the existing pipeline, reused as AI context, edited later, and saved back to S3 with predictable version behavior.

Primary user flow:

1. User uploads a `.doc`, `.docx`, or `.txt` requirements document.
2. The original file is stored in S3.
3. The system extracts text and a normalized markdown representation.
4. The attachment becomes selectable and usable as context in chat and package workflows.
5. The user asks for something like: "Create an SOW from this requirements document."
6. The AI uses the attachment content plus package/session context to generate a draft through the existing document pipeline.
7. If the user edits the attachment or the generated document, the updated artifact is saved back to S3 and tracked.

## What Already Exists

The codebase already has a strong foundation. The feature should extend these paths instead of replacing them.

Current backend capabilities:

- `server/app/routers/documents.py`
  - `POST /api/documents/upload` uploads files to S3.
  - Upload flow already classifies documents and creates a markdown sidecar.
  - `POST /api/documents/{upload_id}/assign-to-package` already turns an uploaded file into a canonical package document version.
  - `GET /api/documents/{doc_key}` already prefers markdown sidecars for binary previews.
  - `PUT /api/documents/{doc_key}` already updates text docs.
  - DOCX/XLSX edit routes already exist.
- `server/app/document_markdown_service.py`
  - Converts `txt`, `md`, `pdf`, `docx`, `xlsx` to markdown-like text.
- `server/app/document_service.py`
  - Canonical versioned package document creation with S3 + DynamoDB + changelog.
- `server/app/document_ai_edit_service.py`
  - DOCX preview extraction and save-back to S3.
- `client/lib/document-api.ts`
  - Frontend upload and package assignment client exists.
- `client/app/api/documents/upload/route.ts`
  - Next.js upload proxy exists and already forwards query parameters.
- `client/app/api/documents/[id]/assign-to-package/route.ts`
  - Package assignment proxy exists.

Current limitations:

- Uploads are durable in S3, but the upload registry is temporary TTL metadata, not a durable attachment record.
- Workspace uploads are not first-class documents with history, metadata, and AI-ready linkage.
- The AI document-generation path does not yet have an explicit attachment-ingestion layer that says "these uploaded docs are part of this request."
- `.doc` support is only best-effort today and will be unreliable without a dedicated conversion fallback.
- Workspace document edits mostly overwrite in place; package docs version properly.
- There is no explicit attachment-to-prompt context builder for requests like "Create an SOW from this requirements doc."

## Product Scope

This feature should cover four related capabilities:

### 1. Durable attachment storage

Every uploaded attachment must be:

- stored in S3 as the source-of-truth binary
- addressable by durable metadata in DynamoDB
- linked to either:
  - a workspace document
  - a package attachment
  - both, if you choose to allow promotion/copy semantics

### 2. Parsed and normalized content

Every supported attachment must also produce:

- extracted plain text
- normalized markdown suitable for prompt context and template filling
- extraction metadata such as parse status, parser used, confidence, and fallback mode

### 3. AI-usable attachment context

Attachments must be usable in downstream workflows:

- chat requests
- `create_document` generation
- package-level generation
- future extraction/template-fill flows

### 4. Save-back behavior

When a user edits an uploaded document:

- the resulting artifact must be written back to S3
- metadata must reflect the new current version or overwrite strategy
- the normalized markdown must be refreshed so AI sees the latest content

## Recommended Design Decisions

### 1. Treat uploads as durable documents, not transient uploads

Current upload metadata under `UPLOAD#{tenant}` is only a staging record. Keep that only for short-lived assignment UX if needed, but introduce a real persistent store for user attachments.

Recommendation:

- add a durable `workspace_document_store.py`
- persist attachment records immediately at upload time
- keep TTL upload records only if the current UI still depends on `upload_id`

### 2. Preserve original binary, store normalized markdown separately

Do not force the original upload to become markdown-only.

Persist both:

- original artifact: source of truth for download and fidelity
- normalized markdown sidecar: source of truth for AI context and text preview where appropriate

This matches the existing package-document pattern in `document_service.py`.

### 3. Use versioned S3 keys for workspace attachments

Package docs already version correctly. Workspace attachments should do the same.

Recommended workspace S3 shape:

```text
eagle/{tenant_id}/{user_id}/workspace-documents/{document_id}/v{version}/{safe_filename}
```

Recommended markdown sidecar:

```text
eagle/{tenant_id}/{user_id}/workspace-documents/{document_id}/v{version}/{safe_filename}.content.md
```

This is better than the current flat upload path:

```text
eagle/{tenant_id}/{user_id}/uploads/{upload_id}/{safe_filename}
```

### 4. Normalize all AI context to markdown

The generation pipeline already expects markdown-oriented content and templates. The attachment ingestion layer should always hand downstream prompt builders a markdown-normalized string plus attachment metadata.

### 5. Explicitly separate attachment ingestion from document generation

Do not bury attachment logic inside `create_document`.

Instead:

- build a dedicated attachment context service
- let `create_document` consume already-resolved attachment context

This keeps upload/storage concerns separate from prompt assembly concerns.

### 6. Define `.doc` support honestly

`.docx` and `.txt` are straightforward.

Legacy `.doc` is not.

Recommendation:

- Phase 1: support `.docx` and `.txt` as production-ready
- Phase 2: allow `.doc` upload but mark parsing as best-effort
- Phase 3: add a real `.doc` conversion fallback using LibreOffice or another converter if required by users

## Proposed Architecture

### New concept: Attachment Record

Add a persistent workspace/package attachment model.

Suggested record shape:

```json
{
  "document_id": "uuid",
  "tenant_id": "dev-tenant",
  "user_id": "dev-user",
  "scope": "workspace",
  "package_id": null,
  "title": "Genomic Technical Requirements",
  "original_filename": "UC16 convert tech req - Genomic_Technical_Requirements.docx",
  "file_type": "docx",
  "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "status": "ready",
  "parse_status": "complete",
  "parse_mode": "docx_markdown",
  "current_version": 1,
  "s3_bucket": "eagle-documents-...",
  "s3_key": "eagle/.../workspace-documents/{document_id}/v1/file.docx",
  "markdown_s3_key": "eagle/.../workspace-documents/{document_id}/v1/file.docx.content.md",
  "size_bytes": 12345,
  "content_hash": "sha256...",
  "classification": {
    "doc_type": "requirements",
    "confidence": 0.81,
    "method": "filename"
  },
  "tags": ["requirements", "source-document"],
  "created_at": "...",
  "updated_at": "..."
}
```

### New concept: Attachment Context

When the user asks for generation, resolve one or more attachments into a compact prompt-ready structure:

```json
{
  "documents": [
    {
      "document_id": "uuid",
      "title": "Genomic Technical Requirements",
      "source_scope": "workspace",
      "package_id": null,
      "file_type": "docx",
      "content_markdown": "# Requirements ...",
      "summary": "Optional short auto-summary",
      "selected_by_user": true
    }
  ]
}
```

This object is what should be injected into generation prompts and tool context.

## Data Model Changes

### 1. New durable workspace document store

Create:

- `server/app/workspace_document_store.py`

Suggested DynamoDB layout:

```text
PK: USERDOC#{tenant_id}#{user_id}
SK: USERDOC#{document_id}
```

Version items:

```text
PK: USERDOCVER#{tenant_id}#{document_id}
SK: VERSION#{version:04d}
```

Suggested fields:

- `document_id`
- `tenant_id`
- `user_id`
- `scope`
- `package_id`
- `title`
- `doc_type`
- `classification`
- `file_type`
- `content_type`
- `status`
- `parse_status`
- `parse_mode`
- `current_version`
- `s3_bucket`
- `s3_key`
- `markdown_s3_key`
- `size_bytes`
- `content_hash`
- `original_filename`
- `created_at`
- `updated_at`

### 2. Optional attachment link table for chat/session scoping

If you want chat-level explicit attachment selection, add linkage records:

```text
PK: SESSIONDOC#{tenant_id}#{session_id}
SK: DOCUMENT#{document_id}
```

This avoids overloading session metadata blobs.

Fields:

- `document_id`
- `selected_at`
- `selected_by_user_id`
- `source_scope`
- `package_id`

### 3. Package attachment policy

There are two valid choices. Pick one and keep it consistent.

Option A:

- package attachments are just durable workspace documents with `package_id` linkage metadata

Option B:

- package attachments become canonical package documents immediately via `create_package_document_version`

Recommendation:

- use Option A for "reference/input documents"
- keep Option B for generated deliverables

That gives you a clean split:

- attachments: source material
- package documents: outputs/deliverables

## Backend Implementation Plan

## Phase 1: Durable Workspace Attachment Foundation

### Files

- new: `server/app/workspace_document_store.py`
- modify: `server/app/routers/documents.py`
- optionally modify: `server/app/document_key_utils.py`
- optionally modify: `server/app/changelog_store.py`

### Tasks

1. Create durable CRUD helpers for workspace documents.
2. Add helpers:
   - `create_workspace_document()`
   - `get_workspace_document()`
   - `list_workspace_documents()`
   - `create_workspace_document_version()`
   - `get_workspace_document_versions()`
   - `update_workspace_document_metadata()`
3. Standardize workspace-document key parsing in `document_key_utils.py`.
4. Add changelog support for workspace-document create/update/version actions.

### Acceptance criteria

- uploading a file creates a persistent record, not only a TTL upload record
- listing workspace documents returns durable metadata
- each workspace attachment has a stable `document_id`

## Phase 2: Upgrade Upload Endpoint Into Durable Attachment Creation

### Files

- modify: `server/app/routers/documents.py`
- modify: `client/lib/document-api.ts`
- modify: `client/app/api/documents/upload/route.ts`

### Tasks

Refactor `POST /api/documents/upload` so it does all of the following:

1. Validate allowed file types.
2. Generate a durable `document_id`.
3. Upload the original artifact to versioned workspace-document S3 storage.
4. Convert to markdown using `document_markdown_service.py`.
5. Store the markdown sidecar in S3.
6. Persist durable metadata in `workspace_document_store.py`.
7. Optionally still create a TTL `upload_id` record for current assignment modal behavior.
8. Return both:
   - `document_id`
   - `upload_id` if still needed for compatibility

Suggested response shape:

```json
{
  "document_id": "uuid",
  "upload_id": "uuid",
  "key": "eagle/.../workspace-documents/...",
  "markdown_key": "eagle/...content.md",
  "filename": "Genomic_Technical_Requirements.docx",
  "size_bytes": 12345,
  "content_type": "...",
  "file_type": "docx",
  "classification": {},
  "parse_status": "complete",
  "parse_mode": "docx_markdown",
  "package_context": { "mode": "workspace", "package_id": null }
}
```

### Important refactor note

The repo has overlapping document endpoint logic in both `main.py` and `routers/documents.py`. The included router is the right place to centralize this feature. Avoid implementing attachment logic in both places.

### Acceptance criteria

- upload creates durable document metadata
- upload returns a persistent `document_id`
- markdown sidecar exists for `.txt` and `.docx` when parsing succeeds

## Phase 3: Add Workspace Versioning and Save-Back

### Files

- modify: `server/app/routers/documents.py`
- modify: `server/app/document_ai_edit_service.py`
- new or modify: `server/app/workspace_document_store.py`

### Tasks

Add version-aware workspace save behavior.

For text updates:

- change workspace `PUT /api/documents/{doc_key}` from direct overwrite to new-version creation when the key belongs to a durable workspace document

For DOCX updates:

- when `save_docx_preview_edits()` updates a workspace doc, write a new version record instead of blind overwrite
- refresh the markdown sidecar from the updated DOCX bytes after save

For binary replacement:

- add `POST /api/documents/{document_id}/versions`
- accept multipart file upload to replace the source artifact with a new version
- rebuild the markdown sidecar from the new binary

For history:

- add `GET /api/documents/{document_id}/versions`

### Behavior recommendation

Use versioned saves for:

- workspace attachments
- package deliverables

Avoid mixed semantics where workspace docs overwrite while package docs version. That difference will create bugs in AI context freshness and change history.

### Acceptance criteria

- editing a workspace `.docx` writes a new S3 version path and new metadata version
- normalized markdown updates after every save
- version history can be queried

## Phase 4: Attachment Context Resolution Service

### Files

- new: `server/app/attachment_context_service.py`
- modify: `server/app/strands_agentic_service.py`
- modify: `server/app/tools/create_document_support.py`
- optionally modify: `server/app/session_store.py` or add session-document linkage logic

### Why this phase matters

This is the missing layer between "uploaded file exists" and "AI can use it to draft an SOW."

### Responsibilities of `attachment_context_service.py`

Provide helpers like:

- `resolve_session_attachments(tenant_id, user_id, session_id)`
- `resolve_package_attachments(tenant_id, package_id)`
- `resolve_explicit_document_ids(tenant_id, user_id, document_ids)`
- `build_attachment_prompt_context(documents, max_chars=...)`

For each selected attachment, load:

- metadata
- current markdown sidecar if present
- fallback preview text if sidecar missing

Return compact prompt-ready structures.

### Prompt integration strategy

For generation requests, augment prompt assembly with an explicit block:

```text
[Attachment Context]
Document 1: Genomic Technical Requirements
Source: workspace attachment
Normalized content:
...
```

Inject this into the prompt builder before `create_document` is called.

### Selection strategy

You need one of these models:

Option A:

- user explicitly selects one or more attachments in UI before asking

Option B:

- system implicitly includes all attachments attached to the active package/session

Recommendation:

- support both
- explicit user-selected documents win
- otherwise fall back to active package/session attachments

### Acceptance criteria

- asking "create an SOW from this requirements doc" uses the uploaded document markdown in the prompt
- the model can identify which attachment drove the output
- the attachment list is deterministic and inspectable in logs

## Phase 5: Integrate Attachment Context Into Document Generation

### Files

- modify: `server/app/strands_agentic_service.py`
- modify: `server/app/tools/document_generation.py`
- modify: `server/app/tools/create_document_support.py`

### Tasks

1. Extend generation request handling to accept explicit attachment identifiers.
2. When a create-document intent is detected, resolve attachment context before tool dispatch.
3. Merge:
   - user request
   - package context
   - attachment context
   - template context
4. Update generation prompts so the model knows:
   - this uploaded attachment is source material
   - generated output should synthesize from it, not quote it blindly
   - missing information should still be flagged per current document rules

### Important implementation detail

Do not stuff full binary previews or massive unbounded text into prompts.

Add truncation and prioritization:

- use markdown sidecar
- cap per-document included size
- optionally prepend an auto-summary for long attachments
- include the most relevant sections first if retrieval/chunking is added later

### Future-friendly option

If attachments become large, move from full-document injection to chunk retrieval. For now, a bounded markdown injection approach is enough.

### Acceptance criteria

- SOW generation from a requirements attachment works without manually copying document text into chat
- generated output still persists through the existing package document pipeline

## Phase 6: UI and UX Changes

### Files

- modify: `client/lib/document-api.ts`
- modify: `client/components/chat-simple/chat-upload-button.tsx`
- modify: `client/components/chat-simple/simple-chat-interface.tsx`
- modify: `client/components/chat-simple/package-selector-modal.tsx`
- modify: `client/app/documents/[id]/page.tsx`
- modify: `client/app/documents/page.tsx`

### Upload UX requirements

After upload, the UI should show:

- upload success
- file type
- parse status
- whether markdown extraction succeeded
- current scope:
  - workspace
  - attached to package

### Attachment UX requirements

In chat:

- users should be able to attach one or more existing uploaded docs to the current conversation
- the selected attachment should be visible in the composer or activity panel
- the user should be able to remove it before send

In package view:

- show "Reference Attachments" separately from generated package documents
- generated outputs should remain in the canonical package-documents area

### Document detail UX

For uploaded attachments, show:

- original filename
- current version
- parse status
- preview mode
- markdown preview if available
- download original
- upload replacement/new version
- edit for supported formats

### Recommendation

Do not mix source attachments and deliverable documents in the same flat list without labels. That will create user confusion.

Use clear groupings:

- Source Attachments
- Generated Documents

## Phase 7: Formatting and Normalization Rules

### Files

- modify: `server/app/document_markdown_service.py`
- optionally modify: `server/app/template_standardizer.py`
- new: `server/app/document_ingestion_service.py`

### Goal

Ensure uploaded attachment content conforms to the formatting expectations of the existing markdown-first generation pipeline.

### Proposed normalization pipeline

1. Parse source file into raw text/structure.
2. Normalize into markdown:
   - headings
   - lists
   - tables
   - paragraph spacing
3. Strip junk:
   - repeated blank lines
   - control characters
   - malformed table rows where possible
4. Preserve useful semantics:
   - section headers
   - numbered requirements
   - checkbox state if available
5. Store both:
   - raw extracted text if needed for debugging
   - final normalized markdown for downstream AI use

### Recommendation

Create `document_ingestion_service.py` as an orchestration layer that calls:

- classification
- markdown conversion
- optional standardization
- metadata persistence

This prevents `routers/documents.py` from becoming the permanent home for business logic.

### `.docx` requirements

For `.docx`, preserve:

- headings
- paragraphs
- bullet lists
- tables
- checkbox lines where possible

### `.txt` requirements

For `.txt`, preserve:

- line breaks where meaningful
- markdown if already present
- simple requirement numbering

### `.doc` requirements

For `.doc`, define one of:

- parse supported with fallback converter
- upload accepted but parse may be partial
- upload rejected until converter exists

Recommendation:

- accept upload
- mark parse status clearly
- log parse mode
- avoid pretending extraction is reliable until a real converter is implemented

## Phase 8: Package Attachment Flow

### Files

- modify: `server/app/routers/documents.py`
- modify: `server/app/routers/packages.py`
- optionally new: `server/app/package_attachment_store.py`

### Recommended behavior

When a user "attaches to a package," do not immediately convert the attachment into a generated package deliverable unless the user intends that.

Instead:

1. Keep it as a reference attachment.
2. Link it to the package.
3. Make it available to package-aware AI generation.

Only use `create_package_document_version()` when:

- generating an actual package document output
- or intentionally promoting an uploaded attachment into a formal package deliverable

### Why this matters

Your example document is a requirements source doc. It should influence SOW generation, but it is not itself the SOW deliverable.

### Suggested endpoints

- `POST /api/packages/{package_id}/attachments`
  - attach an existing workspace document to a package
- `GET /api/packages/{package_id}/attachments`
  - list package reference attachments
- `DELETE /api/packages/{package_id}/attachments/{document_id}`
  - detach without deleting source

Keep existing:

- `POST /api/documents/{upload_id}/assign-to-package`

But redefine or eventually rename it if it currently implies "convert to package deliverable." That name is ambiguous for the new workflow.

## Phase 9: Observability and Auditability

### Files

- modify: `server/app/changelog_store.py`
- modify: `server/app/telemetry/...` as needed

### Track these events

- upload started
- upload completed
- parse completed
- parse failed
- markdown sidecar created
- attachment linked to session
- attachment linked to package
- attachment used in generation
- attachment edited
- new version created

### Log fields

- `document_id`
- `upload_id`
- `package_id`
- `session_id`
- `source_scope`
- `parse_mode`
- `parse_status`
- `version`
- `s3_key`
- `markdown_s3_key`

### Why this matters

When a user says "the SOW ignored my uploaded requirements doc," you need to be able to answer:

- was the attachment parsed?
- was markdown generated?
- was it linked to the session/package?
- was it included in prompt context?

## Phase 10: Testing Plan

### Backend tests

Add or extend tests under `server/tests/`.

Recommended test files:

- `test_upload_endpoints.py`
- `test_document_markdown_service.py`
- new: `test_workspace_document_store.py`
- new: `test_attachment_context_service.py`
- extend: `test_document_ai_edit_service.py`
- extend: `test_canonical_package_document_flow.py`

### Backend cases

1. Upload `.txt` creates:
   - S3 object
   - markdown sidecar
   - durable metadata record
2. Upload `.docx` creates:
   - S3 object
   - markdown sidecar
   - parse metadata
3. Upload `.doc`:
   - accepted or rejected according to chosen policy
   - parse status accurately reported
4. Workspace edit of `.txt` creates v2 and refreshes markdown.
5. DOCX preview edit creates v2 and refreshes markdown sidecar.
6. Package attachment linking persists and can be listed.
7. Attachment context resolution returns selected docs in deterministic order.
8. `create_document` path receives attachment context and generated output reflects source requirements.
9. Unsupported file types are rejected.
10. Large uploads obey size limits.

### Frontend tests

Add or extend tests under `client/tests/`.

Recommended areas:

- upload route proxy
- assign/attach flows
- chat attachment selection
- package attachment list
- document detail version history

### End-to-end cases

1. Upload a requirements `.docx`.
2. Attach it to a chat or package.
3. Ask for an SOW based on that attachment.
4. Verify:
   - create-document tool is called
   - resulting draft reflects attachment content
   - resulting SOW is saved as a package document
5. Edit the source DOCX.
6. Regenerate or update the SOW.
7. Verify the new generation reflects the edited source content.

## Rollout Plan

### Step 1

Land durable workspace document store and upload refactor without changing generation behavior.

### Step 2

Land workspace versioning and save-back refresh.

### Step 3

Land session/package attachment linking APIs and UI.

### Step 4

Land attachment context injection into generation.

### Step 5

Add advanced improvements:

- chunking/retrieval for long attachments
- stronger `.doc` conversion
- attachment summaries
- relevance ranking across multiple attachments

## Open Questions To Resolve Before Coding

These are the few product decisions that affect implementation shape.

### 1. Is a package attachment a source document or a deliverable?

Recommendation:

- source attachment by default
- explicit promotion to deliverable if needed

### 2. Should workspace edits overwrite or version?

Recommendation:

- version

### 3. Should chat include all linked attachments automatically?

Recommendation:

- explicit selected attachments first
- otherwise active package attachments as fallback

### 4. What is the official `.doc` support level?

Recommendation:

- upload yes
- reliable parse no, until converter is added

### 5. Where should the durable source of truth live for workspace uploads?

Recommendation:

- DynamoDB metadata + S3 artifacts
- not browser local storage
- not TTL upload records

## Suggested Implementation Order

1. Create `workspace_document_store.py`.
2. Refactor upload to create durable workspace documents and markdown sidecars.
3. Add workspace versioning and version-history endpoints.
4. Add package/session attachment-linking endpoints.
5. Build `attachment_context_service.py`.
6. Inject attachment context into `create_document` flows.
7. Update chat and package UI to select and display source attachments.
8. Add tests and observability.

## Practical First Slice

If you want the smallest vertical slice that delivers user value quickly, build this first:

1. Upload `.docx` and `.txt` into durable workspace documents.
2. Persist original file + markdown sidecar + metadata.
3. Let the user select one uploaded document in chat.
4. Inject that document's markdown into `create_document` prompt context.
5. Generate an SOW into the existing package document pipeline.

That slice gets you from:

- "I uploaded a requirements doc"

to:

- "Create an SOW from this requirements doc"

without waiting for the full attachment/version/history UI to be complete.

---

## Phase 0: Security & File Validation (Pre-requisite)

This phase must be completed before Phase 2 (upload refactor) to ensure all uploads are validated.

### Files

- new: `server/app/file_validation_service.py`
- modify: `server/app/routers/documents.py`

### Goal

Implement defense-in-depth file validation:
1. Magic byte validation (verify file content matches declared MIME type)
2. DOCX/XLSX macro detection (VBA scanning)
3. Legacy DOC/XLS OLE scanning (best-effort macro detection)
4. Markdown content sanitization (XSS prevention)

### 1. Magic Byte Validation

**What exists:** MIME type whitelist validation at upload time.

**What's missing:** No verification that file content matches declared MIME type. A malicious actor could declare `application/pdf` but upload an executable.

**Implementation:**

Define magic byte signatures for supported types:

```python
MAGIC_SIGNATURES = {
    "application/pdf": [(b"%PDF", 0)],
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [
        (b"PK\x03\x04", 0),  # ZIP-based OOXML
    ],
    "application/msword": [
        (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", 0),  # OLE compound doc
    ],
    "text/plain": [],  # No magic bytes - validate by content
    "text/markdown": [],
}
```

Add `validate_magic_bytes(content: bytes, declared_mime: str) -> tuple[bool, Optional[str]]`:
- Returns `(is_valid, detected_type)`
- For text files, check that content has no null bytes in first 8KB
- Reject uploads where declared MIME doesn't match detected type

### 2. DOCX/XLSX Macro Detection

**What exists:** Nothing.

**What's missing:** Uploaded DOCX files could contain VBA macros that execute on open.

**Implementation:**

Add `scan_docx_for_macros(content: bytes) -> tuple[bool, list[str]]`:

DOCX files are ZIP archives. Scan for:
- `vbaProject.bin` in archive (main macro container)
- `[Content_Types].xml` containing `macroEnabled` content type
- External relationships in `.rels` files (`TargetMode="External"`)
- Attached template relationships
- ActiveX controls
- Embedded executables (`.exe`, `.dll`, `.bat`, `.ps1`)

Return `(has_macros, findings)` where findings is a list of what was detected.

### 3. Legacy DOC/XLS OLE Scanning

**What exists:** Nothing.

**What's missing:** Legacy Office formats use OLE compound documents which can contain VBA.

**Implementation:**

Add `scan_ole_for_macros(content: bytes) -> tuple[bool, list[str]]`:

This is best-effort without full OLE parsing. Scan for byte patterns:
- `_VBA_PROJECT` stream indicator
- `Auto_Open`, `Document_Open`, `Workbook_Open` macro names
- `Shell(`, `WScript`, `PowerShell` command indicators
- Embedded OLE object markers

For production hardening, consider integrating `oletools` library.

### 4. Markdown Content Sanitization

**What exists:** HTML escaping in PDF/DOCX export only.

**What's missing:** Markdown stored in S3 could contain XSS payloads that execute when rendered in the web UI.

**Implementation:**

Add `sanitize_markdown(content: str) -> str`:

Remove or escape dangerous patterns:
- `<script>` tags
- JavaScript/VBScript URLs (`javascript:`, `vbscript:`)
- Event handler attributes (`onclick=`, `onerror=`, etc.)
- `<iframe>`, `<object>`, `<embed>` tags
- HTML data URLs (`data:text/html`)
- CSS `@import` directives

Preserve safe formatting tags: `p`, `br`, `b`, `i`, `strong`, `em`, `code`, `pre`, `ul`, `ol`, `li`, `h1-h6`, `blockquote`, `table`.

### 5. Validation Result Structure

```python
@dataclass
class ValidationResult:
    status: Literal["passed", "failed", "warning"]
    file_type: str
    detected_type: Optional[str]
    threats: list[str]  # "mime_mismatch", "macro_detected", "suspicious_content"
    warnings: list[str]
    details: dict

    @property
    def is_safe(self) -> bool:
        return self.status == "passed" and len(self.threats) == 0
```

### 6. Integration with Upload Endpoint

Modify `POST /api/documents/upload`:

```python
from ..file_validation_service import validate_file, ValidationStatus

# After reading body, before S3 upload:
validation = validate_file(
    content=body,
    filename=file.filename,
    declared_mime=content_type,
    max_size_bytes=_MAX_UPLOAD_BYTES,
    allow_macros=False,  # Configurable per-tenant later
)

if validation.status == ValidationStatus.FAILED:
    raise HTTPException(
        status_code=422,
        detail={
            "error": "File validation failed",
            "threats": validation.threats,
            "details": validation.details,
        },
    )

# Store validation result in upload metadata
persist_upload(..., {
    ...,
    "validation": validation.to_dict(),
})
```

### 7. Markdown Sanitization Integration

After converting to markdown, sanitize before storing:

```python
from ..file_validation_service import validate_and_sanitize_markdown

if markdown_content:
    sanitized, md_validation = validate_and_sanitize_markdown(markdown_content)
    if md_validation.threats:
        logger.warning("Sanitized threats from markdown: %s", md_validation.threats)
    markdown_content = sanitized
```

### Acceptance Criteria

- Upload of file with mismatched magic bytes returns 422 with `mime_mismatch` threat
- Upload of DOCX with `vbaProject.bin` returns 422 with `macro_detected` threat
- Upload of legacy DOC with VBA indicators returns 422 with `macro_detected` threat
- Markdown containing `<script>` tags is sanitized before S3 storage
- Validation result is stored in upload metadata for audit
- Test coverage for all threat detection scenarios

### Testing

Add `server/tests/test_file_validation_service.py`:

```python
def test_magic_bytes_pdf_valid():
    content = b"%PDF-1.4 ..."
    valid, detected = validate_magic_bytes(content, "application/pdf")
    assert valid is True

def test_magic_bytes_mismatch():
    content = b"PK\x03\x04..."  # ZIP signature
    valid, detected = validate_magic_bytes(content, "application/pdf")
    assert valid is False
    assert detected == "application/vnd.openxmlformats-..."

def test_docx_macro_detection():
    # Create a DOCX with vbaProject.bin
    has_macros, findings = scan_docx_for_macros(macro_docx_bytes)
    assert has_macros is True
    assert "VBA macro container found" in findings[0]

def test_markdown_sanitization():
    content = "Hello <script>alert('xss')</script> world"
    sanitized = sanitize_markdown(content)
    assert "<script>" not in sanitized
```

---

## Error Handling Strategy

### Structured Error Codes

Add standardized error codes for client-side handling:

```python
class DocumentErrorCode(str, Enum):
    VALIDATION_FAILED = "DOC_001"
    MIME_MISMATCH = "DOC_002"
    MACRO_DETECTED = "DOC_003"
    OVERSIZED = "DOC_004"
    S3_UPLOAD_FAILED = "DOC_005"
    S3_RETRIEVAL_FAILED = "DOC_006"
    PARSE_FAILED = "DOC_007"
    NOT_FOUND = "DOC_008"
    ACCESS_DENIED = "DOC_009"
    VERSION_CONFLICT = "DOC_010"
```

### Error Response Format

Standardize all document endpoint errors:

```json
{
  "error": {
    "code": "DOC_003",
    "message": "File contains VBA macros which are not allowed",
    "details": {
      "threats": ["macro_detected"],
      "findings": ["VBA macro container found: word/vbaProject.bin"]
    }
  }
}
```

### Retry Logic for S3 Operations

Add retry decorator for transient S3 failures:

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from botocore.exceptions import ClientError

def is_retryable_s3_error(exception: ClientError) -> bool:
    error_code = exception.response.get("Error", {}).get("Code", "")
    return error_code in ("ServiceUnavailable", "SlowDown", "InternalError")

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(lambda e: isinstance(e, ClientError) and is_retryable_s3_error(e)),
)
def s3_put_with_retry(s3, bucket: str, key: str, body: bytes, content_type: str):
    s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType=content_type)
```

### Partial Success Tracking

When optional steps fail (markdown extraction, standardization), track in response:

```json
{
  "key": "...",
  "upload_id": "...",
  "processing_status": {
    "upload": "success",
    "markdown_extraction": "failed",
    "standardization": "skipped",
    "validation": "passed"
  },
  "warnings": ["Markdown extraction failed: unsupported encoding"]
}
```

---

## Concurrency & Version Locking

### Problem

Current version number generation is vulnerable to race conditions:

```python
# VULNERABLE: Two concurrent requests can read same max version
history = get_document_history(tenant_id, package_id, doc_type)
next_version = max(d["version"] for d in history) + 1
```

### Solution: Atomic Version Counter

Add a version counter item per document:

```python
def get_next_version_atomic(tenant_id: str, document_id: str) -> int:
    """Atomically increment and return next version number."""
    table = get_table()
    response = table.update_item(
        Key={
            "PK": f"DOCVER#{tenant_id}",
            "SK": f"COUNTER#{document_id}",
        },
        UpdateExpression="SET version_counter = if_not_exists(version_counter, :zero) + :one",
        ExpressionAttributeValues={
            ":zero": 0,
            ":one": 1,
        },
        ReturnValues="UPDATED_NEW",
    )
    return response["Attributes"]["version_counter"]
```

### Solution: Optimistic Locking for Updates

Add conditional writes to prevent lost updates:

```python
def update_workspace_document(
    tenant_id: str,
    document_id: str,
    expected_version: int,
    updates: dict,
) -> bool:
    """Update document only if version matches expected."""
    try:
        table.update_item(
            Key={"PK": f"USERDOC#{tenant_id}", "SK": f"USERDOC#{document_id}"},
            UpdateExpression="SET ...",
            ConditionExpression="current_version = :expected",
            ExpressionAttributeValues={":expected": expected_version, ...},
        )
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise VersionConflictError(
                f"Document was modified. Expected version {expected_version}."
            )
        raise
```

### API Changes

Add `If-Match` header support for version-aware updates:

```python
@router.put("/{document_id}")
async def update_document(
    document_id: str,
    body: UpdateDocumentRequest,
    if_match: Optional[str] = Header(None, alias="If-Match"),
    user: UserContext = Depends(get_user_from_header),
):
    if if_match:
        expected_version = int(if_match)
        # Use conditional update
    else:
        # Warn in response that optimistic locking was not used
```

---

## Quotas & Limits

### Configuration Structure

Add quota configuration to tenant/user settings:

```python
@dataclass
class DocumentQuotas:
    max_file_size_bytes: int = 25 * 1024 * 1024  # 25 MB
    max_uploads_per_day: int = 100
    max_storage_bytes: int = 500 * 1024 * 1024  # 500 MB total
    max_attachments_per_session: int = 10
    max_attachments_per_package: int = 25
    allowed_mime_types: set[str] = field(default_factory=lambda: ALLOWED_UPLOAD_MIME_TYPES)
```

### Quota Enforcement

Add quota check before upload:

```python
def check_upload_quota(tenant_id: str, user_id: str, file_size: int) -> None:
    """Raise HTTPException if quota exceeded."""
    quotas = get_tenant_quotas(tenant_id)
    usage = get_user_storage_usage(tenant_id, user_id)

    if usage.total_bytes + file_size > quotas.max_storage_bytes:
        raise HTTPException(
            status_code=413,
            detail={
                "error": "Storage quota exceeded",
                "current_usage": usage.total_bytes,
                "limit": quotas.max_storage_bytes,
            },
        )

    if usage.uploads_today >= quotas.max_uploads_per_day:
        raise HTTPException(
            status_code=429,
            detail="Daily upload limit reached",
        )
```

### Usage Tracking

Track storage usage in DynamoDB:

```python
# Update on upload
table.update_item(
    Key={"PK": f"USAGE#{tenant_id}", "SK": f"USER#{user_id}"},
    UpdateExpression="""
        SET total_bytes = if_not_exists(total_bytes, :zero) + :size,
            upload_count = if_not_exists(upload_count, :zero) + :one,
            last_upload = :now
    """,
    ExpressionAttributeValues={
        ":zero": 0,
        ":one": 1,
        ":size": file_size,
        ":now": datetime.now(timezone.utc).isoformat(),
    },
)
```

---

## Cleanup & Deletion Policy

### Document Deletion Endpoint

Add explicit document deletion with S3 cleanup:

```python
@router.delete("/{document_id}")
async def delete_workspace_document(
    document_id: str,
    user: UserContext = Depends(get_user_from_header),
):
    """Delete a workspace document and all its versions from S3."""
    doc = get_workspace_document(user.tenant_id, user.user_id, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Delete all S3 versions
    versions = list_workspace_document_versions(user.tenant_id, document_id)
    s3 = get_s3()
    for version in versions:
        try:
            s3.delete_object(Bucket=version["s3_bucket"], Key=version["s3_key"])
            if version.get("markdown_s3_key"):
                s3.delete_object(Bucket=version["s3_bucket"], Key=version["markdown_s3_key"])
        except ClientError as e:
            logger.warning("Failed to delete S3 object: %s", e)

    # Delete DynamoDB records
    delete_workspace_document_records(user.tenant_id, user.user_id, document_id)

    # Update usage tracking
    update_storage_usage(user.tenant_id, user.user_id, -doc["size_bytes"])

    return {"deleted": document_id, "versions_deleted": len(versions)}
```

### Cascade Behavior

Define cascade rules:

| Parent Deleted | Child Behavior |
|----------------|----------------|
| Workspace | Workspace documents remain (orphaned, user can still access) |
| Package | Package attachments detached, source documents remain |
| Session | Session attachment links removed, source documents remain |
| User | All user documents soft-deleted, S3 retained for compliance |

### S3 Lifecycle Policy (CDK)

Already exists in `storage-stack.ts`:
- Non-current versions → Infrequent Access after 90 days
- Non-current versions → Deleted after 365 days

No changes needed unless retention requirements change.

---

## Infrastructure Updates

### DynamoDB: New GSI for Workspace Documents

Add GSI to support listing documents by user:

```typescript
// storage-stack.ts
metadataTable.addGlobalSecondaryIndex({
  indexName: "user-documents-index",
  partitionKey: { name: "tenant_user_id", type: dynamodb.AttributeType.STRING },
  sortKey: { name: "created_at", type: dynamodb.AttributeType.STRING },
  projectionType: dynamodb.ProjectionType.ALL,
});
```

Composite key format: `{tenant_id}#{user_id}`

### IAM: Backend Write Access to Metadata Table

Current app role has READ-ONLY access to metadata table. For workspace documents, need write access:

```typescript
// core-stack.ts - update appRole policy
{
  Sid: "MetadataTableReadWrite",
  Effect: "Allow",
  Action: [
    "dynamodb:GetItem",
    "dynamodb:Query",
    "dynamodb:Scan",
    "dynamodb:BatchGetItem",
    "dynamodb:PutItem",      // ADD
    "dynamodb:UpdateItem",   // ADD
    "dynamodb:DeleteItem",   // ADD
  ],
  Resource: [metadataTableArn, `${metadataTableArn}/index/*`],
}
```

### S3: Access Logging (Optional)

For audit trail of document access, enable S3 access logging:

```typescript
// storage-stack.ts
const accessLogsBucket = new s3.Bucket(this, "AccessLogsBucket", {
  bucketName: `eagle-access-logs-${account}-${env}`,
  lifecycleRules: [{ expiration: cdk.Duration.days(90) }],
});

documentBucket.addToResourcePolicy(new iam.PolicyStatement({
  principals: [new iam.ServicePrincipal("logging.s3.amazonaws.com")],
  actions: ["s3:PutObject"],
  resources: [`${accessLogsBucket.bucketArn}/*`],
}));
```

---

## Updated Implementation Order

With security as a prerequisite:

1. **Phase 0:** Create `file_validation_service.py` with magic bytes, macro scanning, sanitization
2. **Phase 1:** Create `workspace_document_store.py` with atomic versioning
3. **Phase 2:** Refactor upload to use validation + durable storage
4. **Phase 3:** Add workspace versioning with optimistic locking
5. **Phase 4:** Add package/session attachment linking
6. **Phase 5:** Build `attachment_context_service.py`
7. **Phase 6:** Inject attachment context into generation
8. **Phase 7:** Update UI for attachment selection
9. **Phase 8:** Add quotas and usage tracking
10. **Phase 9:** Add cleanup/deletion endpoints
11. **Phase 10:** Add tests and observability

---

## Open Questions Resolved

### 1. What happens when file validation fails?

**Decision:** Return HTTP 422 with structured error containing threat details. Do not store the file in S3.

### 2. Should macros be allowed with a flag?

**Decision:** Default to rejecting macros. Add `allow_macros` parameter to validation for future per-tenant configuration.

### 3. What happens on version conflict?

**Decision:** Return HTTP 409 Conflict with current version number. Client should re-fetch and retry.

### 4. How are quotas enforced?

**Decision:** Check before upload. Return HTTP 413 for storage quota, HTTP 429 for rate limit.

### 5. What happens to orphaned S3 objects?

**Decision:** S3 lifecycle policy handles cleanup of non-current versions after 365 days. Explicit deletion removes immediately.
