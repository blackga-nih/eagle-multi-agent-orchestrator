# Frontend Plan: Document Viewer with Chat

## Overview
- **Area**: Chat + Documents
- **Primary Chat**: Simple chat (`/`) — the default interface shown in screenshot
- **Viewer Route Strategy**: enhance existing `/documents/[id]` route (no `/view` route)
- **Components Affected**: `simple-message-list.tsx`, `simple-chat-interface.tsx`, `use-agent-stream.ts`, shared chat types
- **New Components**: `document-card.tsx`, enhanced `documents/[id]/page.tsx`

## User Flow

```
1. User asks "Generate a SOW for IT services at NCI" in main chat (/)
2. Backend generates document via create_document tool → saves to S3
3. Chat displays assistant response + embedded DOCUMENT CARD
   (card shows: document type badge, title, "Open Document" button)
4. User clicks "Open Document" → navigates to /documents/{documentId}?session={sessionId}
5. Document viewer opens in SPLIT VIEW (65% document / 35% chat)
   - Left: rendered document (default) with toggle to markdown editor
   - Right: chat panel continuing SAME SESSION (LLM has full context)
6. User chats to refine: "Add a security requirements section"
7. LLM regenerates document → left panel updates automatically
8. User can also toggle to editor mode and make direct edits
9. User clicks Download → chooses DOCX or PDF format
```

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Link style | Document card in chat | Visual, clear call-to-action |
| Layout | 65/35 split view | See document + chat simultaneously |
| Session | Same session (continue) | LLM retains context for form filling |
| Route | Reuse `/documents/[id]` | Avoid duplicate page implementations |
| Download | DOCX + PDF | Word for editing, PDF for distribution |
| Doc updates | LLM regenerates full doc | Matches create_document backend pattern |
| User editing | Toggle markdown editor | Default rendered view, toggle to edit |

## Changes

### Phase 1: Shared Types + Stream Document Events

**New file: `client/types/chat.ts`**
- Add shared `ChatMessage` interface used by both simple and full chat UIs
- Add `DocumentInfo` interface to hold document data from `create_document` tool results
- Keep stream-specific event definitions in `client/types/stream.ts`

```typescript
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  reasoning?: string;
  agent_id?: string;
  agent_name?: string;
}

export interface DocumentInfo {
  document_id?: string;
  document_type: string;
  title: string;
  content?: string;
  status?: string;
  word_count?: number;
  generated_at?: string;
  s3_key?: string;
  s3_location?: string;
}
```

**File: `client/components/chat/chat-interface.tsx`**
- Replace local `Message` interface with import from `client/types/chat.ts`

**File: `client/components/chat-simple/simple-chat-interface.tsx`**
- Replace imported `Message` type from `chat-interface.tsx` with `ChatMessage` from shared types

**File: `client/components/chat-simple/simple-message-list.tsx`**
- Use shared `ChatMessage` type and accept optional `documents` prop keyed by message id

**File: `client/hooks/use-agent-stream.ts`**
- Detect `tool_result` events where tool name is `create_document`
- Parse tool payload safely to extract `DocumentInfo`
- Expose `lastDocument` state and `onDocumentGenerated` callback
- Emit correlation metadata for deterministic message association

### Phase 2: Deterministic Tool-Result Correlation

Document cards and viewer updates will use explicit correlation rules:
1. Prefer backend event correlation id if available (`event.metadata.message_id` or equivalent).
2. Else attach document to latest assistant text message emitted in the same stream request.
3. If no assistant text exists yet, queue the document in `pendingDocumentByRequest`.
4. On next assistant text event for that request, flush pending document and attach.
5. Never attach a document tool result to user messages.

State shape in `use-agent-stream`:

```typescript
type PendingDocState = Record<string, DocumentInfo>;
type MessageDocState = Record<string, DocumentInfo>; // keyed by assistant message id
```

### Phase 3: Document Card in Chat

**New file: `client/components/chat-simple/document-card.tsx`**
- Receives: `DocumentInfo`, `sessionId`, `onClick` handler
- Renders: styled card with document type icon/badge, title, word count, "Open Document" button
- Styling: white card with left blue border, document type pill badge, consistent with NCI theme
- On click: navigates to `/documents/{documentId}?session={sessionId}`
- If no `documentId` is available, fall back to a safe encoded id source agreed with backend (not raw path-like S3 key)

**File: `client/components/chat-simple/simple-message-list.tsx`**
- After rendering an assistant message, check if there's an associated document
- If so, render `<DocumentCard>` below the message bubble
- Documents are tracked via a `documents` prop (map of message_id → DocumentInfo)

**File: `client/components/chat-simple/simple-chat-interface.tsx`**
- Subscribe to `onDocumentGenerated` from `useAgentStream`
- Store documents in state: `Record<string, DocumentInfo>` keyed by the message ID they follow
- Pass documents map to `SimpleMessageList`

### Phase 4: Document Viewer Page

**File: `client/app/documents/[id]/page.tsx`** (enhance existing)
- Replace mock chat with real backend chat via `useAgentStream`
- Read `session` query param to continue same session
- Load document content from:
  - URL state (passed when navigating from chat) for instant load
  - S3 via `/api/documents/{id}?content=true` as fallback/refresh
- Left panel (65%):
  - Default: rendered markdown view using `<MarkdownRenderer>`
  - Toggle button: "Edit Markdown" switches to `<textarea>` editor
  - Document header: title, type badge, status, version, last updated
- Right panel (35%):
  - Connected chat using `useAgentStream` with same `session_id`
  - When `create_document` tool_result arrives in this chat, update left panel content
  - Same message rendering as main chat (ReactMarkdown, copy button, etc.)
- Top bar:
  - Back button (← returns to main chat)
  - Document title
  - Download dropdown (DOCX / PDF)
  - Save button (saves edits back to S3)

### Phase 5: Download Functionality

**File: `client/app/documents/[id]/page.tsx`** (in the same enhanced page)
- Download dropdown with two options: "Download as Word (.docx)" and "Download as PDF (.pdf)"
- Calls frontend proxy export endpoint: `POST /api/documents`
  ```json
  { "content": "<markdown>", "title": "<title>", "format": "docx" | "pdf" }
  ```
- Include `Authorization` header via existing auth context token in fetch request
- Response is binary file → trigger browser download via blob URL

### Phase 6: Document Update Flow

When user says "add security requirements" in the document chat:
1. LLM calls `create_document` tool again → tool_result comes back
2. `useAgentStream` detects the `tool_result` for `create_document`
3. Document viewer page receives the updated content via callback
4. Left panel re-renders with new content
5. Visual indicator: brief highlight/flash to show document was updated

When user edits directly in markdown editor:
1. User toggles to editor mode
2. Makes changes in textarea
3. Clicks "Save" → content state updates, view toggles back to rendered
4. Optionally: save to S3 via API call

## Files Modified

| File | Change Type | Description |
|------|-------------|-------------|
| `client/types/chat.ts` | **new** | Shared `ChatMessage` and `DocumentInfo` types |
| `client/types/stream.ts` | modify | Keep stream events only; reference shared types where needed |
| `client/hooks/use-agent-stream.ts` | modify | Capture create_document tool_results, expose callbacks, correlation |
| `client/components/chat-simple/document-card.tsx` | **new** | Document card widget for chat messages |
| `client/components/chat-simple/simple-message-list.tsx` | modify | Render document cards after relevant messages |
| `client/components/chat-simple/simple-chat-interface.tsx` | modify | Use shared message types, track documents from stream |
| `client/components/chat/chat-interface.tsx` | modify | Import shared message type instead of defining local duplicate |
| `client/app/documents/[id]/page.tsx` | modify | Major enhancement: real chat, download, editor toggle |
| `client/tests/simple-chat-document-card.spec.ts` | **new** | Chat card render + click navigation test |
| `client/tests/document-viewer-session.spec.ts` | **new** | Session carryover + live update test |
| `client/tests/document-export.spec.ts` | **new** | DOCX/PDF export success + failure test |

## Component Design

### DocumentCard Props
```typescript
interface DocumentCardProps {
  document: DocumentInfo;
  sessionId: string;
}
```

### Enhanced Document Viewer Page State
```typescript
// Key state in the enhanced /documents/[id] page
const [documentContent, setDocumentContent] = useState<string>('');
const [documentTitle, setDocumentTitle] = useState<string>('');
const [documentType, setDocumentType] = useState<string>('');
const [isEditing, setIsEditing] = useState(false);
const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
const sessionId = searchParams.get('session');
```

## Verification

1. `npm run build` — no TypeScript errors
2. Unit test: document card appears in chat after a mocked `create_document` tool result
3. Unit test: clicking card navigates to `/documents/{id}?session={sessionId}`
4. Integration test: document viewer chat uses same session and receives responses
5. Integration test: new `create_document` tool result updates left panel content
6. Integration test: queued tool result attaches correctly when assistant text arrives later
7. Unit/integration test: toggle to editor mode, edit, save, and preview updated content
8. API/UI test: DOCX and PDF export succeed via `POST /api/documents`
9. API/UI test: export failure shows user-facing error without crashing UI
10. Navigation test: back button returns to main chat with history intact

## Dependencies

- Existing: `react-markdown`, `lucide-react`, Tailwind CSS
- Existing: Frontend proxy `POST /api/documents` to backend export endpoint
- Existing: Backend `create_document` tool + S3 persistence
- Existing: `useAgentStream` hook, session management
- No new npm packages required
