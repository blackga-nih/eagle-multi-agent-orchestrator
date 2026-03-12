# Document Upload and In-App Editing Feature Plan

Date: 2026-03-09
Owner: EAGLE engineering
Status: Draft - Ready for review
Branch target: `feature/document-upload-edit`

---

## 1. Executive Summary

Users want to upload existing documents (DOCX, PDF, TXT, MD) and edit them within EAGLE's document viewer. The infrastructure is partially in place:

| Component | Status | Gap |
|-----------|--------|-----|
| Upload UI (`DocumentUpload`) | Exists in `/chat-advanced` | Not connected to viewer |
| Upload endpoint (`POST /api/documents/upload`) | Works (S3 storage) | No conversion to editable format |
| Document viewer (`/documents/[id]`) | Has edit mode | Only loads generated docs, not uploads |
| Save edits | Partial (sessionStorage) | No S3 persistence for edits |

This plan bridges these gaps to enable a full upload-edit-download workflow.

---

## 2. Goals and Non-Goals

### Goals

1. Upload DOCX, PDF, TXT, or MD files via the existing `DocumentUpload` component.
2. Convert uploaded files to markdown for in-app editing.
3. Open uploaded documents in the existing document viewer with full edit capability.
4. Save edits back to S3 (new version, not overwrite).
5. Download edited documents as DOCX or PDF.

### Non-Goals

1. Real-time collaborative editing (out of scope).
2. Rich WYSIWYG editor (current markdown editor is sufficient).
3. OCR for scanned PDFs (best-effort text extraction only).
4. Full format fidelity preservation (markdown is lossy by design).

---

## 3. Current State Analysis

### 3.1 Upload Flow (Exists)

```
Frontend                      Backend                         S3
   |                             |                             |
   |  POST /api/documents/upload |                             |
   |  (multipart file)           |                             |
   |---------------------------->|                             |
   |                             |  put_object(...)            |
   |                             |---------------------------->|
   |                             |                             |
   |  { key, filename, size }    |                             |
   |<----------------------------|                             |
```

**Storage path**: `eagle/{tenant_id}/{user_id}/uploads/{safe_filename}`

**Accepted types**: PDF, DOCX, DOC, TXT, MD (see `main.py:663`)

**Current limitation**: File is stored as-is. No conversion. Not linked to viewer.

### 3.2 Document Viewer (Exists)

Location: `client/app/documents/[id]/page.tsx`

Features:
- Preview mode (rendered markdown)
- Edit mode (raw markdown textarea)
- AI chat assistant for editing help
- Download as DOCX/PDF

**Current limitation**: Only loads documents from:
1. `sessionStorage` (from chat navigation)
2. `localStorage` (from `document-store.ts`)
3. API fallback (`/api/documents/[id]`)
4. Local templates (fallback)

Uploaded files are not discoverable by the viewer.

### 3.3 DocumentUpload Component (Exists)

Location: `client/components/documents/document-upload.tsx`

Features:
- Drag-and-drop file selection
- Multi-file upload
- Progress indicators
- File type validation

**Current limitation**: Uploads to S3 but doesn't navigate to viewer or trigger conversion.

---

## 4. Target Architecture

### 4.1 End-to-End Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Frontend: DocumentUpload component                                          │
│   1. User drops file (DOCX/PDF/TXT/MD)                                      │
│   2. POST /api/documents/upload                                             │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Backend: /api/documents/upload (enhanced)                                   │
│   1. Store original file to S3 (existing)                                   │
│   2. Convert to markdown (NEW)                                              │
│   3. Store markdown version to S3 (NEW)                                     │
│   4. Create DOCUMENT# record in DynamoDB (NEW)                              │
│   5. Return { document_id, s3_key, markdown_key, title }                    │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Frontend: Navigation to viewer                                              │
│   1. On upload success, navigate to /documents/{document_id}?session=...    │
│   2. Or show "Open in Editor" button                                        │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Document Viewer: /documents/[id]                                            │
│   1. Load markdown content from API                                         │
│   2. User edits in textarea                                                 │
│   3. Save → POST /api/documents/{id}/save (NEW)                             │
│   4. Download → existing DOCX/PDF export                                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Storage Model

**S3 Keys**:
```
eagle/{tenant_id}/{user_id}/uploads/{filename}           # Original file
eagle/{tenant_id}/{user_id}/documents/{doc_id}/v{N}.md   # Markdown versions
```

**DynamoDB** (existing `DOCUMENT#` entity):
```
PK: DOCUMENT#{tenant_id}
SK: DOCUMENT#{doc_id}
Attributes:
  - document_id
  - title
  - document_type: "uploaded" | "sow" | "igce" | ...
  - source_type: "upload" | "generated"
  - original_s3_key
  - markdown_s3_key
  - version
  - status: "draft" | "final"
  - content_type (original MIME)
  - word_count
  - created_at, updated_at
  - created_by_user_id
```

---

## 5. Implementation Plan

### Phase 1: Backend Document Conversion Service

**Goal**: Convert uploaded files to markdown.

**New file**: `server/app/document_conversion.py`

**Dependencies**:
```python
# requirements.txt additions
python-docx>=1.1.0      # DOCX parsing
pypdf>=4.0.0            # PDF text extraction (replaces PyPDF2)
markdownify>=0.11.0     # HTML → markdown
```

**Functions**:
```python
def convert_to_markdown(file_bytes: bytes, content_type: str, filename: str) -> str:
    """
    Convert uploaded file to markdown.

    Supported formats:
    - text/plain, text/markdown → passthrough
    - application/vnd.openxmlformats-officedocument.wordprocessingml.document → docx_to_markdown()
    - application/pdf → pdf_to_markdown()

    Returns markdown string.
    """

def docx_to_markdown(file_bytes: bytes) -> str:
    """Extract text and structure from DOCX, convert to markdown."""

def pdf_to_markdown(file_bytes: bytes) -> str:
    """Extract text from PDF pages, convert to markdown (best-effort)."""
```

**Edge cases**:
- Scanned PDFs: Return placeholder `[This PDF contains scanned images. Text extraction not available.]`
- Complex DOCX tables: Convert to markdown tables (best-effort)
- Images in DOCX: Skip with `[Image: {alt_text}]` placeholder

**Acceptance criteria**:
- DOCX with headings, paragraphs, lists → valid markdown
- PDF with text → extracted markdown
- TXT/MD → passthrough
- Unsupported format → raises `UnsupportedFormatError`

---

### Phase 2: Enhanced Upload Endpoint

**Goal**: Upload returns editable document metadata.

**File**: `server/app/main.py` (modify existing endpoint)

**Changes to `POST /api/documents/upload`**:

```python
@app.post("/api/documents/upload")
async def api_upload_document(
    file: UploadFile = File(...),
    user: UserContext = Depends(get_user_from_header),
):
    # 1. Existing: validate and store original file
    original_key = f"eagle/{tenant_id}/{user_id}/uploads/{safe_name}"
    s3.put_object(Bucket=bucket, Key=original_key, Body=body, ContentType=content_type)

    # 2. NEW: convert to markdown
    markdown_content = convert_to_markdown(body, content_type, file.filename)

    # 3. NEW: generate document ID and store markdown
    doc_id = f"upload-{uuid4().hex[:12]}"
    markdown_key = f"eagle/{tenant_id}/{user_id}/documents/{doc_id}/v1.md"
    s3.put_object(Bucket=bucket, Key=markdown_key, Body=markdown_content.encode(), ContentType="text/markdown")

    # 4. NEW: create DynamoDB record
    document_store.create_document(
        tenant_id=tenant_id,
        document_id=doc_id,
        title=Path(file.filename).stem,
        document_type="uploaded",
        source_type="upload",
        original_s3_key=original_key,
        markdown_s3_key=markdown_key,
        version=1,
        status="draft",
        content_type=content_type,
        word_count=len(markdown_content.split()),
        created_by_user_id=user_id,
    )

    # 5. Return enhanced response
    return {
        "document_id": doc_id,
        "key": original_key,
        "markdown_key": markdown_key,
        "filename": safe_name,
        "title": Path(file.filename).stem,
        "size_bytes": len(body),
        "content_type": content_type,
        "word_count": len(markdown_content.split()),
        "editable": True,  # Signal to frontend
    }
```

**Acceptance criteria**:
- Upload returns `document_id` and `editable: true`
- Markdown version stored in S3
- `DOCUMENT#` record created in DynamoDB

---

### Phase 3: Document Save Endpoint

**Goal**: Save edited markdown back to S3.

**New endpoint**: `PUT /api/documents/{document_id}/content`

```python
@app.put("/api/documents/{document_id}/content")
async def api_save_document_content(
    document_id: str,
    body: DocumentContentUpdate,  # { content: str }
    user: UserContext = Depends(get_user_from_header),
):
    # 1. Validate ownership
    doc = document_store.get_document(user.tenant_id, document_id)
    if not doc or doc.created_by_user_id != user.user_id:
        raise HTTPException(403, "Not authorized")

    # 2. Increment version
    new_version = doc.version + 1
    markdown_key = f"eagle/{user.tenant_id}/{user.user_id}/documents/{document_id}/v{new_version}.md"

    # 3. Store new version
    s3.put_object(Bucket=bucket, Key=markdown_key, Body=body.content.encode(), ContentType="text/markdown")

    # 4. Update DynamoDB
    document_store.update_document(
        tenant_id=user.tenant_id,
        document_id=document_id,
        markdown_s3_key=markdown_key,
        version=new_version,
        word_count=len(body.content.split()),
        updated_at=datetime.utcnow().isoformat(),
    )

    return {
        "document_id": document_id,
        "version": new_version,
        "markdown_key": markdown_key,
        "saved_at": datetime.utcnow().isoformat(),
    }
```

**Acceptance criteria**:
- Edits create new version (never overwrite)
- Version number increments
- DynamoDB record updated

---

### Phase 4: Frontend Upload → Viewer Connection

**Goal**: Navigate to viewer after upload.

**File**: `client/components/documents/document-upload.tsx`

**Changes**:

```typescript
interface DocumentUploadProps {
    onUpload: (file: File) => Promise<{ success: boolean; error?: string; document_id?: string }>;
    onDocumentReady?: (documentId: string) => void;  // NEW
    // ...existing props
}

// In handleFiles():
if (validation.valid) {
    const result = await onUpload(file);
    if (result.success && result.document_id) {
        onDocumentReady?.(result.document_id);  // Notify parent
    }
    // ...existing status update
}
```

**File**: `client/components/chat/chat-interface.tsx`

**Changes**:

```typescript
const handleDocumentUpload = async (file: File): Promise<{ success: boolean; error?: string; document_id?: string }> => {
    // ...existing upload logic
    if (resp.ok) {
        const result = await resp.json();
        return {
            success: true,
            document_id: result.document_id  // Pass through
        };
    }
};

const handleDocumentReady = (documentId: string) => {
    // Navigate to viewer
    router.push(`/documents/${encodeURIComponent(documentId)}?session=${currentSessionId}`);
};

// In render:
<DocumentUpload
    onUpload={handleDocumentUpload}
    onDocumentReady={handleDocumentReady}  // NEW
    onRemove={handleDocumentRemove}
    maxSizeMB={10}
/>
```

**Acceptance criteria**:
- After successful upload, user is navigated to document viewer
- Document loads with markdown content ready for editing

---

### Phase 5: Viewer Save Integration

**Goal**: Add "Save" button to persist edits.

**File**: `client/app/documents/[id]/page.tsx`

**Changes**:

```typescript
const [isSaving, setIsSaving] = useState(false);
const [lastSaved, setLastSaved] = useState<Date | null>(null);

const handleSave = async () => {
    setIsSaving(true);
    try {
        const token = await getToken();
        const res = await fetch(`/api/documents/${encodeURIComponent(id)}/content`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                ...(token ? { Authorization: `Bearer ${token}` } : {}),
            },
            body: JSON.stringify({ content: editContent }),
        });

        if (!res.ok) {
            const detail = await extractResponseError(res);
            throw new Error(detail);
        }

        const result = await res.json();
        setDocumentContent(editContent);
        setLastSaved(new Date());
        // Update local state with new version
    } catch (err) {
        setExportError(err instanceof Error ? err.message : 'Save failed');
    } finally {
        setIsSaving(false);
    }
};

// In header buttons:
{isEditing && (
    <button
        onClick={handleSave}
        disabled={isSaving || editContent === documentContent}
        className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-xl text-sm font-medium hover:bg-green-700 disabled:opacity-50"
    >
        {isSaving ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
        Save
    </button>
)}
```

**Add Next.js API route**: `client/app/api/documents/[id]/content/route.ts`

```typescript
export async function PUT(request: NextRequest, { params }: { params: { id: string } }) {
    const authHeader = request.headers.get('authorization');
    const body = await request.json();

    const response = await fetch(`${FASTAPI_URL}/api/documents/${params.id}/content`, {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json',
            ...(authHeader ? { Authorization: authHeader } : {}),
        },
        body: JSON.stringify(body),
    });

    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
}
```

**Acceptance criteria**:
- Save button appears in edit mode
- Button disabled when no changes
- Successful save shows timestamp
- Errors displayed to user

---

### Phase 6: Uploaded Documents List

**Goal**: Show uploaded documents in a discoverable list.

**Option A**: Add to existing Documents page
**Option B**: Add tab in `/chat-advanced` sidebar

**Recommended**: Option A - Extend `/documents` page

**File**: `client/app/documents/page.tsx` (create or extend)

```typescript
export default function DocumentsPage() {
    const [documents, setDocuments] = useState<UploadedDocument[]>([]);
    const [filter, setFilter] = useState<'all' | 'uploaded' | 'generated'>('all');

    useEffect(() => {
        async function loadDocuments() {
            const token = await getToken();
            const res = await fetch('/api/documents/list', {
                headers: token ? { Authorization: `Bearer ${token}` } : {},
            });
            if (res.ok) {
                const data = await res.json();
                setDocuments(data.documents);
            }
        }
        loadDocuments();
    }, []);

    // Render document cards with "Open" button → /documents/[id]
}
```

**Backend endpoint**: `GET /api/documents/list`

```python
@app.get("/api/documents/list")
async def api_list_documents(
    source_type: Optional[str] = None,  # "upload" | "generated"
    user: UserContext = Depends(get_user_from_header),
):
    docs = document_store.list_user_documents(
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        source_type=source_type,
    )
    return {"documents": docs}
```

**Acceptance criteria**:
- User can see list of all their documents
- Filter by uploaded vs generated
- Click to open in viewer

---

## 6. Testing Plan

### 6.1 Unit Tests

**File**: `server/tests/test_document_conversion.py`

```python
def test_docx_to_markdown_headings():
    """DOCX with H1, H2, H3 → proper markdown headings"""

def test_docx_to_markdown_lists():
    """DOCX with bullet/numbered lists → markdown lists"""

def test_pdf_to_markdown_multipage():
    """Multi-page PDF → concatenated markdown"""

def test_pdf_to_markdown_scanned():
    """Scanned PDF → placeholder message"""

def test_txt_passthrough():
    """Plain text file → unchanged"""

def test_md_passthrough():
    """Markdown file → unchanged"""

def test_unsupported_format():
    """XLSX, PPTX → raises UnsupportedFormatError"""
```

### 6.2 Integration Tests

**File**: `server/tests/test_document_upload_edit.py`

```python
def test_upload_creates_markdown_version():
    """Upload DOCX → S3 has both original and .md versions"""

def test_upload_creates_dynamodb_record():
    """Upload → DOCUMENT# record exists with correct fields"""

def test_save_increments_version():
    """Edit and save → version bumps, new S3 key created"""

def test_list_documents_filters():
    """List with source_type filter returns correct subset"""
```

### 6.3 E2E Tests (Playwright)

**File**: `client/tests/document-upload-edit.spec.ts`

```typescript
test('upload DOCX and edit', async ({ page }) => {
    // 1. Navigate to /chat-advanced
    // 2. Upload test.docx via dropzone
    // 3. Wait for navigation to /documents/[id]
    // 4. Verify markdown content displayed
    // 5. Switch to edit mode
    // 6. Make changes
    // 7. Click Save
    // 8. Verify "Saved" indicator
    // 9. Download as DOCX
    // 10. Verify downloaded file is non-empty
});

test('upload PDF and view', async ({ page }) => {
    // Similar flow for PDF
});
```

### 6.4 Manual QA Matrix

| Scenario | Browser | Expected |
|----------|---------|----------|
| Upload 5MB DOCX | Chrome | Success, opens in viewer |
| Upload 30MB DOCX | Chrome | Error: exceeds 25MB limit |
| Upload scanned PDF | Chrome | Placeholder message shown |
| Upload TXT file | Firefox | Passthrough, editable |
| Edit and save | Safari | Version increments |
| Save without changes | Chrome | Button disabled |
| Download edited as PDF | Chrome | Valid PDF opens |

---

## 7. Task Breakdown

| # | Task | Depends On | Estimate |
|---|------|------------|----------|
| 1 | Create `document_conversion.py` with DOCX/PDF/TXT converters | - | 1.5d |
| 2 | Add unit tests for conversion | 1 | 0.5d |
| 3 | Enhance `/api/documents/upload` with conversion + DynamoDB | 1 | 1d |
| 4 | Add `PUT /api/documents/{id}/content` endpoint | 3 | 0.5d |
| 5 | Add Next.js proxy route for save | 4 | 0.25d |
| 6 | Update `DocumentUpload` to emit `document_id` | 3 | 0.25d |
| 7 | Add navigation to viewer after upload | 6 | 0.25d |
| 8 | Add Save button to document viewer | 5 | 0.5d |
| 9 | Add `GET /api/documents/list` endpoint | 3 | 0.5d |
| 10 | Create/extend `/documents` page with list | 9 | 1d |
| 11 | Integration tests | 4, 9 | 0.5d |
| 12 | E2E tests | 8, 10 | 0.5d |

**Critical path**: 1 → 3 → 4 → 5 → 8 (3.75 days)
**Total with parallelization**: ~5 days

---

## 8. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Complex DOCX loses formatting | High | Medium | Document limitations clearly; markdown is lossy |
| Scanned PDFs have no text | High | Low | Show clear placeholder message |
| Large files slow conversion | Medium | Medium | Add timeout; show progress indicator |
| S3 version explosion | Low | Medium | Add cleanup job for old versions (>10) |
| User edits conflict | Low | High | Out of scope; single-user editing only |

---

## 9. Definition of Done

1. User can upload DOCX/PDF/TXT/MD via `/chat-advanced`
2. Upload triggers conversion to markdown
3. User is navigated to document viewer after upload
4. User can edit markdown in viewer
5. Save button persists edits to S3 (new version)
6. Download as DOCX/PDF works for edited content
7. User can see list of all their documents
8. All tests pass
9. Manual QA matrix completed

---

## 10. Future Enhancements (Out of Scope)

1. **OCR for scanned PDFs** - Integrate Textract or similar
2. **Image preservation** - Store and render inline images
3. **Rich editor** - Replace textarea with WYSIWYG markdown editor
4. **Collaborative editing** - Real-time sync between users
5. **Version diff view** - Show changes between versions
6. **Auto-save** - Periodic background saves

---

## 11. Appendix: File Checklist

**Backend - Create:**
- [ ] `server/app/document_conversion.py`
- [ ] `server/tests/test_document_conversion.py`
- [ ] `server/tests/test_document_upload_edit.py`

**Backend - Modify:**
- [ ] `server/app/main.py` (enhance upload, add save endpoint, add list endpoint)
- [ ] `server/app/document_store.py` (add list_user_documents if needed)
- [ ] `server/requirements.txt` (add python-docx, pypdf, markdownify)

**Frontend - Create:**
- [ ] `client/app/api/documents/[id]/content/route.ts`
- [ ] `client/app/documents/page.tsx` (or extend existing)
- [ ] `client/tests/document-upload-edit.spec.ts`

**Frontend - Modify:**
- [ ] `client/components/documents/document-upload.tsx` (add onDocumentReady)
- [ ] `client/components/chat/chat-interface.tsx` (add navigation)
- [ ] `client/app/documents/[id]/page.tsx` (add Save button)
