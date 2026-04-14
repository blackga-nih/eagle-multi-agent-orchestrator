'use client';

import { createContext, useContext, useReducer, useMemo, ReactNode, Dispatch } from 'react';
import { ChatMessage, DocumentInfo } from '@/types/chat';
import {
  TrackedToolCall,
  ToolCallsByMessageId,
} from '@/components/chat-simple/simple-chat-interface';

// ---------------------------------------------------------------------------
// State change entries (package state updates rendered inline in chat)
// ---------------------------------------------------------------------------

export interface StateChangeEntry {
  stateType: string;
  packageId?: string;
  phase?: string;
  title?: string;
  acquisitionMethod?: string;
  contractType?: string;
  contractVehicle?: string;
  checklist?: { required: string[]; completed: string[] };
  progressPct?: number;
  textSnapshotLength: number;
  timestamp: number;
  // Sources transparency fields (sources_read / sources_summary events)
  sourceTitle?: string;
  sourceS3Key?: string;
  sourceDocType?: string;
  sourceCharsRead?: number;
  sourceTool?: string;
  // sources_summary aggregate fields
  searchCount?: number;
  fetchCount?: number;
  totalCharsRead?: number;
  fetchedKeys?: string[];
}

// ---------------------------------------------------------------------------
// Per-session generation state
// ---------------------------------------------------------------------------

export interface SessionGenerationState {
  sessionId: string;
  activeRequestId: string | null;
  status: 'idle' | 'streaming' | 'stopping' | 'error';
  streamingMessage: ChatMessage | null;
  streamingMessageId: string | null;
  toolCallsByMsg: ToolCallsByMessageId;
  documentsByMsg: Record<string, DocumentInfo[]>;
  stateChangesByMsg: Record<string, StateChangeEntry[]>;
  agentStatus: string | null;
  error: string | null;
  /** Set once on generation/complete — the final committed message.
   *  Read by the component to commit the message + trigger title generation. */
  completedMessage: ChatMessage | null;
}

export type ChatRuntimeState = Record<string, SessionGenerationState>;

const IDLE_SESSION: Omit<SessionGenerationState, 'sessionId'> = {
  activeRequestId: null,
  status: 'idle',
  streamingMessage: null,
  streamingMessageId: null,
  toolCallsByMsg: {},
  documentsByMsg: {},
  stateChangesByMsg: {},
  agentStatus: null,
  error: null,
  completedMessage: null,
};

function makeIdle(sessionId: string): SessionGenerationState {
  return { ...IDLE_SESSION, sessionId };
}

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

export type ChatRuntimeAction =
  | { type: 'generation/start'; sessionId: string; requestId: string; streamingMsgId: string }
  | { type: 'generation/message'; sessionId: string; requestId: string; message: ChatMessage }
  | { type: 'generation/status'; sessionId: string; requestId: string; status: string }
  | {
      type: 'generation/toolUse';
      sessionId: string;
      requestId: string;
      msgId: string;
      toolUseId: string;
      patch: Partial<TrackedToolCall>;
    }
  | {
      type: 'generation/toolResult';
      sessionId: string;
      requestId: string;
      msgId: string;
      toolName: string;
      toolUseId?: string;
      result: unknown;
    }
  | {
      type: 'generation/toolInputDelta';
      sessionId: string;
      requestId: string;
      msgId: string;
      toolUseId: string;
      delta: string;
    }
  | {
      type: 'generation/document';
      sessionId: string;
      requestId: string;
      msgId: string;
      document: DocumentInfo;
    }
  | {
      type: 'generation/stateChange';
      sessionId: string;
      requestId: string;
      msgId: string;
      stateChange: StateChangeEntry;
    }
  | {
      type: 'generation/complete';
      sessionId: string;
      requestId: string;
      finalMessage?: ChatMessage;
    }
  | { type: 'generation/error'; sessionId: string; requestId: string; error: string }
  | { type: 'generation/stopping'; sessionId: string }
  | { type: 'generation/reset'; sessionId: string }
  | {
      type: 'generation/restore';
      sessionId: string;
      toolCallsByMsg: ToolCallsByMessageId;
      stateChangesByMsg: Record<string, StateChangeEntry[]>;
      documentsByMsg: Record<string, DocumentInfo[]>;
    };

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Force any non-terminal tool call to the given terminal status.
 *  Prevents "Writing..." indicators from persisting after stream ends. */
function sweepStuckTools(
  toolCallsByMsg: ToolCallsByMessageId,
  terminalStatus: 'done' | 'error',
): ToolCallsByMessageId {
  let changed = false;
  const swept: ToolCallsByMessageId = {};
  for (const [msgId, calls] of Object.entries(toolCallsByMsg)) {
    const hasStuck = calls.some((tc) => tc.status !== 'done' && tc.status !== 'error');
    if (hasStuck) {
      changed = true;
      swept[msgId] = calls.map((tc) =>
        tc.status !== 'done' && tc.status !== 'error'
          ? { ...tc, status: terminalStatus, streamingInput: undefined }
          : tc,
      );
    } else {
      swept[msgId] = calls;
    }
  }
  return changed ? swept : toolCallsByMsg;
}

function dedupeDocuments(docs: DocumentInfo[]): DocumentInfo[] {
  const seen = new Set<string>();
  const unique: DocumentInfo[] = [];
  for (const doc of docs) {
    const key = doc.s3_key ?? doc.document_id ?? `${doc.document_type}:${doc.title}`;
    if (seen.has(key)) continue;
    seen.add(key);
    unique.push(doc);
  }
  return unique;
}

function toolCallIdentity(call: TrackedToolCall): string {
  if (call.toolUseId) return `id:${call.toolUseId}`;
  return `fallback:${call.toolName}:${call.textSnapshotLength ?? -1}:${JSON.stringify(call.input ?? {})}`;
}

function toolStatusRank(status: TrackedToolCall['status']): number {
  switch (status) {
    case 'done':
      return 4;
    case 'error':
      return 3;
    case 'interrupted':
      return 2;
    case 'running':
      return 1;
    default:
      return 0;
  }
}

function mergeToolCall(existing: TrackedToolCall, incoming: TrackedToolCall): TrackedToolCall {
  const existingRank = toolStatusRank(existing.status);
  const incomingRank = toolStatusRank(incoming.status);
  const preferred = incomingRank > existingRank ? incoming : existing;
  const fallback = preferred === incoming ? existing : incoming;

  return {
    ...fallback,
    ...preferred,
    input: Object.keys(preferred.input ?? {}).length > 0 ? preferred.input : fallback.input,
    result: preferred.result ?? fallback.result,
    streamingInput:
      (preferred.streamingInput?.length ?? 0) >= (fallback.streamingInput?.length ?? 0)
        ? preferred.streamingInput
        : fallback.streamingInput,
    textSnapshotLength: preferred.textSnapshotLength ?? fallback.textSnapshotLength,
  };
}

function dedupeToolCalls(calls: TrackedToolCall[]): TrackedToolCall[] {
  const byId = new Map<string, TrackedToolCall>();
  for (const call of calls) {
    const key = toolCallIdentity(call);
    const existing = byId.get(key);
    byId.set(key, existing ? mergeToolCall(existing, call) : call);
  }
  return Array.from(byId.values()).sort(
    (a, b) => (a.textSnapshotLength ?? 0) - (b.textSnapshotLength ?? 0),
  );
}

function stateChangeIdentity(entry: StateChangeEntry): string {
  if (entry.stateType === 'checklist_update') {
    return `checklist:${entry.packageId ?? ''}`;
  }
  if (entry.stateType === 'sources_summary') {
    return `sources_summary:${entry.textSnapshotLength}:${entry.fetchCount ?? 0}:${
      entry.searchCount ?? 0
    }:${entry.totalCharsRead ?? 0}:${(entry.fetchedKeys ?? []).join('|')}`;
  }
  if (entry.stateType === 'sources_read') {
    return `sources_read:${entry.textSnapshotLength}:${entry.sourceS3Key ?? ''}:${
      entry.sourceTitle ?? ''
    }:${entry.sourceCharsRead ?? 0}`;
  }
  return `${entry.stateType}:${entry.timestamp}:${entry.packageId ?? ''}:${entry.title ?? ''}`;
}

function dedupeStateChanges(entries: StateChangeEntry[]): StateChangeEntry[] {
  const byId = new Map<string, StateChangeEntry>();
  for (const entry of entries) {
    byId.set(stateChangeIdentity(entry), entry);
  }
  return Array.from(byId.values()).sort((a, b) => a.timestamp - b.timestamp);
}

// ---------------------------------------------------------------------------
// Reducer
// ---------------------------------------------------------------------------

function chatRuntimeReducer(state: ChatRuntimeState, action: ChatRuntimeAction): ChatRuntimeState {
  const sessionId = action.sessionId;
  const session = state[sessionId] ?? makeIdle(sessionId);

  // Stale-request guard: every action with a requestId must match the active one.
  if ('requestId' in action && action.requestId !== session.activeRequestId) {
    // Exception: generation/start always wins (it sets the new requestId).
    if (action.type !== 'generation/start') return state;
  }

  switch (action.type) {
    case 'generation/start':
      return {
        ...state,
        [sessionId]: {
          ...makeIdle(sessionId),
          // Preserve historical tool calls, documents, and state changes from previous requests
          toolCallsByMsg: session.toolCallsByMsg,
          documentsByMsg: session.documentsByMsg,
          stateChangesByMsg: session.stateChangesByMsg,
          activeRequestId: action.requestId,
          status: 'streaming',
          streamingMessageId: action.streamingMsgId,
        },
      };

    case 'generation/message':
      return {
        ...state,
        [sessionId]: {
          ...session,
          streamingMessage: action.message,
        },
      };

    case 'generation/status':
      return {
        ...state,
        [sessionId]: {
          ...session,
          agentStatus: action.status || null,
        },
      };

    case 'generation/toolUse': {
      const calls = session.toolCallsByMsg[action.msgId] ?? [];
      const idx = calls.findIndex((t) => t.toolUseId === action.toolUseId);
      let updated: TrackedToolCall[];
      if (idx === -1) {
        updated = [
          ...calls,
          {
            toolUseId: action.toolUseId,
            toolName: action.patch.toolName ?? '',
            input: action.patch.input ?? {},
            status: action.patch.status ?? 'pending',
            isClientSide: action.patch.isClientSide ?? false,
            result: action.patch.result,
            textSnapshotLength: action.patch.textSnapshotLength,
          },
        ];
      } else {
        updated = calls.slice();
        updated[idx] = { ...updated[idx], ...action.patch };
      }
      return {
        ...state,
        [sessionId]: {
          ...session,
          toolCallsByMsg: { ...session.toolCallsByMsg, [action.msgId]: updated },
        },
      };
    }

    case 'generation/toolResult': {
      const calls = session.toolCallsByMsg[action.msgId] ?? [];
      // Prefer exact match by toolUseId, fall back to name-based matching
      let idx = action.toolUseId
        ? calls.findIndex((tc) => tc.toolUseId === action.toolUseId)
        : -1;
      if (idx === -1) {
        idx = calls.findIndex((tc) => tc.toolName === action.toolName && tc.status !== 'done');
      }
      if (idx === -1) return state;
      const updated = calls.slice();
      updated[idx] = {
        ...updated[idx],
        status: 'done',
        result: action.result as TrackedToolCall['result'],
        streamingInput: undefined,
      };
      return {
        ...state,
        [sessionId]: {
          ...session,
          toolCallsByMsg: { ...session.toolCallsByMsg, [action.msgId]: updated },
        },
      };
    }

    case 'generation/toolInputDelta': {
      const calls = session.toolCallsByMsg[action.msgId] ?? [];
      const idx = calls.findIndex((tc) => tc.toolUseId === action.toolUseId);
      if (idx === -1) return state;
      const updated = calls.slice();
      const existing = updated[idx];
      updated[idx] = {
        ...existing,
        status: 'running',
        streamingInput: (existing.streamingInput ?? '') + action.delta,
      };
      return {
        ...state,
        [sessionId]: {
          ...session,
          toolCallsByMsg: { ...session.toolCallsByMsg, [action.msgId]: updated },
        },
      };
    }

    case 'generation/document': {
      const existingDocs = session.documentsByMsg[action.msgId] ?? [];
      const merged = dedupeDocuments([...existingDocs, action.document]);
      return {
        ...state,
        [sessionId]: {
          ...session,
          documentsByMsg: { ...session.documentsByMsg, [action.msgId]: merged },
        },
      };
    }

    case 'generation/stateChange': {
      const existing = session.stateChangesByMsg[action.msgId] ?? [];
      const sc = action.stateChange;
      let updated: StateChangeEntry[];
      if (sc.stateType === 'checklist_update') {
        // Dedup: replace the last checklist_update for the same packageId
        const idx = existing.findLastIndex(
          (e) => e.stateType === 'checklist_update' && e.packageId === sc.packageId,
        );
        if (idx >= 0) {
          updated = [...existing];
          updated[idx] = sc;
        } else {
          updated = [...existing, sc];
        }
      } else {
        updated = dedupeStateChanges([...existing, sc]);
      }
      return {
        ...state,
        [sessionId]: {
          ...session,
          stateChangesByMsg: {
            ...session.stateChangesByMsg,
            [action.msgId]: updated,
          },
        },
      };
    }

    case 'generation/complete': {
      // Sweep stuck tools: force any tool not in a terminal state to 'done'
      // so "Writing..." indicators don't persist after the stream ends.
      const completedTools = sweepStuckTools(session.toolCallsByMsg, 'done');
      return {
        ...state,
        [sessionId]: {
          ...session,
          status: 'idle',
          activeRequestId: null,
          streamingMessage: null,
          agentStatus: null,
          completedMessage: action.finalMessage ?? session.streamingMessage ?? null,
          toolCallsByMsg: completedTools,
        },
      };
    }

    case 'generation/error': {
      const errorTools = sweepStuckTools(session.toolCallsByMsg, 'error');
      return {
        ...state,
        [sessionId]: {
          ...session,
          status: 'error',
          error: action.error,
          streamingMessage: null,
          agentStatus: null,
          toolCallsByMsg: errorTools,
        },
      };
    }

    case 'generation/stopping':
      return {
        ...state,
        [sessionId]: {
          ...session,
          status: 'stopping',
        },
      };

    case 'generation/reset':
      return {
        ...state,
        [sessionId]: makeIdle(sessionId),
      };

    case 'generation/restore': {
      // Bulk-load persisted tool calls, state changes, and documents
      // without changing session status (stays idle). Bypasses stale-request
      // guard since it has no requestId.
      //
      // Must be idempotent: React StrictMode double-fires effects in dev, and
      // the session-load effect can run more than once per mount (route
      // transitions, auth refresh). Use the reducer-level dedupe helpers so
      // repeated restores do not accumulate duplicate tool cards or state
      // entries, including fallback cases where toolUseId may be absent.
      const mergedTools: ToolCallsByMessageId = { ...session.toolCallsByMsg };
      for (const [msgId, calls] of Object.entries(action.toolCallsByMsg)) {
        mergedTools[msgId] = dedupeToolCalls([...(mergedTools[msgId] ?? []), ...calls]);
      }
      const mergedStateChanges: Record<string, StateChangeEntry[]> = {
        ...session.stateChangesByMsg,
      };
      for (const [msgId, entries] of Object.entries(action.stateChangesByMsg)) {
        mergedStateChanges[msgId] = dedupeStateChanges([
          ...(mergedStateChanges[msgId] ?? []),
          ...entries,
        ]);
      }
      const mergedDocs: Record<string, DocumentInfo[]> = { ...session.documentsByMsg };
      for (const [msgId, docs] of Object.entries(action.documentsByMsg)) {
        mergedDocs[msgId] = dedupeDocuments([...(mergedDocs[msgId] ?? []), ...docs]);
      }
      return {
        ...state,
        [sessionId]: {
          ...session,
          toolCallsByMsg: mergedTools,
          stateChangesByMsg: mergedStateChanges,
          documentsByMsg: mergedDocs,
        },
      };
    }

    default:
      return state;
  }
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

interface ChatRuntimeContextValue {
  state: ChatRuntimeState;
  dispatch: Dispatch<ChatRuntimeAction>;
}

const ChatRuntimeContext = createContext<ChatRuntimeContextValue | null>(null);

export function ChatRuntimeProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(chatRuntimeReducer, {} as ChatRuntimeState);
  const value = useMemo(() => ({ state, dispatch }), [state, dispatch]);

  return <ChatRuntimeContext.Provider value={value}>{children}</ChatRuntimeContext.Provider>;
}

export function useChatRuntimeContext() {
  const ctx = useContext(ChatRuntimeContext);
  if (!ctx) {
    throw new Error('useChatRuntimeContext must be used within a ChatRuntimeProvider');
  }
  return ctx;
}
