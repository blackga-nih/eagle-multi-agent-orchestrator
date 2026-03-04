'use client';

import { createContext, useContext, ReactNode } from 'react';
import { useLocalCache } from '@/hooks/use-local-cache';
import { useAuth } from '@/contexts/auth-context';
import { Message, AcquisitionData } from '@/components/chat/chat-interface';
import { ChatSession } from '@/components/layout/chat-history-dropdown';
import { ChatMessage, DocumentInfo } from '@/types/chat';

interface SessionContextValue {
    sessions: ChatSession[];
    currentSessionId: string;
    isLoading: boolean;
    saveSession: (messages: Message[], acquisitionData: AcquisitionData, documents?: Record<string, DocumentInfo[]>) => void;
    loadSession: (sessionId: string) => {
        id: string;
        title: string;
        summary?: string;
        messages: Message[];
        acquisitionData: AcquisitionData;
        documents?: Record<string, DocumentInfo[]>;
        createdAt: string;
        updatedAt: string;
        status: 'in_progress' | 'completed' | 'draft';
    } | null;
    createNewSession: () => string;
    deleteSession: (sessionId: string) => void;
    setCurrentSession: (sessionId: string) => void;
    markSessionComplete: (sessionId: string) => void;
    renameSession: (sessionId: string, newTitle: string) => void;
    /** Optimistic write: persists message to IndexedDB immediately, fire-and-forget. */
    writeMessageOptimistic: (sessionId: string, message: ChatMessage) => void;
    /** Fetch from backend and populate IDB if empty or stale (>5 min). */
    hydrateFromBackend: (sessionId: string) => Promise<void>;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
    const { user } = useAuth();

    // Use stable fallback identifiers while auth is loading so the hook
    // initialises immediately (no-op DB writes until real IDs arrive).
    const userId = user?.userId ?? 'anon';
    const tenantId = user?.tenantId ?? 'default';

    const cache = useLocalCache(userId, tenantId);

    return (
        <SessionContext.Provider value={cache}>
            {children}
        </SessionContext.Provider>
    );
}

export function useSession() {
    const context = useContext(SessionContext);
    if (!context) {
        throw new Error('useSession must be used within a SessionProvider');
    }
    return context;
}
