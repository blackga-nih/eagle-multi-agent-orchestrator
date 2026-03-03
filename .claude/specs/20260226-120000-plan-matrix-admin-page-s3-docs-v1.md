# Plan: /admin/matrix Page + S3 Document Fetching

**Date**: 2026-02-26
**Effort**: ~4–5 hours
**Branch**: feat/matrix-admin-page

---

## Overview

Convert `contract-requirements-matrix.html` into a hidden Next.js admin page at `/admin/matrix`. No nav link — URL-only access. Documents (reference PDFs, KB docx, templates) are uploaded to S3 under a `reference/` prefix. The page fetches presigned URLs from a new backend endpoint. The matrix JS calls those endpoints with the Cognito Bearer token, replacing the current relative file links.

No Bedrock KB. No OpenSearch. Agent reads DynamoDB `eagle-document-metadata-dev` to discover documents; fetches full S3 objects via presigned URL. Section-level fetch is a later optimization.

---

## Architecture

```
Browser (/admin/matrix)
  └── Next.js page (auth guard via admin layout)
       └── calls GET /api/admin/matrix/documents   →  FastAPI
                                                        ├── s3.list_objects_v2(prefix="reference/")
                                                        ├── s3.generate_presigned_url() per object
                                                        └── returns [{key, name, url, size, type}]
       └── matrix JS opens presigned URL in new tab on doc link click
```

---

## S3 Document Layout

Upload once to `eagle-documents-695681773636-dev`:

```
reference/
  ap-exhibits/
    AP-Exhibit-01A.pdf
    AP-Exhibit-01B.pdf
    AP-Exhibit-01C.pdf
    AP-with-attachments-EIP-TO-Final.pdf
  kb/
    contract-type-selection.docx
    threshold-decision-tree.docx
  templates/
    sow-template.md
    igce-template.md
    market-research-template.md
    acquisition-plan-template.md
    justification-template.md
```

Upload command (run once):
```bash
AWS_PROFILE=eagle aws s3 cp "docs/architecture/reference-documents/AP - Exhibit 01.A.pdf" \
  s3://eagle-documents-695681773636-dev/reference/ap-exhibits/AP-Exhibit-01A.pdf

AWS_PROFILE=eagle aws s3 cp "docs/architecture/reference-documents/" \
  s3://eagle-documents-695681773636-dev/reference/ap-exhibits/ \
  --recursive --exclude "*" --include "*.pdf"

AWS_PROFILE=eagle aws s3 cp "data/kb/contract type selection.docx" \
  s3://eagle-documents-695681773636-dev/reference/kb/contract-type-selection.docx

AWS_PROFILE=eagle aws s3 cp "data/kb/Threshhold decision tree.docx" \
  s3://eagle-documents-695681773636-dev/reference/kb/threshold-decision-tree.docx

AWS_PROFILE=eagle aws s3 cp eagle-plugin/data/templates/ \
  s3://eagle-documents-695681773636-dev/reference/templates/ --recursive
```

---

## IAM

`eagle-app-role-dev` already has S3 access to `eagle-documents-695681773636-dev` (granted in EagleStorageStack). No CDK changes needed.

Verify:
```bash
AWS_PROFILE=eagle aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::695681773636:role/eagle-app-role-dev \
  --action-names s3:ListBucket s3:GetObject \
  --resource-arns arn:aws:s3:::eagle-documents-695681773636-dev \
    arn:aws:s3:::eagle-documents-695681773636-dev/reference/*
```

---

## Implementation Steps

### Step 1 — Upload reference docs to S3 (30 min)
Run the upload commands above. Verify with `aws s3 ls s3://eagle-documents-695681773636-dev/reference/ --recursive`.

### Step 2 — Backend: two new endpoints (1 hr)

In `server/app/main.py`:

```python
REFERENCE_PREFIX = "reference/"
PRESIGN_TTL = 900  # 15 minutes

@app.get("/api/admin/matrix/documents")
async def list_matrix_documents(user=Depends(get_current_user)):
    """List all reference documents with presigned URLs."""
    s3 = boto3.client("s3", region_name="us-east-1")
    bucket = os.environ["S3_BUCKET"]
    resp = s3.list_objects_v2(Bucket=bucket, Prefix=REFERENCE_PREFIX)
    docs = []
    for obj in resp.get("Contents", []):
        key = obj["Key"]
        name = key.split("/")[-1]
        if not name:
            continue
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=PRESIGN_TTL,
        )
        docs.append({
            "key": key,
            "name": name,
            "folder": key.split("/")[-2] if "/" in key else "",
            "size_bytes": obj["Size"],
            "url": url,
            "content_type": _mime_for(name),
        })
    return {"documents": docs}

def _mime_for(name: str) -> str:
    ext = name.rsplit(".", 1)[-1].lower()
    return {"pdf": "application/pdf", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "md": "text/markdown", "doc": "application/msword"}.get(ext, "application/octet-stream")
```

### Step 3 — Frontend: /admin/matrix page (2 hr)

`client/app/admin/matrix/page.tsx`:
- `'use client'` component
- Auth: `useAuth().getToken()` — same pattern as other admin pages
- On mount: calls `GET /api/admin/matrix/documents` with Bearer token, stores result in state
- Renders the matrix HTML inline (paste the full HTML body content) in a `<div>` with a `<style>` block
- Injects the documents list into the matrix JS as `window.EAGLE_DOCS` before the matrix initializes
- Matrix JS checks `window.EAGLE_DOCS` and uses presigned URLs instead of relative file paths

```tsx
// client/app/admin/matrix/page.tsx
'use client'
import { useEffect, useRef } from 'react'
import { useAuth } from '@/contexts/auth-context'

export default function MatrixPage() {
  const { getToken } = useAuth()
  const initialized = useRef(false)

  useEffect(() => {
    if (initialized.current) return
    initialized.current = true
    getToken().then(token => {
      fetch('/api/admin/matrix/documents', {
        headers: { Authorization: `Bearer ${token}` }
      })
      .then(r => r.json())
      .then(data => {
        (window as any).EAGLE_DOCS = data.documents
        // matrix JS reads window.EAGLE_DOCS on init
      })
    })
  }, [])

  return (
    <>
      <style>{/* inline the CSS from contract-requirements-matrix.html */}</style>
      <div id="matrix-root">
        {/* inline the HTML body from contract-requirements-matrix.html */}
      </div>
      <script dangerouslySetInnerHTML={{ __html: `/* inline the JS */` }} />
    </>
  )
}
```

### Step 4 — Matrix JS: consume EAGLE_DOCS (30 min)

In the matrix JS (now inline in the page), replace the static `DOC_TEMPLATES` reference link generation:

```js
// At the top of the script, load S3 docs
const S3_DOCS = window.EAGLE_DOCS || [];
const S3_DOC_MAP = {};
S3_DOCS.forEach(d => { S3_DOC_MAP[d.name] = d; });

// In renderManifest(), when building a doc row that has an S3 match:
function getDocLink(docName) {
  const match = S3_DOCS.find(d =>
    d.name.toLowerCase().includes(docName.toLowerCase().replace(/\s+/g, '-'))
  );
  return match ? match.url : null;
}
```

### Step 5 — Next.js API proxy (30 min)

`client/app/api/admin/matrix/documents/route.ts` — proxies to FastAPI with auth header (same pattern as other proxy routes).

---

## What does NOT change

- No CDK changes
- No DynamoDB schema changes
- No navigation files touched
- No existing routes modified
- The original `contract-requirements-matrix.html` stays at root (local dev reference)

---

## Verification

```bash
# 1. S3 upload
AWS_PROFILE=eagle aws s3 ls s3://eagle-documents-695681773636-dev/reference/ --recursive

# 2. Backend endpoint (local)
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/admin/matrix/documents

# 3. Page accessible
open http://localhost:3000/admin/matrix
# Should render matrix, docs panel shows S3 links
# Clicking a doc link opens presigned URL in new tab

# 4. No nav link
# Confirm matrix does NOT appear in sidebar/header components
```

---

## Cost

| Resource | Cost |
|---|---|
| S3 storage (~15 MB of reference docs) | <$0.01/month |
| S3 GET requests (presigned URL generation) | <$0.01/month |
| No new AWS resources created | $0 |

---

## Rollback

If the page causes issues: delete `client/app/admin/matrix/` and `client/app/api/admin/matrix/`. The original HTML at root is unaffected. S3 uploads can stay — they're inert.
