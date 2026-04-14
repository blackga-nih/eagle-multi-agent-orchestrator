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
        updated = [...existing, sc];
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
      // transitions, auth refresh). Dedupe by natural key so repeated restores
      // don't accumulate duplicate tool cards / state entries.
      const mergedTools: ToolCallsByMessageId = { ...session.toolCallsByMsg };
      for (const [msgId, calls] of Object.entries(action.toolCallsByMsg)) {
        const existing = mergedTools[msgId] ?? [];
        const seen = new Set<string>(existing.map((tc) => tc.toolUseId));
        const additions: TrackedToolCall[] = [];
        for (const tc of calls) {
          if (seen.has(tc.toolUseId)) continue;
          seen.add(tc.toolUseId);
          additions.push(tc);
        }
        mergedTools[msgId] = additions.length ? [...existing, ...additions] : existing;
      }
      const mergedStateChanges: Record<string, StateChangeEntry[]> = {
        ...session.stateChangesByMsg,
      };
      for (const [msgId, entries] of Object.entries(action.stateChangesByMsg)) {
        const existing = mergedStateChanges[msgId] ?? [];
        const seen = new Set<string>(
          existing.map((e) => `${e.stateType}:${e.timestamp}:${e.packageId ?? ''}`),
        );
        const additions: StateChangeEntry[] = [];
        for (const e of entries) {
          const key = `${e.stateType}:${e.timestamp}:${e.packageId ?? ''}`;
          if (seen.has(key)) continue;
          seen.add(key);
          additions.push(e);
        }
        mergedStateChanges[msgId] = additions.length ? [...existing, ...additions] : existing;
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
