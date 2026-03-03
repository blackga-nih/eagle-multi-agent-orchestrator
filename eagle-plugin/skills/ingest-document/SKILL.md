---
name: ingest-document
description: Handle document ingestion for two distinct flows — user upload to session workspace and admin S3 knowledge-base drop with HITL matrix review. Extracts text, classifies document type, and surfaces key facts relevant to the current acquisition.
triggers:
  - "upload", "attach", "document", "file", "pdf", "word"
  - "add document", "upload file", "attach file"
  - "knowledge base", "kb update", "update matrix"
  - "ingest", "import document"
---

# Ingest Document Skill

Handles two distinct ingestion flows: user uploads for session context, and admin knowledge-base drops that may update the acquisition decision matrix.

---

## Trigger A — User Uploads a Document

### Flow

1. Frontend calls `POST /api/documents/upload` with the file (multipart form).
2. Backend validates MIME type and size (≤25 MB), then saves to:
   ```
   s3://eagle/{tenant_id}/{user_id}/uploads/{sanitized_filename}
   ```
3. The existing Lambda metadata extractor fires automatically on `s3:ObjectCreated`.
4. Lambda extracts full text and writes a `DOCMETA#` record to DynamoDB.
5. This skill receives the extracted text and metadata, then responds with:
   - **Document type** (FAR clause, SOW, J&A, market research, invoice, etc.)
   - **Key facts** (dollar values, dates, parties, regulatory references)
   - **Relevance** to the current acquisition in session context
6. The document's content is available for follow-up queries within the session.

### User Response Format

```markdown
## Document Ingested: {filename}

**Type:** {document_type}
**Key Facts:**
- {fact_1}
- {fact_2}
- {fact_3}

**Relevance to current acquisition:**
{1-2 sentences connecting doc content to the acquisition in progress}

Would you like me to use this document to help draft {suggested next document}?
```

### Error Handling

- Unsupported format → Tell user accepted formats: PDF, Word (.docx), Markdown, plain text.
- File too large (>25 MB) → Suggest splitting the document.
- Extraction failed → Acknowledge receipt, note manual review needed.

---

## Trigger B — Admin Drops Doc into Knowledge Base

### Flow

1. Admin uploads file to `eagle-knowledge-base/pending/{filename}` via:
   - Admin UI (`/admin/kb-reviews`)
   - Direct S3 upload
2. Lambda KB handler (branch in metadata extractor) detects `eagle-knowledge-base/pending/` prefix:
   - Extracts full text
   - Loads current `eagle-plugin/data/matrix.json`
   - Calls Claude: "Analyze this document vs the matrix. Return a structured diff of proposed threshold, doc_rule, or contract_type changes."
   - Writes `KB_REVIEW#{review_id}` to DynamoDB with `status: "pending"` and the full diff payload.
3. Admin dashboard (`/admin/kb-reviews`) shows a pending review card.
4. **Approve** → backend applies diff to `matrix.json`, regenerates HTML data arrays, moves doc to `eagle-knowledge-base/approved/`.
5. **Reject** → marks record `rejected`, moves doc to `eagle-knowledge-base/rejected/`.

### DynamoDB Record Schema

```json
{
  "PK": "KB_REVIEW#2026-02-25T14:30:00Z-abc123",
  "SK": "META",
  "review_id": "2026-02-25T14:30:00Z-abc123",
  "filename": "FAC-2025-07-amendment.pdf",
  "s3_key": "eagle-knowledge-base/pending/FAC-2025-07-amendment.pdf",
  "status": "pending",
  "proposed_diff": {
    "thresholds": [...],
    "doc_rules": {...},
    "approval_chains": {...}
  },
  "analysis_summary": "This FAR amendment raises the MPT to $20K effective Q3 2026...",
  "created_at": "2026-02-25T14:30:00Z",
  "reviewed_by": null,
  "reviewed_at": null
}
```

### Diff Format (proposed_diff)

The diff uses JSON Patch semantics (RFC 6902):
```json
[
  { "op": "replace", "path": "/thresholds/0/value", "value": 20000 },
  { "op": "add",     "path": "/doc_rules/special_factors/isNewFactor", "value": ["New doc"] }
]
```

---

## Integration Notes

- **Session context**: Uploaded documents are summarized and attached to session context so subsequent OA Intake and Document Generator queries can reference them.
- **Matrix authority**: After admin approval, `matrix.json` is the authoritative source. The OA Intake skill must reload it on the next query (no caching beyond the session turn).
- **No PII in KB**: Admin KB uploads should contain regulatory documents only (FAR, HHSAR, class deviations). User-uploaded documents stay in the user's private S3 prefix and are never promoted to the KB.
