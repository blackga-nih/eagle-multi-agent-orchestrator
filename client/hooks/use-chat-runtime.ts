'use client';

import { useMemo } from 'react';
import { useChatRuntimeContext, SessionGenerationState } from '@/contexts/chat-runtime-context';

const IDLE_STATE: SessionGenerationState = {
    sessionId: '',
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

export interface ChatRuntimeView extends SessionGenerationState {
    isStreaming: boolean;
    isIdle: boolean;
}

/**
 * Selector hook — read the generation state for a single session.
 * Returns a stable idle object when no generation has ever started for this session.
 */
export function useChatRuntime(sessionId: string): ChatRuntimeView {
    const { state } = useChatRuntimeContext();
    const session = state[sessionId] ?? IDLE_STATE;

    return useMemo(
        () => ({
            ...session,
            isStreaming: session.status === 'streaming' || session.status === 'stopping',
            isIdle: session.status === 'idle',
        }),
        [session],
    );
}
