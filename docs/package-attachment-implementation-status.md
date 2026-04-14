# Package Attachments Implementation Status

Last updated: 2026-04-14

## Goal

Support uploaded source material inside acquisition packages so the system can:

- attach documents, screenshots, and reference files directly to a package
- include selected attachments in the package ZIP export
- use attached files as source context for generation
- keep official package documents separate from uploaded source material

## Current Model

There are now two asset types in the package workflow:

1. `package documents`
Official canonical versioned docs like `sow`, `igce`, `market_research`, `acquisition_plan`.

2. `package attachments`
Uploaded source material like technical requirements, prior SOWs, prior IGCEs, screenshots, quotes, and other evidence.

## What Has Been Implemented

### Phase 1: Package Attachment Foundation

Status: implemented

Implemented backend storage:

- `server/app/package_attachment_store.py`

What it does:

- stores package-scoped attachments in DynamoDB
- supports create/get/list/update/delete
- stores metadata like `category`, `usage`, `attachment_type`, `doc_type`, `include_in_zip`, `extracted_text`
- attachment metadata now also supports `linked_doc_type` for checklist linkage

Implemented package attachment API endpoints:

- `POST /api/packages/{package_id}/attachments`
- `GET /api/packages/{package_id}/attachments`
- `PATCH /api/packages/{package_id}/attachments/{attachment_id}`
- `DELETE /api/packages/{package_id}/attachments/{attachment_id}`
- `GET /api/packages/{package_id}/attachments/{attachment_id}/download-url`

Primary file:

- `server/app/routers/packages.py`

Implemented upload support for images:

- generic upload now accepts `image/png` and `image/jpeg`
- package attachment upload accepts documents plus PNG/JPEG

Primary file:

- `server/app/routers/documents.py`

Implemented ZIP inclusion:

- package ZIP export now includes attachments under `09_Attachments/{category}/`
- export names are package-aware

Primary files:

- `server/app/routers/packages.py`
- `server/app/document_export.py`

Implemented frontend integration:

- active package uploads now go directly to package attachments
- chat upload no longer depends on the broken legacy `assign-to-package` path for active package uploads
- client API/proxy routes added for attachment operations

Primary files:

- `client/lib/document-api.ts`
- `client/app/api/packages/[packageId]/attachments/...`
- `client/components/chat-simple/chat-upload-button.tsx`
- `client/components/chat-simple/simple-chat-interface.tsx`

Implemented metadata fallback fix:

- upload modal now respects either `package_context.package_id` or `package_id`

Primary file:

- `client/components/chat-simple/package-selector-modal.tsx`

### Phase 2: Attachment Context for Generation

Status: partially implemented, core retrieval path done

Implemented attachment visibility in session preload:

- active package preload now includes attachments
- prompt context now includes focused `Source Attachments`

Primary file:

- `server/app/session_preloader.py`

Implemented agent tool support:

- `list_user_documents` now includes package attachments
- `get_document_content` can resolve either user uploads or package attachments

Primary file:

- `server/app/tools/user_document_tools.py`

Implemented relevance ranking for generation:

- added attachment ranking and selection helper
- ranks attachments by target doc type, category, usage, and available extracted text
- produces excerpts for prompt use

Primary file:

- `server/app/package_attachment_context.py`

Implemented generation-path enrichment:

- preloaded prompt context is doc-type-aware
- `create_document` tool path enriches generation data with relevant package attachments
- direct-request fallback path also enriches from relevant package attachments
- document generation executor also enriches data from attachments when `package_id` is present

Primary files:

- `server/app/strands_agentic_service.py`
- `server/app/tools/document_generation.py`

## What Has Not Been Implemented Yet

### Remaining Phase 2 Work

Status: not complete

- stronger end-to-end verification that generated SOW/IGCE content materially reflects attached source docs
- attachment-to-output prompting refinements if ranking alone is not strong enough
- OCR or image-text extraction for screenshots/images with no extracted text

Note:

- OCR can be deferred if screenshots are not currently required to drive generation
- the more urgent integration problem is solved better by attachment storage, retrieval, and package-aware generation than by OCR

### Phase 3: Document Intent and Promotion Flows

Status: in progress, backend promotion and attachment intent slice implemented

Phase 3 is about lifecycle and intent, not basic context retrieval.

Needed behavior:

- prior SOW or prior IGCE uploads should not silently replace the package’s official document
- uploaded files should support `reference`, `checklist_support`, and `official_document` flows
- users should be able to promote an uploaded artifact into the canonical package document flow
- users should be able to compare or revise using prior artifacts

Implemented:

- backend promotion endpoint:
  - `POST /api/packages/{packageId}/attachments/{attachmentId}/promote`
- promotion reuses canonical package document creation via `create_package_document_version(...)`
- promoted attachments can be marked `official_document`
- promotion carries attachment-derived markdown/extracted text when available
- client proxy and API method added for promotion
- attachment metadata now supports `linked_doc_type`
- checklist-linked attachments can be marked `checklist_support`
- attachment ranking now boosts checklist-linked files for the requested output doc type
- active package UI now includes an attachment management panel with 3 intents:
  - supporting document
  - supports checklist item
  - use as official checklist document

Primary files:

- `server/app/routers/packages.py`
- `server/app/package_attachment_store.py`
- `server/app/package_attachment_context.py`
- `server/app/document_service.py`
- `client/app/api/packages/[packageId]/attachments/[attachmentId]/promote/route.ts`
- `client/lib/document-api.ts`
- `client/components/chat-simple/package-attachments-panel.tsx`
- `client/components/chat-simple/activity-panel.tsx`

Still not implemented:

- compare/revise workflow for prior package artifacts
- stronger package-state UX around checklist-linked attachments after promotion
- additional guardrails and confirmation UX for replacing an official artifact

## Recommended Next Steps

### If OCR Is Deferred

Recommended next sequence:

1. finish Phase 2 verification
2. continue Phase 3 intent handling on top of the new promotion endpoint
3. return to OCR later only if screenshot-driven generation becomes important

Why:

- package integration is the current bottleneck
- promotion/reference flows are higher-value than image OCR if the main need is handling uploaded requirements docs and prior SOW/IGCE artifacts

### Concrete Next Slice

Recommended next implementation slice:

1. add compare/revise workflow for prior SOW/IGCE attachments
2. add clearer post-promotion UX in the checklist itself
3. add guardrails if a package already has an official document for the chosen checklist item
4. return to OCR only if screenshots must drive generation rather than just package support

## Verification So Far

Focused backend tests currently cover:

- package attachment CRUD
- ZIP inclusion for attachments
- session preload attachment visibility
- attachment retrieval tools
- attachment ranking and enrichment helpers

Open verification gap:

- end-to-end generation proof that a package attachment materially changes the generated document content
