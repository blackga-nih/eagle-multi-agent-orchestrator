# 2026-03-18 Chat Thread Stabilization Plan (Phase 1)

Date: 2026-03-18
Owner: EAGLE engineering
Status: Proposed
Audience: Frontend engineers working on chat/thread state
Scope: Stop cross-thread corruption without yet supporting simultaneous active generation across threads

## 1. Purpose
This plan describes the first implementation phase for the chat thread switching bug:

- A response that started in thread A can continue to write into thread B after the user switches threads.
- The visible history in thread B can be replaced or polluted by updates that originated in thread A.
- Autosave can then persist the corrupted in-memory state under the wrong `sessionId`.

Phase 1 is intentionally scoped to stop data corruption and restore thread isolation. It is not meant to deliver the final product behavior of background generation across multiple threads. That is covered in Phase 2.

## 2. Goals
### In scope
- Prevent stream updates from thread A from mutating thread B's visible state.
- Prevent autosave from persisting messages/documents/tool state into the wrong session.
- Make session ownership explicit in persistence paths.
- Add regression coverage for thread-switch corruption.

### Out of scope
- Allowing thread A to continue generating while thread B also generates.
- Multiple concurrent active streams in the frontend.
- Final `Esc` stop-generation UX.
- Sidebar indicators for background generation.

## 3. Current Failure Mechanism

## 3.1 Shared visible thread state
In [simple-chat-interface.tsx](/Users/hoquemi/Desktop/sm_eagle/client/components/chat-simple/simple-chat-interface.tsx), the component keeps one mutable copy of:

- `messages`
- `streamingMsg`
- `documents`
- `toolCallsByMsg`
- `agentStatus`

Those values represent "whatever thread is currently open", not "the thread that originated the stream".

When `currentSessionId` changes, the component reloads a different thread into that same state container.

## 3.2 Stream callbacks outlive the selected thread
In [use-agent-stream.ts](/Users/hoquemi/Desktop/sm_eagle/client/hooks/use-agent-stream.ts), stream callbacks continue to emit `onMessage`, `onToolUse`, `onToolResult`, `onDocumentGenerated`, and `onComplete` after a thread switch.

Those callbacks are not scoped to the originating session at the UI layer. They call setters captured from the active component instance, which means late events from thread A can still mutate the now-visible thread B state.

## 3.3 Autosave uses ambient session state
In [use-local-cache.ts](/Users/hoquemi/Desktop/sm_eagle/client/hooks/use-local-cache.ts), `saveSession()` writes to whatever `currentSessionId` is active when the save happens.

That means:
1. Thread A starts streaming.
2. User switches to thread B.
3. Late updates from A modify the shared `messages` array.
4. Debounced `saveSession()` runs under `currentSessionId = B`.
5. Thread B gets thread A's content written into its persisted history.

## 3.4 Why a narrow guard is still useful
Even though Phase 1 will not satisfy the final product requirement, it is still worth doing because it:

- eliminates data corruption quickly
- reduces risk before the larger concurrency refactor
- gives us safer tests and clearer interfaces for Phase 2

## 4. Phase 1 Design Principles

1. A stream response must be associated with the `sessionId` that started it.
2. Visible component state must reject updates from stale or foreign sessions.
3. Persistence APIs must not infer the target session from mutable global UI state.
4. Thread switching must clear transient view state that should not follow the user into another thread.

## 5. Implementation Plan

## 5.1 Make persistence APIs explicitly session-scoped
Primary file:
- [use-local-cache.ts](/Users/hoquemi/Desktop/sm_eagle/client/hooks/use-local-cache.ts)

Current problem:
- `saveSession(messages, acquisitionData, documents)` writes using `currentSessionId` from closure state.

Change:
- Update the API to:
```ts
saveSession(
  sessionId: string,
  messages: Message[],
  acquisitionData: AcquisitionData,
  documents?: Record<string, DocumentInfo[]>,
): void
```

Required changes:
- Update `SessionContextValue` in [session-context.tsx](/Users/hoquemi/Desktop/sm_eagle/client/contexts/session-context.tsx)
- Update all callers in:
  - [simple-chat-interface.tsx](/Users/hoquemi/Desktop/sm_eagle/client/components/chat-simple/simple-chat-interface.tsx)
  - [chat-interface.tsx](/Users/hoquemi/Desktop/sm_eagle/client/components/chat/chat-interface.tsx)
  - any document page or admin page using `saveSession`

Expected result:
- Persistence target is always explicit.
- Late callbacks can no longer accidentally save to the currently selected thread just because the user navigated away.

## 5.2 Track the session that owns the active request
Primary file:
- [simple-chat-interface.tsx](/Users/hoquemi/Desktop/sm_eagle/client/components/chat-simple/simple-chat-interface.tsx)

Add refs:
```ts
const activeRequestSessionIdRef = useRef<string | null>(null);
const activeRequestIdRef = useRef<string | null>(null);
```

Behavior:
- On `handleSend`, capture the current `sessionId` into `activeRequestSessionIdRef`.
- Generate a request token and store it in `activeRequestIdRef`.
- Pass both to stream handling logic.

Reason:
- The UI must know whether an incoming callback belongs to the thread currently being rendered.

## 5.3 Guard every stream callback by originating session
Primary files:
- [simple-chat-interface.tsx](/Users/hoquemi/Desktop/sm_eagle/client/components/chat-simple/simple-chat-interface.tsx)
- optionally [use-agent-stream.ts](/Users/hoquemi/Desktop/sm_eagle/client/hooks/use-agent-stream.ts) if we add lightweight metadata

Pattern:
- For each callback, compare the callback's originating `sessionId` or current request token against the refs set when the request started.
- If the callback does not belong to the currently owned request, ignore it.

Callbacks to guard:
- `onMessage`
- `onComplete`
- `onError`
- `onDocumentGenerated`
- `onToolUse`
- `onToolResult`
- `onAgentStatus`

Short-term implementation option:
- If `useAgentStream` does not yet emit `sessionId` in callbacks, wrap it from the component side by capturing `sessionIdAtSend` in closure variables.

Example approach:
```ts
const sessionIdAtSend = currentSessionId;
const requestId = crypto.randomUUID();
activeRequestSessionIdRef.current = sessionIdAtSend;
activeRequestIdRef.current = requestId;
```

Then inside callbacks:
```ts
if (activeRequestIdRef.current !== requestId) return;
if (activeRequestSessionIdRef.current !== sessionIdAtSend) return;
```

This is sufficient for Phase 1 because only one stream is supported at a time.

## 5.4 Clear transient view state on thread switch
Primary file:
- [simple-chat-interface.tsx](/Users/hoquemi/Desktop/sm_eagle/client/components/chat-simple/simple-chat-interface.tsx)

When `currentSessionId` changes:
- reload persisted session data as today
- also clear:
  - `streamingMsg`
  - `streamingMsgRef`
  - `agentStatus`
  - `toolCallsByMsg`
  - `lastAssistantIdRef`
  - any temporary stream message IDs for the previous thread

Reason:
- Even if a stale callback is later ignored, the new thread should not inherit transient artifacts from the previous one.

## 5.5 Stop autosave from following the selected thread implicitly
Primary files:
- [simple-chat-interface.tsx](/Users/hoquemi/Desktop/sm_eagle/client/components/chat-simple/simple-chat-interface.tsx)
- [use-local-cache.ts](/Users/hoquemi/Desktop/sm_eagle/client/hooks/use-local-cache.ts)

Change autosave from:
```ts
saveSession(messages, {}, documents)
```

To:
```ts
saveSession(currentSessionId, messages, {}, documents)
```

And ensure the save callback is rebuilt when `currentSessionId` changes, so the session ID is not stale in the debounced closure.

## 5.6 Apply the same protection to the legacy chat component
Primary file:
- [chat-interface.tsx](/Users/hoquemi/Desktop/sm_eagle/client/components/chat/chat-interface.tsx)

This component shows the same pattern:
- it reloads one `messages` array on session change
- it commits stream completion into that same array
- it autosaves using ambient current session state

Even if the simple chat is the main route, this path should not be left vulnerable if it is still accessible.

## 5.7 Add an explicit code comment about Phase 1 limitation
In both chat components and/or in `use-agent-stream.ts`, document:

- only one active request is supported at a time
- this phase prevents cross-thread corruption
- this does not preserve generation across thread switches

This prevents future engineers from assuming the code already supports background generation.

## 6. File-by-File Change List

## 6.1 `client/hooks/use-local-cache.ts`
Changes:
- update `saveSession` signature to take explicit `sessionId`
- replace internal reads of `currentSessionId` inside save path with the parameter
- update localStorage and IDB writes to use the passed `sessionId`
- ensure session list updates target the same explicit session

Validation:
- saving messages from session A while session B is selected should still write to session A only

## 6.2 `client/contexts/session-context.tsx`
Changes:
- update `SessionContextValue` type
- pass through new `saveSession(sessionId, ...)` signature

## 6.3 `client/components/chat-simple/simple-chat-interface.tsx`
Changes:
- capture `sessionIdAtSend`
- capture `requestId`
- guard callback handlers
- clear transient state on session switch
- update autosave to pass explicit `sessionId`
- prevent wrong-session document persistence

Validation:
- switching threads during a stream must not update the newly opened thread

## 6.4 `client/components/chat/chat-interface.tsx`
Changes:
- mirror the same session-explicit save behavior
- add the same stale callback protection

## 6.5 `client/hooks/use-agent-stream.ts`
Optional Phase 1 enhancement:
- add callback metadata with `sessionId` and `requestId`
- keep singleton behavior for now

This is optional if the component-side closure guard is sufficient, but adding metadata now will make Phase 2 easier.

## 7. Testing Plan

## 7.1 Unit tests
Targets:
- `use-local-cache.ts`
- `use-agent-stream.ts` if callback metadata is added

Test cases:
1. `saveSession(sessionA, ...)` writes only to session A even if `currentSessionId` later changes.
2. stale callback guard ignores events for a previous request after a thread switch.
3. switching sessions clears transient streaming UI state.

## 7.2 Playwright regression tests
Add or extend tests in `client/tests/`.

Required scenarios:
1. Start generating in thread A, switch to thread B before completion, assert thread B history remains unchanged.
2. Start generating in thread A, switch away, then return to A, assert no partial response leaked into B.
3. Start generating in A, then create a new thread, verify the new thread stays empty until explicitly used.

Important note:
- In Phase 1, the test should expect that the original generation does not continue correctly after switching if the request is no longer represented in the view. The goal here is data safety, not background continuity.

## 8. Rollout Strategy

1. Land persistence API changes first.
2. Land stale callback guards second.
3. Land thread-switch transient state cleanup third.
4. Add regression tests before merge if practical; at minimum in the same branch before release.

## 9. Risks

## 9.1 False sense of completeness
Risk:
- After Phase 1, the obvious corruption symptom is gone, but the product requirement is still unmet.

Mitigation:
- label this work clearly as stabilization only
- immediately follow with Phase 2

## 9.2 Hidden reachability of legacy chat
Risk:
- the advanced/legacy chat path may still be used internally and remain broken

Mitigation:
- patch both chat surfaces or remove one from the supported UI

## 9.3 Debounce-related edge cases
Risk:
- old autosave timers may still fire after a session change

Mitigation:
- ensure timeouts are cleared correctly in `useEffect` cleanup
- make saved session target explicit regardless

## 10. Acceptance Criteria

Phase 1 is complete when:

1. Switching from thread A to thread B no longer causes thread A content to appear in thread B.
2. Persisted history for thread B is not overwritten by late updates from thread A.
3. Session save paths no longer depend on ambient `currentSessionId`.
4. Regression tests cover the corruption scenario.
5. The codebase is documented as stabilized but not yet background-concurrent.

## 11. Recommended Follow-Up
Immediately proceed to Phase 2 to support the intended UX:

- thread A keeps generating in the background
- thread B can start its own generation
- `Esc` only stops the active thread after confirmation

That work is described in:
- `docs/plans/20260318-chat-thread-phase2-concurrent-generation-plan.md`
