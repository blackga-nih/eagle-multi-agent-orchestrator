# Smart Chat Renaming for Acquisition Packages

## Problem Statement

Currently, chat sessions are named using the first 5 words of the user's message, resulting in unhelpful titles like:
- `/document I need an SOW...`
- `/document I need an SOW...`

When users create documents or plans, the chat should be renamed to something meaningful like:
- `EAGLE Agents - SOW`
- `Lab Equipment - IGCE`

## Objectives

1. **Smart title extraction** - Parse user intent and extract project name + document type
2. **Backend API** - Add endpoint to update session titles
3. **Auto-rename on document generation** - Trigger rename when documents are created
4. **Manual rename UI** - Allow users to edit chat titles in the sidebar

---

## Technical Approach

### 1. Smart Title Generation Function

**File:** `client/hooks/use-session-persistence.ts`

Replace the naive `generateSessionTitle()` with intelligent parsing:

```typescript
interface ParsedIntent {
    projectName?: string;
    documentType?: string;
    action?: 'document' | 'plan' | 'intake' | 'question';
}

function parseUserIntent(message: string): ParsedIntent {
    const result: ParsedIntent = {};

    // Detect slash commands
    if (message.startsWith('/document')) {
        result.action = 'document';
    } else if (message.startsWith('/plan') || message.startsWith('/quick-plan')) {
        result.action = 'plan';
    } else if (message.startsWith('/oa-intake')) {
        result.action = 'intake';
    }

    // Extract document type from keywords
    const docTypePatterns: Record<string, string> = {
        'sow|statement of work': 'SOW',
        'igce|cost estimate': 'IGCE',
        'acquisition plan': 'Acquisition Plan',
        'market research': 'Market Research',
        'justification|j&a': 'Justification',
    };

    const lowerMsg = message.toLowerCase();
    for (const [pattern, label] of Object.entries(docTypePatterns)) {
        if (new RegExp(pattern).test(lowerMsg)) {
            result.documentType = label;
            break;
        }
    }

    // Extract project name using patterns like:
    // "for a project called X", "for X project", "called X", "named X"
    const projectPatterns = [
        /(?:project|program)\s+(?:called|named)\s+["']?([^"'.,]+)["']?/i,
        /(?:called|named)\s+["']?([^"'.,]+)["']?/i,
        /for\s+(?:the\s+)?["']?([A-Z][A-Za-z0-9\s]+?)["']?\s+(?:project|program|initiative)/i,
        /["']([^"']+)["']\s+(?:sow|igce|acquisition)/i,
    ];

    for (const pattern of projectPatterns) {
        const match = message.match(pattern);
        if (match) {
            result.projectName = match[1].trim();
            break;
        }
    }

    return result;
}

function generateSmartTitle(
    messages: Message[],
    acquisitionData: AcquisitionData,
    documents?: Record<string, DocumentInfo[]>
): string {
    // Priority 1: If we have documents, use document metadata
    if (documents && Object.keys(documents).length > 0) {
        const allDocs = Object.values(documents).flat();
        const firstDoc = allDocs[0];
        if (firstDoc) {
            const docLabel = formatDocType(firstDoc.document_type);
            const projectName = firstDoc.title?.replace(/\s*(SOW|IGCE|Plan).*$/i, '').trim();
            if (projectName && projectName !== docLabel) {
                return `${projectName} - ${docLabel}`;
            }
            return docLabel;
        }
    }

    // Priority 2: Parse first user message for intent
    const firstUserMessage = messages.find(m => m.role === 'user');
    if (firstUserMessage) {
        const parsed = parseUserIntent(firstUserMessage.content);

        if (parsed.projectName && parsed.documentType) {
            return `${parsed.projectName} - ${parsed.documentType}`;
        }
        if (parsed.projectName) {
            return parsed.projectName;
        }
        if (parsed.documentType) {
            return `New ${parsed.documentType}`;
        }
    }

    // Priority 3: Use acquisition requirement (cleaned)
    if (acquisitionData.requirement) {
        // Remove slash commands and extract meaningful content
        const cleaned = acquisitionData.requirement
            .replace(/^\/\w+\s*/, '')  // Remove slash command
            .replace(/^I need (an?|the)\s*/i, '')  // Remove "I need a/an/the"
            .trim();

        if (cleaned.length > 0) {
            const words = cleaned.split(' ').slice(0, 4).join(' ');
            return words + (cleaned.length > words.length ? '...' : '');
        }
    }

    // Fallback
    return `Session ${new Date().toLocaleDateString()}`;
}

function formatDocType(type: string): string {
    const labels: Record<string, string> = {
        'sow': 'SOW',
        'igce': 'IGCE',
        'acquisition_plan': 'Acquisition Plan',
        'market_research': 'Market Research',
        'justification': 'Justification',
        'funding_doc': 'Funding Document',
    };
    return labels[type] || type.toUpperCase();
}
```

### 2. Backend API Endpoint for Title Updates

**File:** `server/app/main.py`

Add a PATCH endpoint:

```python
from pydantic import BaseModel

class UpdateSessionRequest(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None
    metadata: Optional[Dict] = None

@app.patch("/api/sessions/{session_id}")
async def api_update_session(
    session_id: str,
    req: UpdateSessionRequest,
    user: UserContext = Depends(get_user_from_header)
):
    """Update session title or metadata."""
    tenant_id, user_id, _ = get_session_context(user)

    updates = {}
    if req.title is not None:
        updates["title"] = req.title
    if req.status is not None:
        updates["status"] = req.status
    if req.metadata is not None:
        updates["metadata"] = req.metadata

    if USE_PERSISTENT_SESSIONS:
        session = eagle_update_session(session_id, tenant_id, user_id, updates)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return session
    else:
        if session_id not in SESSIONS:
            raise HTTPException(status_code=404, detail="Session not found")
        # In-memory sessions don't have metadata, just acknowledge
        return {"session_id": session_id, **updates}
```

### 3. Frontend: Add renameSession Function

**File:** `client/hooks/use-session-persistence.ts`

Add to the hook return:

```typescript
interface UseSessionPersistenceReturn {
    // ... existing
    renameSession: (sessionId: string, newTitle: string) => void;
}

const renameSession = useCallback((sessionId: string, newTitle: string) => {
    try {
        const stored = localStorage.getItem(STORAGE_KEY);
        if (!stored) return;

        const allSessions: Record<string, SessionData> = JSON.parse(stored);
        if (allSessions[sessionId]) {
            allSessions[sessionId].title = newTitle;
            allSessions[sessionId].updatedAt = new Date().toISOString();
            localStorage.setItem(STORAGE_KEY, JSON.stringify(allSessions));

            setSessions((prev) =>
                prev.map((s) =>
                    s.id === sessionId
                        ? { ...s, title: newTitle, updatedAt: new Date() }
                        : s
                )
            );

            // Sync to backend if available
            fetch(`/api/sessions/${sessionId}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title: newTitle }),
            }).catch(console.error);
        }
    } catch (error) {
        console.error('Error renaming session:', error);
    }
}, []);
```

### 4. Manual Rename UI in Chat History

**File:** `client/components/layout/chat-history-dropdown.tsx`

Add inline edit capability:

```typescript
interface ChatHistoryDropdownProps {
    // ... existing
    onRenameSession?: (sessionId: string, newTitle: string) => void;
}

// Inside the component:
const [editingId, setEditingId] = useState<string | null>(null);
const [editTitle, setEditTitle] = useState('');

const handleStartEdit = (session: ChatSession, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingId(session.id);
    setEditTitle(session.title);
};

const handleSaveEdit = () => {
    if (editingId && editTitle.trim() && onRenameSession) {
        onRenameSession(editingId, editTitle.trim());
    }
    setEditingId(null);
};

// In the session item render:
{editingId === session.id ? (
    <input
        type="text"
        value={editTitle}
        onChange={(e) => setEditTitle(e.target.value)}
        onBlur={handleSaveEdit}
        onKeyDown={(e) => e.key === 'Enter' && handleSaveEdit()}
        className="text-sm font-medium w-full bg-white border rounded px-1"
        autoFocus
        onClick={(e) => e.stopPropagation()}
    />
) : (
    <p className="text-sm font-medium truncate" onDoubleClick={(e) => handleStartEdit(session, e)}>
        {session.title}
    </p>
)}
```

### 5. Auto-Rename on Document Generation

When a document is generated, update the session title automatically.

**File:** `client/components/chat/chat-interface.tsx` (or wherever documents are processed)

```typescript
// After document generation succeeds:
const handleDocumentGenerated = (doc: DocumentInfo) => {
    const projectName = extractProjectName(doc);
    const docType = formatDocType(doc.document_type);
    const newTitle = projectName ? `${projectName} - ${docType}` : `New ${docType}`;

    renameSession(currentSessionId, newTitle);
};
```

---

## Implementation Steps

1. **Update `generateSessionTitle`** in `use-session-persistence.ts`
   - Add `parseUserIntent()` function
   - Add `generateSmartTitle()` function
   - Replace existing title generation

2. **Add backend PATCH endpoint**
   - Add `UpdateSessionRequest` model
   - Add `/api/sessions/{session_id}` PATCH route
   - Update `session_store.py` if needed

3. **Add `renameSession` to hook**
   - Implement localStorage update
   - Add backend sync call
   - Export from hook

4. **Update chat history UI**
   - Add double-click to edit
   - Add inline input field
   - Wire up rename callback

5. **Add auto-rename trigger**
   - Hook into document generation flow
   - Call rename with smart title

---

## Testing Strategy

1. **Unit Tests**
   - `parseUserIntent()` with various input formats
   - `generateSmartTitle()` priority logic
   - Edge cases: empty messages, no project name, etc.

2. **Integration Tests**
   - Create session → generate document → verify title updates
   - Manual rename → verify persistence
   - Backend sync → verify DynamoDB update

3. **Manual Testing Scenarios**
   - `/document I need an SOW for a project called EAGLE Agents` → "EAGLE Agents - SOW"
   - `/document Create an IGCE for Lab Equipment` → "Lab Equipment - IGCE"
   - Double-click to rename → new title persists
   - Refresh page → title remains

---

## Success Criteria

- [ ] Chats auto-named with `{ProjectName} - {DocType}` format when identifiable
- [ ] Slash commands stripped from titles
- [ ] Backend API accepts title updates
- [ ] Users can double-click to rename in sidebar
- [ ] Titles persist across sessions and page reloads
- [ ] Existing sessions retain their titles (no breaking change)

---

## Files to Modify

| File | Changes |
|------|---------|
| `client/hooks/use-session-persistence.ts` | Smart title gen, renameSession |
| `client/components/layout/chat-history-dropdown.tsx` | Inline edit UI |
| `server/app/main.py` | PATCH endpoint |
| `server/app/session_store.py` | Verify update_session works |
| `client/types/chat.ts` | Add title to DocumentInfo if needed |
