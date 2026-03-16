# Native Document Editor Implementation Plan

Status: archived and superseded.

This document previously described an embedded native-editor / ONLYOFFICE approach. That path is no longer part of the product direction and should not be used for deployment or configuration.

Removed assumptions:

- no embedded ONLYOFFICE editor
- no `NATIVE_EDITOR_PROVIDER`
- no `NATIVE_EDITOR_SERVER_URL`
- no `NATIVE_EDITOR_CALLBACK_SECRET`
- no `/api/editor/...` backend flow

Current implementation plan in effect:

1. Keep generated DOCX files as the source of truth in S3.
2. Render a server-generated DOCX preview in the document page.
3. Let AI apply targeted edits directly to the `.docx` with `python-docx`.
4. Save the edited document back through the existing versioned document service.
5. Avoid markdown round-trips for DOCX edits.

Primary code paths:

- [server/app/document_ai_edit_service.py](/Users/hoquemi/Desktop/sm_eagle/server/app/document_ai_edit_service.py)
- [server/app/document_service.py](/Users/hoquemi/Desktop/sm_eagle/server/app/document_service.py)
- [server/app/main.py](/Users/hoquemi/Desktop/sm_eagle/server/app/main.py)
- [client/app/documents/[id]/page.tsx](/Users/hoquemi/Desktop/sm_eagle/client/app/documents/[id]/page.tsx)
