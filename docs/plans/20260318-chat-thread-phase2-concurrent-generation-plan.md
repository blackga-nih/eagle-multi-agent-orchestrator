# 2026-03-18 Chat Thread Concurrent Generation Plan (Phase 2)

Date: 2026-03-18
Owner: EAGLE engineering
Status: Proposed
Audience: Frontend engineers implementing session-scoped chat runtime state
Scope: Full product-aligned support for background generation per thread and concurrent generation across threads

## 1. Purpose
This plan describes the architecture and implementation steps required to support the intended chat behavior:

1. A generation started in thread A continues even if the user switches to thread B.
2. The user can start a new generation in thread B while thread A is still generating.
3. Each stream updates only the thread that originated it.
4. `Esc` affects only the currently visible thread, and only after confirmation.

This is the real solution to the thread-switching bug. Phase 1 stabilizes corruption; Phase 2 delivers the correct UX model.

## 2. Product Behavior to Support

## 2.1 Thread behavior
- Switching threads does not cancel generation.
- The thread list should reflect that a background generation is in progress.
- Returning to a generating thread should show the current partial response and tool activity.

## 2.2 Concurrency behavior
- Multiple sessions may generate at the same time.
- Only one active generation per session is allowed for the initial implementation.
- A second send in the same session while that session is generating should be blocked with a clear user message or disabled input.

## 2.3 Stop behavior
- Pressing `Esc` in the active thread opens a confirm prompt if that thread is generating.
- Confirming stops only that thread's active request.
- `Esc` must not stop background threads.
- A visible stop button should exist in the active thread UI as well.

## 3. Why the Current Architecture Cannot Support This

Current blockers:

1. [use-agent-stream.ts](/Users/hoquemi/Desktop/sm_eagle/client/hooks/use-agent-stream.ts) is singleton-based.
   - one `AbortController`
   - one `isStreaming`
   - one set of callback channels

2. [simple-chat-interface.tsx](/Users/hoquemi/Desktop/sm_eagle/client/components/chat-simple/simple-chat-interface.tsx) stores transient stream state in a single component instance.
   - one `streamingMsg`
   - one `toolCallsByMsg`
   - one `agentStatus`

3. The selected thread is treated as the owner of runtime state, instead of the originating `sessionId`.

This means the code currently answers:
- "What is happening in the visible tab?"

But it needs to answer:
- "What is happening in each session, regardless of which one is visible?"

## 4. Target Architecture

## 4.1 Core principle
All runtime chat activity must be keyed by `sessionId`.

Persisted state and transient state must be separated:

- Persisted session state:
  - committed messages
  - committed documents
  - session metadata
  - stored in localStorage and IndexedDB

- Transient session runtime state:
  - in-flight streaming assistant text
  - pending tool calls
  - agent status
  - request IDs
  - abort controller references
  - runtime errors
  - held in memory only

## 4.2 New frontend layers
Recommended structure:

1. Session persistence layer
   - existing `useLocalCache`
   - explicit `sessionId` APIs

2. Chat runtime layer
   - new context or hook managing per-session active requests
   - owns transient state only

3. Stream transport layer
   - refactored `useAgentStream` or a new `chat-stream-manager`
   - owns network request lifecycle and SSE parsing

4. View layer
   - `SimpleChatInterface`
   - renders one selected session by combining persisted history with runtime overlay for that session

## 5. Proposed Data Model

## 5.1 Session runtime state
Create a new type, for example:

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
  startedAt?: string;
};
```

Runtime store:

```ts
type ChatRuntimeState = Record<string, SessionGenerationState>;
```

Key property:
- every active request is looked up by `sessionId`

## 5.2 Stream request registry
In the transport manager, maintain:

```ts
Map<string, {
  sessionId: string;
  requestId: string;
  abortController: AbortController;
}>
```

Keyed by `requestId`.

Also keep a reverse map:

```ts
Map<string, string>
```

Where:
- key = `sessionId`
- value = `requestId`

This enforces one active request per session while allowing many sessions concurrently.

## 6. New Responsibilities by Layer

## 6.1 Persistence layer
Primary file:
- [use-local-cache.ts](/Users/hoquemi/Desktop/sm_eagle/client/hooks/use-local-cache.ts)

Responsibilities:
- store committed messages by session
- store session metadata
- store committed documents by session
- expose explicit methods:
  - `saveSession(sessionId, ...)`
  - `writeMessageOptimistic(sessionId, message)`
  - `commitAssistantMessage(sessionId, message)`

This layer must not know or care which thread is visible.

## 6.2 Runtime layer
Suggested new file:
- `client/contexts/chat-runtime-context.tsx`
or
- `client/hooks/use-chat-runtime.ts`

Responsibilities:
- hold session-scoped in-memory stream state
- expose selectors:
  - `getSessionGenerationState(sessionId)`
  - `isSessionStreaming(sessionId)`
  - `getStreamingMessage(sessionId)`
- expose actions:
  - `startGeneration(sessionId, requestId, streamingMsgId)`
  - `appendChunk(sessionId, requestId, message)`
  - `upsertToolCall(sessionId, requestId, ...)`
  - `attachDocument(sessionId, requestId, ...)`
  - `completeGeneration(sessionId, requestId, finalMessage)`
  - `failGeneration(sessionId, requestId, error)`
  - `stopGeneration(sessionId)`

## 6.3 Transport layer
Recommended refactor target:
- [use-agent-stream.ts](/Users/hoquemi/Desktop/sm_eagle/client/hooks/use-agent-stream.ts)

Responsibilities:
- start fetch/SSE requests
- parse stream events
- route events to the runtime layer with `sessionId` and `requestId`
- keep an `AbortController` per request
- stop a request by `sessionId` or `requestId`

It should stop being a view-oriented hook with one `isStreaming`.

## 6.4 View layer
Primary files:
- [simple-chat-interface.tsx](/Users/hoquemi/Desktop/sm_eagle/client/components/chat-simple/simple-chat-interface.tsx)
- [sidebar-nav.tsx](/Users/hoquemi/Desktop/sm_eagle/client/components/layout/sidebar-nav.tsx)

Responsibilities:
- select which session to render
- read committed history from persistence
- read runtime overlay from session runtime
- display stop controls for the visible session
- show session badges/spinners in the sidebar

## 7. Detailed Implementation Plan

## Phase 2.1: Finish explicit persistence APIs
This is a dependency from Phase 1 and must be complete first.

Required outcomes:
- `saveSession` requires `sessionId`
- `writeMessageOptimistic` already requires `sessionId`
- any commit/finalize helpers also require `sessionId`

## Phase 2.2: Introduce a session-scoped runtime store
Create a new context/hook with:

- reducer-based state management
- per-session transient state
- pure actions

Suggested reducer actions:
```ts
type Action =
  | { type: 'generation/start'; sessionId: string; requestId: string; streamingMsgId: string }
  | { type: 'generation/message'; sessionId: string; requestId: string; message: ChatMessage }
  | { type: 'generation/status'; sessionId: string; requestId: string; status: string }
  | { type: 'generation/toolUse'; sessionId: string; requestId: string; payload: ... }
  | { type: 'generation/toolResult'; sessionId: string; requestId: string; payload: ... }
  | { type: 'generation/document'; sessionId: string; requestId: string; document: DocumentInfo }
  | { type: 'generation/complete'; sessionId: string; requestId: string; finalMessage?: ChatMessage }
  | { type: 'generation/error'; sessionId: string; requestId: string; error: string }
  | { type: 'generation/stopping'; sessionId: string; requestId: string }
  | { type: 'generation/resetTransient'; sessionId: string };
```

Reducer rules:
- if an action's `requestId` does not match the session's active request, ignore it
- this prevents stale events from older requests from mutating current runtime state

## Phase 2.3: Refactor stream transport into a multi-request manager
Refactor [use-agent-stream.ts](/Users/hoquemi/Desktop/sm_eagle/client/hooks/use-agent-stream.ts) or replace it with a new manager.

Recommended API:
```ts
startQuery({
  sessionId,
  query,
  packageId,
}): Promise<{ requestId: string }>

stopQuery(sessionId: string): void

isSessionStreaming(sessionId: string): boolean
```

Internal behavior:
- create a new `AbortController` per request
- reject starting a second request in the same session if one is already active
- allow requests in other sessions
- propagate parsed events with `sessionId` and `requestId`

Important implementation note:
- do not let the manager call React component state setters directly
- the manager should dispatch actions into the runtime store

## Phase 2.4: Move transient stream state out of `SimpleChatInterface`
Primary file:
- [simple-chat-interface.tsx](/Users/hoquemi/Desktop/sm_eagle/client/components/chat-simple/simple-chat-interface.tsx)

Remove or minimize local ownership of:
- `streamingMsg`
- `streamingMsgRef`
- `toolCallsByMsg`
- `agentStatus`

Replace with selectors:
```ts
const sessionRuntime = useChatRuntime(currentSessionId);
const streamingMsg = sessionRuntime.streamingMessage;
const toolCallsByMsg = sessionRuntime.toolCallsByMsg;
const agentStatus = sessionRuntime.agentStatus;
const isStreaming = sessionRuntime.status === 'streaming';
```

The component should become:
- one renderer
- one sender
- not the owner of long-lived cross-thread runtime state

## Phase 2.5: Commit completed responses into persisted session history
When the runtime store receives `generation/complete`:

1. read the final in-flight message for that session
2. write it into persisted messages for the same session
3. move any temporary stream-keyed docs/tool state to the committed assistant message ID
4. clear transient state for that session only

This should happen in a session-scoped finalize path, not in the visible component.

Recommended abstraction:
- `finalizeSessionGeneration(sessionId, requestId)`

This function can:
- commit assistant message
- reconcile document attachments
- reconcile tool calls
- optionally generate title if it is the first response in that session

## Phase 2.6: Add per-session sidebar indicators
Primary file:
- [sidebar-nav.tsx](/Users/hoquemi/Desktop/sm_eagle/client/components/layout/sidebar-nav.tsx)

For each session row:
- if `isSessionStreaming(session.id)` show spinner or "Generating"
- do not switch away from that session's data ownership

This improves usability and makes background activity visible.

## Phase 2.7: Add stop-generation controls
Primary files:
- [simple-chat-interface.tsx](/Users/hoquemi/Desktop/sm_eagle/client/components/chat-simple/simple-chat-interface.tsx)
- new confirm modal if needed

User interactions:
- stop button in the active thread input/footer area
- `Esc` key handler scoped to the visible thread

Behavior:
1. If current session is not streaming, `Esc` does nothing.
2. If current session is streaming, open confirm modal:
   - "Stop generating in this thread?"
3. On confirm:
   - call `stopQuery(currentSessionId)`
   - mark that session as `stopping`
4. Background sessions continue untouched.

## Phase 2.8: Same-session resend policy
Initial recommended policy:
- disable input send while the current session is already streaming
- show helper text: "Wait for this response to finish or stop it first"

Reason:
- allowing multiple overlapping requests within one session complicates message ordering and tool result routing significantly

This keeps Phase 2 bounded while fully supporting cross-session concurrency.

## 8. File-by-File Plan

## 8.1 New runtime state module
Add one of:
- `client/contexts/chat-runtime-context.tsx`
- `client/hooks/use-chat-runtime.ts`

Contents:
- runtime types
- reducer
- provider
- selectors
- action creators

## 8.2 `client/hooks/use-agent-stream.ts`
Refactor to:
- support multiple requests
- remove global singleton semantics
- expose per-session start/stop APIs
- emit normalized events to runtime store

Potential rename:
- `client/lib/chat-stream-manager.ts`

This may be cleaner than overloading the existing hook.

## 8.3 `client/components/chat-simple/simple-chat-interface.tsx`
Refactor to:
- read session runtime via selectors
- send user messages to persistence immediately
- start query for the current session only
- display persisted + transient state for the selected session
- wire stop button and `Esc` handling

## 8.4 `client/components/layout/sidebar-nav.tsx`
Enhance to:
- read per-session active generation status
- show background activity on thread rows

## 8.5 `client/components/chat/chat-interface.tsx`
Either:
- migrate to the same runtime store
or
- remove/deprecate if unsupported

Recommendation:
- migrate if still reachable
- otherwise document and disable the path

## 9. Testing Plan

## 9.1 Unit tests for runtime reducer
Required scenarios:
1. `generation/start` creates runtime state for session A only.
2. `generation/message` for stale `requestId` is ignored.
3. `generation/complete` clears transient state only for the matching session.
4. `stopQuery(sessionA)` affects session A but not session B.

## 9.2 Unit tests for stream manager
Required scenarios:
1. starting request B does not abort request A
2. starting a second request in A is blocked
3. `stopQuery(A)` aborts only A's controller
4. callbacks are tagged with correct `sessionId` and `requestId`

## 9.3 Playwright tests
Required end-to-end scenarios:
1. Start generation in A, switch to B, verify B remains unchanged.
2. While A is streaming, send message in B, verify both sessions show independent progress.
3. Return to A after some delay, verify A accumulated more output while in background.
4. Press `Esc` in B while B is streaming, confirm stop, verify A continues if A is also streaming.
5. Press `Esc` when only A is streaming in background and B is visible, verify nothing happens.
6. Attempt second send in the same session while streaming, verify send is blocked.

## 10. Rollout Plan

## 10.1 Suggested implementation order
1. Finish Phase 1 stabilization work.
2. Introduce runtime store with no UI behavior change yet.
3. Refactor transport layer to multi-request support.
4. Migrate `SimpleChatInterface` to runtime selectors.
5. Add sidebar generation indicators.
6. Add stop button and `Esc` confirm modal.
7. Add final regression coverage.

## 10.2 PR strategy
Recommended split:

PR 1:
- runtime types and provider
- explicit persistence APIs if not already done

PR 2:
- multi-request stream manager
- simple chat migration

PR 3:
- stop controls
- sidebar indicators
- tests and cleanup

This reduces blast radius and makes regressions easier to localize.

## 11. Risks and Mitigations

## 11.1 Over-refactoring `use-agent-stream`
Risk:
- the current hook mixes transport, logging, and view callbacks

Mitigation:
- consider extracting a new `chat-stream-manager` instead of forcing the old hook to serve two incompatible models

## 11.2 Runtime/persistence duplication
Risk:
- messages may exist partly in runtime and partly in storage in confusing ways

Mitigation:
- define a strict rule:
  - runtime store owns transient in-flight state
  - persistence layer owns committed history only

## 11.3 Tool/document reconciliation complexity
Risk:
- tool calls and document cards currently key off temporary stream IDs

Mitigation:
- keep one stable temporary stream ID per request
- on completion, reconcile temp IDs into committed assistant message ID for that same session only

## 11.4 Background work visibility
Risk:
- users may forget thread A is still running

Mitigation:
- add sidebar indicators early in the rollout

## 12. Acceptance Criteria

Phase 2 is complete when:

1. Thread A can continue generating after the user switches to thread B.
2. Thread B can start its own generation while A is still generating.
3. Stream events are routed only to their originating session.
4. No thread history is overwritten by another session's output.
5. Each session allows at most one active generation.
6. `Esc` only offers to stop the currently visible thread.
7. Confirming stop aborts only that thread's request.
8. Regression tests cover cross-thread concurrent generation behavior.

## 13. Recommendation
Do not try to satisfy Phase 2 by layering more guards on the current singleton implementation.

The product behavior requires:
- per-session runtime ownership
- per-request abort controllers
- a transport layer that supports concurrency explicitly

That is a moderate frontend refactor, but it is the correct boundary and should make future chat behavior more predictable and testable.
