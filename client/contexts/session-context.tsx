'use client';

import { createContext, useContext, ReactNode } from 'react';
import { useSessionPersistence } from '@/hooks/use-session-persistence';
import { Message, AcquisitionData } from '@/components/chat/chat-interface';
import { ChatSession } from '@/components/layout/chat-history-dropdown';
import { DocumentInfo } from '@/types/chat';

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
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
    const sessionPersistence = useSessionPersistence();

    return (
        <SessionContext.Provider value={sessionPersistence}>
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
