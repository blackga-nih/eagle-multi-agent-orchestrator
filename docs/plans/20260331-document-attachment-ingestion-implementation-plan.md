# Document Attachment Ingestion Implementation Plan

## Goal

Enable users to upload documents that persist, can be assigned to packages, and can be used by the AI to generate new documents through natural conversation.

## User Flows

### Flow 1: Upload source doc → Generate from it
```
1. User uploads requirements.docx
2. User asks: "Create an SOW from my requirements doc"
3. Model finds the doc, fetches its content, generates SOW
4. SOW saved as deliverable document in package
```

### Flow 2: Upload completed doc → Assign to package
```
1. User uploads filled_igce.xlsx
2. User assigns to package (immediately or later)
3. Excel appears in package panel (right side)
4. User can view/download from package view
```

---

## Current State

### What Works (Frontend)
- Upload button accepts Excel, Word, PDF, TXT, Markdown
- Package selector modal appears after upload
- Activity panel (right side) shows package with document list
- Spreadsheet preview component for Excel files
- Document viewer for other formats

### What's Broken (Backend)
- Upload creates `UPLOAD#` TTL record → **expires in 24h** if not assigned
- Assign-to-package **re-uploads** to different S3 location (wasteful)
- No agent tools to use uploaded docs in generation

### Current Storage (3 overlapping concepts)
| Concept | Key Pattern | Behavior |
|---------|-------------|----------|
| Uploads | `UPLOAD#{tenant_id}` | TTL 24h, temporary staging |
| Package docs | `DOCUMENT#{tenant_id}` | Durable, versioned |
| Metadata table | `eagle-document-metadata` | Lambda-fed, separate table |

---

## Solution: Unified Document Model

Replace all three concepts with **one document type** where `package_id` is nullable.

### Single Document Record

```
PK: DOC#{tenant_id}
SK: DOC#{document_id}

GSI1PK: OWNER#{tenant_id}#{user_id}
GSI1SK: DOC#{created_at}

GSI2PK: PKG#{tenant_id}#{package_id}
GSI2SK: DOC#{doc_type}#{version}
```

### Fields

```python
{
    "document_id": "uuid",
    "tenant_id": "...",
    "owner_user_id": "...",
    
    # S3 location (never moves after upload)
    "s3_bucket": "...",
    "s3_key": "eagle/{tenant}/{user}/documents/{document_id}/v{version}/{filename}",
    "markdown_s3_key": ".../.content.md",
    
    # Versioning
    "current_version": 1,
    "status": "draft" | "final" | "superseded",
    
    # Classification (extracted at upload)
    "title": "...",
    "doc_type": "requirements" | "sow" | "igce" | "market_research" | ...,
    "file_type": "docx" | "xlsx" | "pdf" | "md" | "txt",
    "content_type": "application/...",
    "content_hash": "sha256...",
    
    # Package relationship (THE KEY SIMPLIFICATION)
    "package_id": null | "PKG-2026-0001",   # null = workspace doc
    "is_deliverable": false,                 # true = generated output
    
    # Metadata
    "original_filename": "...",
    "size_bytes": 12345,
    "classification": {
        "doc_type": "...",
        "confidence": 0.85,
        "method": "filename" | "content"
    },
    "created_at": "...",
    "updated_at": "...",
}
```

### Key Behaviors

| Action | Old Behavior | New Behavior |
|--------|--------------|--------------|
| Upload | TTL record, expires 24h | Durable `DOC#` record, never expires |
| Assign to package | Re-upload to new S3 key | Update `package_id` field only |
| Unassign | Not possible | Set `package_id = null` |
| List user docs | Query `UPLOAD#` (temporary) | Query GSI1 (permanent) |
| List package docs | Query `DOCUMENT#` | Query GSI2 |

### Queries

| Use Case | Query |
|----------|-------|
| User's workspace docs | GSI1 where `package_id = null` |
| User's all docs | GSI1 (no filter) |
| Package source attachments | GSI2 where `is_deliverable = false` |
| Package deliverables | GSI2 where `is_deliverable = true` |

---

## Conversational Attachment Injection

### How It Works

User: "Create an SOW from my requirements doc"

Model:
1. Calls `list_user_documents` → sees uploaded docs
2. Matches "requirements doc" to uploaded file
3. Calls `get_document_content` → fetches markdown
4. Includes content in generation prompt
5. Generates SOW

### New Agent Tools

**Tool 1: `list_user_documents`**
```python
{
    "name": "list_user_documents",
    "description": "List documents uploaded by the current user",
    "parameters": {
        "scope": "workspace | package | all",
        "package_id": "PKG-..."  # optional filter
    }
}

# Returns:
[
    {
        "document_id": "uuid",
        "title": "Genomic Requirements",
        "doc_type": "requirements",
        "filename": "Genomic_Requirements.docx",
        "package_id": null,
        "created_at": "2026-03-31T..."
    }
]
```

**Tool 2: `get_document_content`**
```python
{
    "name": "get_document_content",
    "description": "Get the text content of an uploaded document",
    "parameters": {
        "document_id": "uuid"
    }
}

# Returns:
{
    "document_id": "uuid",
    "title": "Genomic Requirements",
    "content": "# Requirements\n\n1. System shall...",
    "doc_type": "requirements",
    "truncated": false
}
```

### Token Budget

| Constraint | Value |
|------------|-------|
| Max chars per document | 50,000 (~12.5k tokens) |
| Max documents per request | 5 |
| Total attachment budget | 150,000 chars (~37.5k tokens) |

---

## Implementation

### Files to Create

| File | Purpose |
|------|---------|
| `server/app/unified_document_store.py` | CRUD operations for unified `DOC#` records |
| `server/app/tools/document_tools.py` | Agent tools: `list_user_documents`, `get_document_content` |

### Files to Modify

| File | Changes |
|------|---------|
| `server/app/routers/documents.py` | Upload creates `DOC#`, add PATCH endpoint for assign/unassign |
| `server/app/document_service.py` | Use unified store for generated docs |
| `server/app/strands_agentic_service.py` | Register new agent tools |
| `eagle-plugin/agents/supervisor/agent.md` | Document new tools |

### Files to Deprecate (Later)

- `_put_upload()`, `_get_upload()`, `_delete_upload()` in documents.py
- TTL upload pattern

---

## Implementation Steps

### Part 1: Unified Document Model (~6 hours)

| Step | Task | Time |
|------|------|------|
| 1.1 | Create `unified_document_store.py` with CRUD | ~2h |
| 1.2 | Update upload endpoint to use unified store, remove TTL | ~1h |
| 1.3 | Add `PATCH /api/documents/{id}` for assign/unassign | ~1h |
| 1.4 | Add `GET /api/documents` list endpoint with filters | ~30m |
| 1.5 | Update document generation to use unified store | ~1h |
| 1.6 | Remove deprecated upload functions | ~30m |

### Part 2: Conversational Injection (~3 hours)

| Step | Task | Time |
|------|------|------|
| 2.1 | Create `list_user_documents` tool | ~1h |
| 2.2 | Create `get_document_content` tool | ~1h |
| 2.3 | Register tools, update agent prompts | ~30m |
| 2.4 | End-to-end testing | ~30m |

**Total: ~9 hours**

---

## API Changes

### Upload Response (Enhanced)

```json
{
  "document_id": "uuid",
  "key": "eagle/.../documents/{id}/v1/file.docx",
  "filename": "requirements.docx",
  "package_id": null,
  "classification": {
    "doc_type": "requirements",
    "confidence": 0.85
  }
}
```

### Assign/Unassign (New)

```http
PATCH /api/documents/{document_id}
Content-Type: application/json

{
  "package_id": "PKG-2026-0001",  # or null to unassign
  "doc_type": "requirements",      # optional override
  "is_deliverable": false          # source doc, not output
}
```

### List Documents (New)

```http
GET /api/documents?scope=workspace           # package_id = null
GET /api/documents?package_id=PKG-2026-0001  # all docs in package
GET /api/documents?package_id=PKG-...&deliverable=false
```

---

## Verification

### Part 1: Unified Model

1. Upload `requirements.docx` → `DOC#` record created, no TTL
2. Check after 25 hours → document still exists
3. `PATCH` to assign to package → same S3 key, `package_id` updated
4. View package in UI → document appears in right panel
5. `PATCH` to unassign → document returns to workspace
6. Delete document → record and S3 objects removed

### Part 2: Conversational Injection

1. Upload `requirements.docx`
2. Chat: "What documents do I have?" → model calls `list_user_documents`
3. Chat: "Create an SOW from my requirements doc" → model:
   - Calls `list_user_documents`
   - Calls `get_document_content`
   - Calls `create_document` with source content
4. SOW appears in package with `is_deliverable=true`

---

## Decisions

| Decision | Choice |
|----------|--------|
| Unassign allowed? | Yes - `package_id` can be set back to `null` |
| Version history scope | Per document (not per package+doc_type) |
| Attachment selection UX | Conversational - no UI picker, model figures it out |
| Security hardening | Future work (file validation, macro scanning) |

---

## Future Work

Not included in this implementation:

- **Security hardening**: Magic byte validation, DOCX macro scanning, markdown sanitization
- **Quotas**: Per-user storage limits (not needed for POC)
- **Advanced versioning**: Optimistic locking, version comparison UI
- **Chunking**: For documents exceeding token limits
