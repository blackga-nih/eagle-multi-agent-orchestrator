# Chat Thread Persistence — Implementation Plan

**Date:** 2026-03-20
**Status:** Ready to implement
**Branch:** `main` (independent of `dev/refactor-0319-ah`)
**Source plans:** `20260318-chat-thread-phase1-stabilization-plan.md`, `20260318-chat-thread-phase2-concurrent-generation-plan.md`

---

## Problem

When a user switches chat threads during active streaming, three things go wrong:

1. **Stream callbacks write to the wrong thread** — `onComplete` at line 297 of `simple-chat-interface.tsx` captures ambient `currentSessionId` at fire time, not at send time. Title generation, document saves, and message commits land in whichever thread is visible when the callback fires.

2. **Autosave persists to the wrong session** — `saveSession()` (line 135) takes no `sessionId` parameter. The 500ms debounce can fire after a session switch, writing thread A's messages into thread B's storage.

3. **IDB writes use stale session ID** — The async IndexedDB write at `use-local-cache.ts:373` closes over `currentSessionId` and can execute after the user has already navigated away.

---

## Implementation Sequence

### PR 1: Phase 1 — Stop Corruption (4 files, ~80 lines changed)

| Step | File | Change |
|------|------|--------|
| 1a | `client/hooks/use-local-cache.ts` | Add `sessionId: string` as first param to `saveSession` |
| 1b | `client/contexts/session-context.tsx` | Update `SessionContextValue.saveSession` type |
| 1c | `client/components/chat-simple/simple-chat-interface.tsx` | Pass explicit `sessionId`, add request guards, clear transient state |
| 1d | `client/components/chat/chat-interface.tsx` | Same fixes for legacy chat |

### PR 2: Phase 2 — Background Generation (3 new files, 3 modified)

| Step | File | Change |
|------|------|--------|
| 2a | `client/contexts/chat-runtime-context.tsx` | NEW — per-session runtime store with reducer |
| 2b | `client/lib/chat-stream-manager.ts` | NEW — multi-request SSE transport |
| 2c | `client/hooks/use-chat-runtime.ts` | NEW — selector hook |
| 2d | `client/components/chat-simple/simple-chat-interface.tsx` | Replace local state with runtime selectors |
| 2e | `client/components/layout/sidebar-nav.tsx` | Add streaming indicator per session |
| 2f | `client/components/chat-simple/simple-chat-interface.tsx` | Stop button + Esc handling |

### PR 3: Tests

| Step | File | Change |
|------|------|--------|
| 3a | `client/tests/chat-thread-isolation.spec.ts` | NEW — Playwright regression tests |

---

## PR 1 Detail: Phase 1 — Stop Corruption

### Step 1a: `client/hooks/use-local-cache.ts`

**Current signature (line 274):**
```ts
const saveSession = useCallback(
    (messages: Message[], acquisitionData: AcquisitionData, documents?: Record<string, DocumentInfo[]>): void => {
        if (!currentSessionId || messages.length === 0) return;
        // writes to allSessions[currentSessionId]
    },
    [currentSessionId, userId, tenantId],
);
```

**New signature:**
```ts
const saveSession = useCallback(
    (sessionId: string, messages: Message[], acquisitionData: AcquisitionData, documents?: Record<string, DocumentInfo[]>): void => {
        if (!sessionId || messages.length === 0) return;
        // writes to allSessions[sessionId]  (NOT currentSessionId)
    },
    [userId, tenantId],  // remove currentSessionId from deps
);
```

**Changes required inside the function body:**
- Line 280: `if (!currentSessionId` → `if (!sessionId`
- Line 288: `allSessions[currentSessionId]` → `allSessions[sessionId]`
- Line 303: `allSessions[currentSessionId] = sessionData` → `allSessions[sessionId] = sessionData`
- Line 323: localStorage key construction — use `sessionId` param
- Line 373: IDB write — use `sessionId` param instead of closure `currentSessionId`
- Line 379: Remove `currentSessionId` from dependency array

**Why:** Eliminates the root cause. The save target is now determined by the caller, not by ambient context state. The function no longer depends on `currentSessionId`, so React won't recreate it on session switches.

### Step 1b: `client/contexts/session-context.tsx`

**Current type (line 14):**
```ts
saveSession: (messages: Message[], acquisitionData: AcquisitionData, documents?: Record<string, DocumentInfo[]>) => void;
```

**New type:**
```ts
saveSession: (sessionId: string, messages: Message[], acquisitionData: AcquisitionData, documents?: Record<string, DocumentInfo[]>) => void;
```

### Step 1c: `client/components/chat-simple/simple-chat-interface.tsx`

**4 changes in this file:**

**Change 1 — Add request tracking refs (after line 78):**
```ts
const activeRequestSessionIdRef = useRef<string | null>(null);
const activeRequestIdRef = useRef<string | null>(null);
```

**Change 2 — Guard autosave with explicit sessionId (lines 133-137):**

Current:
```ts
const saveSessionDebounced = useCallback(() => {
    if (messages.length > 0) {
        saveSession(messages, {}, documents);
    }
}, [messages, documents, saveSession]);
```

New:
```ts
const saveSessionDebounced = useCallback(() => {
    if (messages.length > 0 && currentSessionId) {
        saveSession(currentSessionId, messages, {}, documents);
    }
}, [currentSessionId, messages, documents, saveSession]);
```

**Change 3 — Capture session at send time + guard callbacks (line 412+):**

In `handleSend`, before calling `sendQuery`:
```ts
const sessionIdAtSend = currentSessionId;
const requestId = crypto.randomUUID();
activeRequestSessionIdRef.current = sessionIdAtSend;
activeRequestIdRef.current = requestId;
```

Then guard every callback. For each of the 7 callbacks in the `useAgentStream` options:
```ts
onMessage: (msg) => {
    if (activeRequestIdRef.current !== requestId) return;
    // ... existing logic
},
onComplete: (info) => {
    if (activeRequestIdRef.current !== requestId) return;
    // ... existing logic
    // Line 297: replace `const sid = currentSessionId` with `const sid = sessionIdAtSend`
},
onDocumentGenerated: (doc) => {
    if (activeRequestIdRef.current !== requestId) return;
    // ... existing logic
    // Line 342: replace `if (currentSessionId)` with `if (sessionIdAtSend)`
    // Line 346: replace `saveGeneratedDocument(doc, currentSessionId, title)` with `saveGeneratedDocument(doc, sessionIdAtSend, title)`
},
// same pattern for onToolUse, onToolResult, onError, onAgentStatus
```

**Implementation note:** The closure-based guard works because `requestId` and `sessionIdAtSend` are `const` values captured when `handleSend` runs. They don't change when `currentSessionId` changes. The `activeRequestIdRef` check is the early-exit: if a new request started (user sent another message or switched sessions), the old callbacks silently no-op.

**Change 4 — Clear transient state on session switch (line 110 useEffect):**

Add to the existing `currentSessionId` useEffect, before loading:
```ts
// Clear transient state from previous session
setStreamingMsg(null);
streamingMsgRef.current = null;
setAgentStatus(null);
setToolCallsByMsg({});
lastAssistantIdRef.current = null;
activeRequestSessionIdRef.current = null;
activeRequestIdRef.current = null;
```

### Step 1d: `client/components/chat/chat-interface.tsx`

Mirror the same changes:
- Autosave: `saveSession(currentSessionId, messages, acquisitionData)` (line 93)
- Add request tracking refs
- Guard stream callbacks with `requestId`
- Clear transient state on session switch (line 70 useEffect)

### Phase 1 Validation

```bash
npx tsc --noEmit                    # TypeScript compiles
npx playwright test chat-thread     # Regression tests pass
```

Manual test:
1. Start a message in thread A
2. While streaming, click a different thread in sidebar
3. Verify thread B shows its own history, not thread A's streaming content
4. Return to thread A — verify its history is intact (stream may have been lost, which is expected for Phase 1)

---

## PR 2 Detail: Phase 2 — Background Generation

### Step 2a: `client/contexts/chat-runtime-context.tsx` (NEW)

Per-session runtime store using `useReducer`. This replaces the local `useState` calls in `simple-chat-interface.tsx`.

**Types:**
```ts
type SessionGenerationState = {
  sessionId: string;
  activeRequestId: string | null;
  status: 'idle' | 'streaming' | 'stopping' | 'error';
  streamingMessage: ChatMessage | null;
  streamingMessageId: string | null;
  toolCallsByMsg: ToolCallsByMessageId;
  documentsByMsg: Record<string, DocumentInfo[]>;
  agentStatus: string | null;
  error: string | null;
};

type ChatRuntimeState = Record<string, SessionGenerationState>;
```

**Reducer actions:**
```ts
type Action =
  | { type: 'generation/start'; sessionId: string; requestId: string; streamingMsgId: string }
  | { type: 'generation/message'; sessionId: string; requestId: string; message: ChatMessage }
  | { type: 'generation/status'; sessionId: string; requestId: string; status: string }
  | { type: 'generation/toolUse'; sessionId: string; requestId: string; toolUseId: string; patch: Partial<TrackedToolCall> }
  | { type: 'generation/toolResult'; sessionId: string; requestId: string; toolName: string; result: unknown }
  | { type: 'generation/document'; sessionId: string; requestId: string; document: DocumentInfo }
  | { type: 'generation/complete'; sessionId: string; requestId: string; finalMessage?: ChatMessage }
  | { type: 'generation/error'; sessionId: string; requestId: string; error: string }
  | { type: 'generation/stopping'; sessionId: string }
  | { type: 'generation/reset'; sessionId: string };
```

**Reducer rule:** Every action checks `state[sessionId]?.activeRequestId === requestId`. If mismatch, the action is ignored (stale event from a previous request).

**Provider:** Wraps the app at the same level as `SessionProvider`. Exposes `dispatch` and `state` via context.

### Step 2b: `client/lib/chat-stream-manager.ts` (NEW)

Replaces the singleton `useAgentStream` hook for request lifecycle management.

**API:**
```ts
class ChatStreamManager {
  // Start a new SSE request for a session
  startQuery(params: {
    sessionId: string;
    query: string;
    packageId?: string;
    getToken: () => Promise<string>;
    dispatch: React.Dispatch<Action>;
  }): string;  // returns requestId

  // Abort the active request for a session
  stopQuery(sessionId: string): void;

  // Check if a session has an active request
  isStreaming(sessionId: string): boolean;
}
```

**Internal state:**
```ts
private requests = new Map<string, {  // keyed by requestId
  sessionId: string;
  abortController: AbortController;
}>();
private sessionToRequest = new Map<string, string>();  // sessionId → requestId
```

**Key behaviors:**
- `startQuery` rejects if `sessionToRequest.has(sessionId)` (one active per session)
- SSE events are parsed and dispatched as reducer actions with `sessionId` + `requestId`
- `stopQuery` aborts the controller and dispatches `generation/stopping`
- The manager does NOT call React state setters — it only dispatches actions

**SSE parsing:** Extracted from `use-agent-stream.ts` lines 358-508. Same event handling logic (text, tool_use, tool_result, document_generated, complete, error, metadata) but routed through `dispatch` instead of callback functions.

### Step 2c: `client/hooks/use-chat-runtime.ts` (NEW)

Selector hook for the view layer:
```ts
function useChatRuntime(sessionId: string): SessionGenerationState & {
  isStreaming: boolean;
  isIdle: boolean;
} {
  const { state } = useChatRuntimeContext();
  const session = state[sessionId] ?? IDLE_STATE;
  return {
    ...session,
    isStreaming: session.status === 'streaming',
    isIdle: session.status === 'idle',
  };
}
```

### Step 2d: Migrate `simple-chat-interface.tsx`

**Remove local state:**
```diff
- const [streamingMsg, setStreamingMsg] = useState<ChatMessage | null>(null);
- const streamingMsgRef = useRef<ChatMessage | null>(null);
- const [toolCallsByMsg, setToolCallsByMsg] = useState<ToolCallsByMessageId>({});
- const [agentStatus, setAgentStatus] = useState<string | null>(null);
- const streamingMsgIdRef = useRef<string>(`stream-${Date.now()}`);
```

**Replace with selectors:**
```ts
const runtime = useChatRuntime(currentSessionId);
const streamingMsg = runtime.streamingMessage;
const toolCallsByMsg = runtime.toolCallsByMsg;
const agentStatus = runtime.agentStatus;
const isStreaming = runtime.isStreaming;
```

**Replace `sendQuery` call with stream manager:**
```ts
const streamManager = useChatStreamManager();

const handleSend = async () => {
    // ... user message handling (unchanged)
    const requestId = streamManager.startQuery({
        sessionId: currentSessionId,
        query,
        packageId: packageState.packageId,
        getToken,
        dispatch,
    });
};
```

**Replace `handleStopGeneration` with:**
```ts
const handleStopGeneration = () => {
    streamManager.stopQuery(currentSessionId);
};
```

**Remove all stream callback handlers** — they're now inside the stream manager dispatching to the reducer.

**Add generation finalization effect:**
```ts
// When runtime transitions to 'idle' after 'streaming', commit the final message
useEffect(() => {
    if (runtime.status === 'idle' && runtime.streamingMessage === null) {
        // Already committed by reducer's generation/complete handler
        return;
    }
}, [runtime.status]);
```

### Step 2e: Sidebar streaming indicator

In `sidebar-nav.tsx`, for each session row:
```tsx
const runtime = useChatRuntime(session.id);

// In the session row JSX:
{runtime.isStreaming && (
    <span className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-pulse shrink-0" />
)}
```

### Step 2f: Stop controls

**Stop button** — show in chat input area when `runtime.isStreaming`:
```tsx
{isStreaming && (
    <button onClick={handleStopGeneration} className="...">
        Stop generating
    </button>
)}
```

**Esc handler** — scoped to visible session only:
```ts
useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
        if (e.key === 'Escape' && runtime.isStreaming) {
            // Show confirm dialog or stop directly
            streamManager.stopQuery(currentSessionId);
        }
    };
    window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
}, [currentSessionId, runtime.isStreaming]);
```

**Same-session resend block:**
```ts
const handleSend = async () => {
    if (!input.trim() || runtime.isStreaming) return;
    // ...
};
```

---

## PR 3: Playwright Tests

### `client/tests/chat-thread-isolation.spec.ts`

**Phase 1 tests (corruption prevention):**

| # | Scenario | Assert |
|---|----------|--------|
| 1 | Send message in thread A, switch to thread B before completion | Thread B history unchanged |
| 2 | Send in A, switch to B, return to A | Thread A history intact, no B content leaked |
| 3 | Send in A, create new thread | New thread is empty |
| 4 | Send in A, switch to B, wait for A's debounce | Thread B localStorage not overwritten |

**Phase 2 tests (background generation):**

| # | Scenario | Assert |
|---|----------|--------|
| 5 | Send in A, switch to B, send in B | Both sessions show independent progress |
| 6 | Return to A after delay | A accumulated output while in background |
| 7 | Press Esc in B while B streaming, A streaming | Only B stops; A continues |
| 8 | Press Esc in B when only A streaming in background | Nothing happens |
| 9 | Try second send in same session while streaming | Send blocked with message |

---

## File Change Summary

| PR | File | Action | Lines |
|----|------|--------|-------|
| 1 | `client/hooks/use-local-cache.ts` | EDIT | ~15 |
| 1 | `client/contexts/session-context.tsx` | EDIT | ~2 |
| 1 | `client/components/chat-simple/simple-chat-interface.tsx` | EDIT | ~40 |
| 1 | `client/components/chat/chat-interface.tsx` | EDIT | ~25 |
| 2 | `client/contexts/chat-runtime-context.tsx` | NEW | ~180 |
| 2 | `client/lib/chat-stream-manager.ts` | NEW | ~250 |
| 2 | `client/hooks/use-chat-runtime.ts` | NEW | ~30 |
| 2 | `client/components/chat-simple/simple-chat-interface.tsx` | EDIT | ~120 |
| 2 | `client/components/layout/sidebar-nav.tsx` | EDIT | ~10 |
| 2 | `client/hooks/use-agent-stream.ts` | DEPRECATE | -- |
| 3 | `client/tests/chat-thread-isolation.spec.ts` | NEW | ~200 |

---

## Acceptance Criteria

### Phase 1
1. Switching threads during streaming does not corrupt either thread's history
2. `saveSession` requires explicit `sessionId` — no ambient state dependency
3. Stale stream callbacks are silently dropped
4. Transient state (streamingMsg, toolCalls, agentStatus) cleared on thread switch
5. TypeScript compiles clean, Playwright Phase 1 tests pass

### Phase 2
6. Thread A continues generating after switching to thread B
7. Thread B can start its own generation while A runs
8. Stream events route only to their originating session
9. Sidebar shows streaming indicator for background sessions
10. Esc/stop button only affects the visible thread
11. Second send in same session is blocked while streaming
12. Playwright Phase 2 tests pass
