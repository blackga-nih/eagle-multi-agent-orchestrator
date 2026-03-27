# Jira Tickets - Completed Work

> Generated: 2026-02-18
> Status: All tickets completed and ready for documentation

---

## EAGLE-001: Fix Document Checklist Status & Linking

**Type:** Bug
**Priority:** High
**Component:** Frontend - Acquisition Pane
**Status:** Done

### Summary
Fix document checklist in acquisition pane to show accurate completion status and link to actual generated documents instead of hardcoded templates.

### Description
The document checklist in `document-checklist.tsx` had two critical bugs:
1. **Wrong status logic** - Documents were marked "completed" based on intake field presence, not actual document generation
2. **Template content instead of generated docs** - Clicking a document showed hardcoded inline templates, not actual generated documents from `document-store.ts`

### Acceptance Criteria
- [x] Documents show "completed" status ONLY when `document_id` exists in package checklist
- [x] Clicking completed documents opens document viewer page in new tab
- [x] Clicking non-completed documents shows template preview with "Template" badge
- [x] Progress bar and completion count reflect actual generated documents
- [x] Status persists across page refreshes (via localStorage)
- [x] TypeScript compiles without errors

### Technical Details
**Files Modified:**
- `client/components/checklist/document-checklist.tsx`
- `client/components/chat/chat-interface.tsx`

**Key Changes:**
- Added `sessionId` prop for package lookup
- Implemented `DOC_TYPE_MAP` for document type mapping
- Status derivation from actual `PackageChecklist.document_id`
- Navigation to `/documents/${document_id}` for completed docs
- Visual indicator with ExternalLink icon for viewable documents

---

## EAGLE-002: Fix Document Viewer Bugs (Load Failure, Navigation, Persistence)

**Type:** Bug
**Priority:** High
**Component:** Frontend - Document Viewer
**Status:** Done

### Summary
Fix three bugs preventing the document viewer from working end-to-end: sessionStorage key mismatch, same-tab navigation, and document card persistence.

### Description
Three bugs prevented the document viewer from working:
1. **Document can't load** - sessionStorage key mismatch between `document-card.tsx` (URL-encoded) and `documents/[id]/page.tsx` (decoded)
2. **Opens in same tab** - `router.push()` replaced the chat tab instead of opening new tab
3. **Cards vanish on back-nav** - Documents state was ephemeral React state, not persisted

### Acceptance Criteria
- [x] Document viewer loads content from sessionStorage or template fallback
- [x] "Open Document" button opens document in new tab
- [x] Document cards persist after navigating away and back
- [x] Template fallback works for S3 filenames (e.g., `sow_20260212_145613.md`)
- [x] Backward compatibility with old `%2E` encoded keys
- [x] TypeScript compiles without errors

### Technical Details
**Files Modified:**
- `client/components/chat-simple/document-card.tsx`
- `client/app/documents/[id]/page.tsx`
- `client/hooks/use-session-persistence.ts`
- `client/contexts/session-context.tsx`
- `client/components/chat-simple/simple-chat-interface.tsx`

**Key Changes:**
- Changed `router.push()` to `window.open(url, '_blank')`
- Removed `.replace(/\./g, '%2E')` encoding
- Added double-lookup for backward compat
- Added `TEMPLATE_MAP` with prefix-based matching
- Extended `SessionData` to include `documents` field
- Strip `content` field to prevent localStorage bloat

---

## EAGLE-003: Frontend Document Viewer with Chat Integration

**Type:** Story
**Priority:** High
**Component:** Frontend - Document Viewer
**Status:** Done

### Summary
Implement document viewer with integrated chat for real-time document editing and refinement through conversational AI.

### Description
Enhanced the document viewing experience with a split-view layout (65% document / 35% chat) that allows users to view generated documents while continuing to chat with the AI to make refinements.

### User Flow
1. User asks "Generate a SOW for IT services" in main chat
2. Backend generates document via `create_document` tool → saves to S3
3. Chat displays assistant response + embedded document card
4. User clicks "Open Document" → navigates to `/documents/{documentId}?session={sessionId}`
5. Document viewer opens in split view with chat panel continuing same session
6. User can refine document through chat or toggle to markdown editor
7. User can download as DOCX or PDF

### Acceptance Criteria
- [x] Document card appears in chat after document generation
- [x] Card displays document type badge, title, word count, "Open Document" button
- [x] Split view layout (65% document / 35% chat)
- [x] Same session continues in document viewer chat
- [x] Document updates automatically when LLM regenerates
- [x] Toggle between rendered view and markdown editor
- [x] Download functionality for DOCX and PDF formats
- [x] Back button returns to main chat with history intact

### Technical Details
**New Files:**
- `client/types/chat.ts` - Shared `ChatMessage` and `DocumentInfo` types
- `client/components/chat-simple/document-card.tsx` - Document card widget

**Modified Files:**
- `client/hooks/use-agent-stream.ts` - Capture `create_document` tool results
- `client/components/chat-simple/simple-message-list.tsx` - Render document cards
- `client/components/chat-simple/simple-chat-interface.tsx` - Track documents from stream
- `client/app/documents/[id]/page.tsx` - Enhanced with real chat, download, editor toggle

---

## EAGLE-004: Smart Chat Renaming for Acquisition Packages

**Type:** Story
**Priority:** Medium
**Component:** Frontend - Chat
**Status:** Done

### Summary
Implement intelligent chat session naming that extracts project name and document type from user messages instead of using generic "first 5 words" approach.

### Description
Previously, chat sessions were named using the first 5 words of the user's message, resulting in unhelpful titles like `/document I need an SOW...`. Now sessions are automatically renamed to meaningful titles like `EAGLE Agents - SOW` or `Lab Equipment - IGCE`.

### Acceptance Criteria
- [x] Chats auto-named with `{ProjectName} - {DocType}` format when identifiable
- [x] Slash commands stripped from titles
- [x] Backend API accepts title updates via PATCH endpoint
- [x] Users can double-click to rename sessions in sidebar
- [x] Titles persist across sessions and page reloads
- [x] Existing sessions retain their titles (no breaking change)

### Technical Details
**Files Modified:**
- `client/hooks/use-session-persistence.ts` - Smart title generation, `renameSession` function
- `client/components/layout/chat-history-dropdown.tsx` - Inline edit UI
- `server/app/main.py` - PATCH `/api/sessions/{session_id}` endpoint

**Key Features:**
- `parseUserIntent()` function for extracting document types
- `generateSmartTitle()` with priority: documents > parsed intent > acquisition data > fallback
- Pattern matching for project names: "for a project called X", "named X", etc.
- Document type detection: SOW, IGCE, Acquisition Plan, Market Research, Justification

---

## EAGLE-005: Home Page Redesign (Research Optimizer Style)

**Type:** Story
**Priority:** Medium
**Component:** Frontend - Home Page
**Status:** Done

### Summary
Redesign the application home page to match the Research Optimizer visual style and layout.

### Description
Updated the front page of the application to align with the Research Optimizer design language, improving visual consistency and user experience across the NCI application suite.

### Acceptance Criteria
- [x] Home page layout matches Research Optimizer style
- [x] Consistent visual design with NCI branding
- [x] Improved navigation and user flow
- [x] Responsive design maintained

### Technical Details
**Files Modified:**
- Frontend home page components
- Styling and layout updates

---

## EAGLE-006: Mock Document Templates for Application Preview

**Type:** Task
**Priority:** Low
**Component:** Frontend - Documents
**Status:** Done

### Summary
Create mock document templates that can be previewed within the application for demonstration and testing purposes.

### Description
Added mock templates for various acquisition document types (SOW, IGCE, Acquisition Plan, etc.) that users can view within the application. These templates serve as examples and fallbacks when actual generated documents are not available.

### Acceptance Criteria
- [x] Mock templates available for all major document types
- [x] Templates display correctly in document viewer
- [x] Templates serve as fallback when generated documents unavailable
- [x] Template content is realistic and representative

### Technical Details
**Template Types:**
- Statement of Work (SOW)
- Independent Government Cost Estimate (IGCE)
- Acquisition Plan
- Market Research
- Justification

---

## Summary

| Ticket | Type | Priority | Component |
|--------|------|----------|-----------|
| EAGLE-001 | Bug | High | Acquisition Pane |
| EAGLE-002 | Bug | High | Document Viewer |
| EAGLE-003 | Story | High | Document Viewer |
| EAGLE-004 | Story | Medium | Chat |
| EAGLE-005 | Story | Medium | Home Page |
| EAGLE-006 | Task | Low | Documents |

**Total Completed:** 6 tickets
**Sprint:** Document Viewer & UX Improvements
