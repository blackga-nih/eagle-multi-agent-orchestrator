# Native Document Editor Progress

Status: archived and no longer active.

The previous ONLYOFFICE/native-editor direction has been removed from the application. Do not configure `NATIVE_EDITOR_*` environment variables or deploy a document-server container for EAGLE.

Current direction:

- DOCX files remain native `.docx` artifacts in S3.
- The web app shows a DOCX preview instead of embedding an external office editor.
- AI applies targeted DOCX edits server-side with `python-docx`.
- No external document editing service is required.

Relevant implementation:

- [server/app/document_ai_edit_service.py](/Users/hoquemi/Desktop/sm_eagle/server/app/document_ai_edit_service.py)
- [server/app/agentic_service.py](/Users/hoquemi/Desktop/sm_eagle/server/app/agentic_service.py)
- [server/app/strands_agentic_service.py](/Users/hoquemi/Desktop/sm_eagle/server/app/strands_agentic_service.py)
- [server/app/main.py](/Users/hoquemi/Desktop/sm_eagle/server/app/main.py)
- [client/app/documents/[id]/page.tsx](/Users/hoquemi/Desktop/sm_eagle/client/app/documents/[id]/page.tsx)
