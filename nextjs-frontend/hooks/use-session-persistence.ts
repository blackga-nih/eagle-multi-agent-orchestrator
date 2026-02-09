'use client';

import { useState, useEffect, useCallback } from 'react';
import { Message, AcquisitionData } from '@/components/chat/chat-interface';
import { ChatSession } from '@/components/layout/chat-history-dropdown';
import { generateUUID } from '@/lib/uuid';

const STORAGE_KEY = 'eagle_chat_sessions';
const CURRENT_SESSION_KEY = 'eagle_current_session';

interface SessionData {
    id: string;
    title: string;
    summary?: string;
    messages: Message[];
    acquisitionData: AcquisitionData;
    createdAt: string;
    updatedAt: string;
    status: 'in_progress' | 'completed' | 'draft';
}

interface UseSessionPersistenceReturn {
    sessions: ChatSession[];
    currentSessionId: string;
    currentSession: SessionData | null;
    isLoading: boolean;
    saveSession: (messages: Message[], acquisitionData: AcquisitionData) => void;
    loadSession: (sessionId: string) => SessionData | null;
    createNewSession: () => string;
    deleteSession: (sessionId: string) => void;
    setCurrentSession: (sessionId: string) => void;
    markSessionComplete: (sessionId: string) => void;
}

function generateSessionTitle(messages: Message[], acquisitionData: AcquisitionData): string {
    // Try to extract a meaningful title from the first user message or acquisition data
    if (acquisitionData.requirement) {
        const words = acquisitionData.requirement.split(' ').slice(0, 5).join(' ');
        return words + (acquisitionData.requirement.length > words.length ? '...' : '');
    }

    const firstUserMessage = messages.find((m) => m.role === 'user');
    if (firstUserMessage) {
        const words = firstUserMessage.content.split(' ').slice(0, 5).join(' ');
        return words + (firstUserMessage.content.length > words.length ? '...' : '');
    }

    return `Session ${new Date().toLocaleDateString()}`;
}

function generateSessionSummary(acquisitionData: AcquisitionData): string | undefined {
    const parts = [];

    if (acquisitionData.acquisitionType) {
        parts.push(acquisitionData.acquisitionType);
    }
    if (acquisitionData.estimatedValue) {
        parts.push(acquisitionData.estimatedValue);
    }
    if (acquisitionData.equipmentType) {
        parts.push(acquisitionData.equipmentType);
    }

    return parts.length > 0 ? parts.join(' • ') : undefined;
}

export function useSessionPersistence(): UseSessionPersistenceReturn {
    const [sessions, setSessions] = useState<ChatSession[]>([]);
    const [currentSessionId, setCurrentSessionId] = useState<string>('');
    const [isLoading, setIsLoading] = useState(true);

    // Load sessions from localStorage on mount
    useEffect(() => {
        try {
            const stored = localStorage.getItem(STORAGE_KEY);
            if (stored) {
                const data: Record<string, SessionData> = JSON.parse(stored);
                const sessionList: ChatSession[] = Object.values(data).map((session) => ({
                    id: session.id,
                    title: session.title,
                    summary: session.summary,
                    createdAt: new Date(session.createdAt),
                    updatedAt: new Date(session.updatedAt),
                    status: session.status,
                    messageCount: session.messages.length,
                }));
                setSessions(sessionList);
            }

            // Load current session ID
            const currentId = localStorage.getItem(CURRENT_SESSION_KEY);
            if (currentId) {
                setCurrentSessionId(currentId);
            } else {
                // Create a new session if none exists
                const newId = generateUUID();
                setCurrentSessionId(newId);
                localStorage.setItem(CURRENT_SESSION_KEY, newId);
            }
        } catch (error) {
            console.error('Error loading sessions:', error);
        } finally {
            setIsLoading(false);
        }
    }, []);

    const saveSession = useCallback((messages: Message[], acquisitionData: AcquisitionData) => {
        if (!currentSessionId || messages.length === 0) return;

        try {
            const stored = localStorage.getItem(STORAGE_KEY);
            const allSessions: Record<string, SessionData> = stored ? JSON.parse(stored) : {};

            const existingSession = allSessions[currentSessionId];
            const now = new Date().toISOString();

            const sessionData: SessionData = {
                id: currentSessionId,
                title: generateSessionTitle(messages, acquisitionData),
                summary: generateSessionSummary(acquisitionData),
                messages: messages.map((m) => ({
                    ...m,
                    timestamp: m.timestamp instanceof Date ? m.timestamp.toISOString() : m.timestamp,
                })) as any,
                acquisitionData,
                createdAt: existingSession?.createdAt || now,
                updatedAt: now,
                status: existingSession?.status || 'in_progress',
            };

            allSessions[currentSessionId] = sessionData;
            localStorage.setItem(STORAGE_KEY, JSON.stringify(allSessions));

            // Update sessions list
            setSessions((prev) => {
                const filtered = prev.filter((s) => s.id !== currentSessionId);
                return [
                    {
                        id: sessionData.id,
                        title: sessionData.title,
                        summary: sessionData.summary,
                        createdAt: new Date(sessionData.createdAt),
                        updatedAt: new Date(sessionData.updatedAt),
                        status: sessionData.status,
                        messageCount: messages.length,
                    },
                    ...filtered,
                ];
            });
        } catch (error) {
            console.error('Error saving session:', error);
        }
    }, [currentSessionId]);

    const loadSession = useCallback((sessionId: string): SessionData | null => {
        try {
            const stored = localStorage.getItem(STORAGE_KEY);
            if (!stored) return null;

            const allSessions: Record<string, SessionData> = JSON.parse(stored);
            const session = allSessions[sessionId];

            if (session) {
                // Convert timestamps back to Date objects
                return {
                    ...session,
                    messages: session.messages.map((m: any) => ({
                        ...m,
                        timestamp: new Date(m.timestamp),
                    })),
                };
            }

            return null;
        } catch (error) {
            console.error('Error loading session:', error);
            return null;
        }
    }, []);

    const createNewSession = useCallback((): string => {
        const newId = generateUUID();
        setCurrentSessionId(newId);
        localStorage.setItem(CURRENT_SESSION_KEY, newId);
        return newId;
    }, []);

    const deleteSession = useCallback((sessionId: string) => {
        try {
            const stored = localStorage.getItem(STORAGE_KEY);
            if (!stored) return;

            const allSessions: Record<string, SessionData> = JSON.parse(stored);
            delete allSessions[sessionId];
            localStorage.setItem(STORAGE_KEY, JSON.stringify(allSessions));

            setSessions((prev) => prev.filter((s) => s.id !== sessionId));

            // If deleting current session, create a new one
            if (sessionId === currentSessionId) {
                createNewSession();
            }
        } catch (error) {
            console.error('Error deleting session:', error);
        }
    }, [currentSessionId, createNewSession]);

    const setCurrentSessionById = useCallback((sessionId: string) => {
        setCurrentSessionId(sessionId);
        localStorage.setItem(CURRENT_SESSION_KEY, sessionId);
    }, []);

    const markSessionComplete = useCallback((sessionId: string) => {
        try {
            const stored = localStorage.getItem(STORAGE_KEY);
            if (!stored) return;

            const allSessions: Record<string, SessionData> = JSON.parse(stored);
            if (allSessions[sessionId]) {
                allSessions[sessionId].status = 'completed';
                allSessions[sessionId].updatedAt = new Date().toISOString();
                localStorage.setItem(STORAGE_KEY, JSON.stringify(allSessions));

                setSessions((prev) =>
                    prev.map((s) =>
                        s.id === sessionId
                            ? { ...s, status: 'completed' as const, updatedAt: new Date() }
                            : s
                    )
                );
            }
        } catch (error) {
            console.error('Error marking session complete:', error);
        }
    }, []);

    const currentSession = currentSessionId ? loadSession(currentSessionId) : null;

    return {
        sessions,
        currentSessionId,
        currentSession,
        isLoading,
        saveSession,
        loadSession,
        createNewSession,
        deleteSession,
        setCurrentSession: setCurrentSessionById,
        markSessionComplete,
    };
}
