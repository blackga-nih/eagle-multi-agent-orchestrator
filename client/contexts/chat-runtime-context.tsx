'use client';

import { createContext, useContext, useReducer, ReactNode, Dispatch } from 'react';
import { ChatMessage, DocumentInfo } from '@/types/chat';
import { TrackedToolCall, ToolCallsByMessageId } from '@/components/chat-simple/simple-chat-interface';

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
    agentStatus: string | null;
    error: string | null;
}

export type ChatRuntimeState = Record<string, SessionGenerationState>;

const IDLE_SESSION: Omit<SessionGenerationState, 'sessionId'> = {
    activeRequestId: null,
    status: 'idle',
    streamingMessage: null,
    streamingMessageId: null,
    toolCallsByMsg: {},
    documentsByMsg: {},
    agentStatus: null,
    error: null,
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
    | { type: 'generation/toolUse'; sessionId: string; requestId: string; msgId: string; toolUseId: string; patch: Partial<TrackedToolCall> }
    | { type: 'generation/toolResult'; sessionId: string; requestId: string; msgId: string; toolName: string; result: unknown }
    | { type: 'generation/document'; sessionId: string; requestId: string; msgId: string; document: DocumentInfo }
    | { type: 'generation/complete'; sessionId: string; requestId: string; finalMessage?: ChatMessage }
    | { type: 'generation/error'; sessionId: string; requestId: string; error: string }
    | { type: 'generation/stopping'; sessionId: string }
    | { type: 'generation/reset'; sessionId: string };

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

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
                    // Preserve historical tool calls and documents from previous requests
                    toolCallsByMsg: session.toolCallsByMsg,
                    documentsByMsg: session.documentsByMsg,
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
            const idx = calls.findIndex((tc) => tc.toolName === action.toolName && tc.status !== 'done');
            if (idx === -1) return state;
            const updated = calls.slice();
            updated[idx] = { ...updated[idx], status: 'done', result: action.result as TrackedToolCall['result'] };
            return {
                ...state,
                [sessionId]: {
                    ...session,
                    toolCallsByMsg: { ...session.toolCallsByMsg, [action.msgId]: updated },
                },
            };
        }

        case 'generation/document': {
            const existing = session.documentsByMsg[action.msgId] ?? [];
            const merged = dedupeDocuments([...existing, action.document]);
            return {
                ...state,
                [sessionId]: {
                    ...session,
                    documentsByMsg: { ...session.documentsByMsg, [action.msgId]: merged },
                },
            };
        }

        case 'generation/complete':
            return {
                ...state,
                [sessionId]: {
                    ...session,
                    status: 'idle',
                    activeRequestId: null,
                    streamingMessage: null,
                    agentStatus: null,
                },
            };

        case 'generation/error':
            return {
                ...state,
                [sessionId]: {
                    ...session,
                    status: 'error',
                    error: action.error,
                    streamingMessage: null,
                    agentStatus: null,
                },
            };

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

    return (
        <ChatRuntimeContext.Provider value={{ state, dispatch }}>
            {children}
        </ChatRuntimeContext.Provider>
    );
}

export function useChatRuntimeContext() {
    const ctx = useContext(ChatRuntimeContext);
    if (!ctx) {
        throw new Error('useChatRuntimeContext must be used within a ChatRuntimeProvider');
    }
    return ctx;
}
