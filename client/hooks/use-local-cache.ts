'use client';

/**
 * use-local-cache.ts
 *
 * React hook providing an IndexedDB-backed cache layer for EAGLE chat
 * messages and sessions. Designed as a drop-in complement to
 * `use-session-persistence.ts` — it exposes the same core interface
 * (sessions, currentSessionId, saveSession, loadSession, createNewSession,
 * deleteSession, setCurrentSession, markSessionComplete, renameSession)
 * plus two new methods:
 *
 *   writeMessageOptimistic(sessionId, message)
 *     Writes a message to IndexedDB immediately, fire-and-forget.
 *     NEVER awaited in the hot path — the caller gets no Promise back.
 *
 *   hydrateFromBackend(sessionId)
 *     Fetches messages from /api/sessions/{sessionId}/messages and
 *     populates IDB if it is empty or stale (>5 minutes old).
 *
 * localStorage remains as a secondary write path for backwards compat with
 * code that reads from it directly (e.g., use-session-persistence.ts).
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import {
    getEagleDB,
    idbGetSession,
    idbPutSession,
    idbDeleteSession,
    idbGetMessages,
    idbPutMessage,
    idbPutMessages,
    IDBSession,
} from '@/lib/idb-cache';
import { ChatMessage, DocumentInfo } from '@/types/chat';
import { Message, AcquisitionData } from '@/components/chat/chat-interface';
import { ChatSession } from '@/components/layout/chat-history-dropdown';
import { generateUUID } from '@/lib/uuid';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STORAGE_KEY = 'eagle_chat_sessions';
const CURRENT_SESSION_KEY = 'eagle_current_session';
/** Hydrate from backend if IDB cache is older than this many milliseconds. */
const STALE_THRESHOLD_MS = 5 * 60 * 1000; // 5 minutes

// ---------------------------------------------------------------------------
// SessionData mirrors the shape from use-session-persistence.ts
// ---------------------------------------------------------------------------

interface SessionData {
    id: string;
    title: string;
    summary?: string;
    messages: Message[];
    acquisitionData: AcquisitionData;
    documents?: Record<string, DocumentInfo[]>;
    createdAt: string;
    updatedAt: string;
    status: 'in_progress' | 'completed' | 'draft';
}

// ---------------------------------------------------------------------------
// Return type (superset of UseSessionPersistenceReturn)
// ---------------------------------------------------------------------------

export interface UseLocalCacheReturn {
    sessions: ChatSession[];
    currentSessionId: string;
    currentSession: SessionData | null;
    isLoading: boolean;
    saveSession: (
        messages: Message[],
        acquisitionData: AcquisitionData,
        documents?: Record<string, DocumentInfo[]>,
    ) => void;
    loadSession: (sessionId: string) => SessionData | null;
    createNewSession: () => string;
    deleteSession: (sessionId: string) => void;
    setCurrentSession: (sessionId: string) => void;
    markSessionComplete: (sessionId: string) => void;
    renameSession: (sessionId: string, newTitle: string) => void;
    /** Fire-and-forget optimistic write to IndexedDB. Never awaited. */
    writeMessageOptimistic: (sessionId: string, message: ChatMessage) => void;
    /** Fetch from backend and populate IDB if empty or stale (>5 min). */
    hydrateFromBackend: (sessionId: string) => Promise<void>;
}

// ---------------------------------------------------------------------------
// Internal type for raw localStorage message (timestamps are stored as strings)
// ---------------------------------------------------------------------------

interface RawMessage {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    timestamp: string;
    reasoning?: string;
    agent_id?: string;
    agent_name?: string;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useLocalCache(
    userId: string,
    tenantId: string,
): UseLocalCacheReturn {
    const [sessions, setSessions] = useState<ChatSession[]>([]);
    const [currentSessionId, setCurrentSessionId] = useState<string>('');
    const [isLoading, setIsLoading] = useState(true);

    // DB handle stored in a ref — avoids re-renders when it becomes available.
    type EagleDBType = Awaited<ReturnType<typeof getEagleDB>>;
    const dbRef = useRef<EagleDBType>(null);

    // ---------------------------------------------------------------------------
    // DB initialisation
    // ---------------------------------------------------------------------------

    useEffect(() => {
        if (!userId || !tenantId) return;

        getEagleDB(userId, tenantId)
            .then((db) => {
                dbRef.current = db;
            })
            .catch((err) => {
                console.error('[use-local-cache] Failed to open IDB:', err);
            });
    }, [userId, tenantId]);

    // ---------------------------------------------------------------------------
    // Mount: load sessions from localStorage (fast synchronous path)
    // ---------------------------------------------------------------------------

    useEffect(() => {
        try {
            const stored = localStorage.getItem(STORAGE_KEY);
            if (stored) {
                const data: Record<string, SessionData> = JSON.parse(stored);
                const sessionList: ChatSession[] = Object.values(data).map(
                    (s) => ({
                        id: s.id,
                        title: s.title,
                        summary: s.summary,
                        createdAt: new Date(s.createdAt),
                        updatedAt: new Date(s.updatedAt),
                        status: s.status,
                        messageCount: s.messages.length,
                    }),
                );
                setSessions(sessionList);
            }

            const currentId = localStorage.getItem(CURRENT_SESSION_KEY);
            if (currentId) {
                setCurrentSessionId(currentId);
            } else {
                const newId = generateUUID();
                setCurrentSessionId(newId);
                localStorage.setItem(CURRENT_SESSION_KEY, newId);
            }
        } catch (err) {
            console.error('[use-local-cache] Error loading from localStorage:', err);
        } finally {
            setIsLoading(false);
        }
    }, []);

    // ---------------------------------------------------------------------------
    // writeMessageOptimistic — fire-and-forget
    // ---------------------------------------------------------------------------

    const writeMessageOptimistic = useCallback(
        (sessionId: string, message: ChatMessage): void => {
            // Kick off async write without awaiting — never blocks the caller.
            void (async () => {
                const db = dbRef.current;
                if (!db) {
                    // DB not ready yet — quietly drop (localStorage still has it)
                    return;
                }
                await idbPutMessage(db, sessionId, message, 'pending');
            })();
        },
        [],
    );

    // ---------------------------------------------------------------------------
    // hydrateFromBackend
    // ---------------------------------------------------------------------------

    const hydrateFromBackend = useCallback(
        async (sessionId: string): Promise<void> => {
            const db = dbRef.current;
            if (!db || !sessionId) return;

            try {
                // Check existing IDB state
                const existingMessages = await idbGetMessages(db, sessionId);
                const sessionMeta = await idbGetSession(db, sessionId);

                if (existingMessages.length > 0 && sessionMeta) {
                    const updatedAt = new Date(sessionMeta.updatedAt).getTime();
                    const ageMs = Date.now() - updatedAt;
                    if (ageMs < STALE_THRESHOLD_MS) {
                        // Cache is fresh — skip backend fetch
                        return;
                    }
                }

                // Fetch from backend
                const resp = await fetch(
                    `/api/sessions/${encodeURIComponent(sessionId)}/messages`,
                );
                if (!resp.ok) {
                    console.warn(
                        '[use-local-cache] Backend returned',
                        resp.status,
                        'for session messages',
                    );
                    return;
                }

                const data = await resp.json();
                const rawList: unknown[] = data.messages ?? data ?? [];

                const backendMessages: ChatMessage[] = rawList.map((raw) => {
                    // Parse each raw backend record safely
                    const m = raw as Record<string, unknown>;
                    return {
                        id: String(m['id'] ?? generateUUID()),
                        role: (m['role'] === 'user' ? 'user' : 'assistant') as 'user' | 'assistant',
                        content: String(m['content'] ?? ''),
                        timestamp: m['timestamp']
                            ? new Date(m['timestamp'] as string)
                            : new Date(),
                        reasoning: m['reasoning'] != null ? String(m['reasoning']) : undefined,
                        agent_id: m['agent_id'] != null ? String(m['agent_id']) : undefined,
                        agent_name: m['agent_name'] != null ? String(m['agent_name']) : undefined,
                    };
                });

                if (backendMessages.length > 0) {
                    await idbPutMessages(db, sessionId, backendMessages, 'synced');

                    // Update session metadata timestamp so it is not considered stale again
                    const meta = await idbGetSession(db, sessionId);
                    if (meta) {
                        await idbPutSession(db, {
                            ...meta,
                            updatedAt: new Date().toISOString(),
                            messageCount: backendMessages.length,
                        });
                    }
                }
            } catch (err) {
                console.error('[use-local-cache] hydrateFromBackend error:', err);
            }
        },
        [],
    );

    // ---------------------------------------------------------------------------
    // saveSession — writes to localStorage (sync) + IDB (async, fire-and-forget)
    // ---------------------------------------------------------------------------

    const saveSession = useCallback(
        (
            messages: Message[],
            acquisitionData: AcquisitionData,
            documents?: Record<string, DocumentInfo[]>,
        ): void => {
            if (!currentSessionId || messages.length === 0) return;

            try {
                const stored = localStorage.getItem(STORAGE_KEY);
                const allSessions: Record<string, SessionData> = stored
                    ? JSON.parse(stored)
                    : {};

                const existing = allSessions[currentSessionId];
                const now = new Date().toISOString();

                let strippedDocs: Record<string, DocumentInfo[]> | undefined;
                if (documents && Object.keys(documents).length > 0) {
                    strippedDocs = {};
                    for (const [msgId, docs] of Object.entries(documents)) {
                        strippedDocs[msgId] = docs.map(
                            // eslint-disable-next-line @typescript-eslint/no-unused-vars
                            ({ content, ...meta }) => meta,
                        );
                    }
                }

                const sessionData: SessionData = {
                    id: currentSessionId,
                    title:
                        existing?.title ??
                        `Session ${new Date().toLocaleDateString()}`,
                    summary: existing?.summary,
                    messages: messages.map((m) => ({
                        ...m,
                        timestamp:
                            m.timestamp instanceof Date
                                ? (m.timestamp.toISOString() as unknown as Date)
                                : m.timestamp,
                    })) as Message[],
                    acquisitionData,
                    documents: strippedDocs,
                    createdAt: existing?.createdAt ?? now,
                    updatedAt: now,
                    status: existing?.status ?? 'in_progress',
                };

                allSessions[currentSessionId] = sessionData;
                localStorage.setItem(STORAGE_KEY, JSON.stringify(allSessions));

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

                // Also persist to IDB asynchronously — fire-and-forget
                void (async () => {
                    const db = dbRef.current;
                    if (!db) return;

                    const idbSession: IDBSession = {
                        id: currentSessionId,
                        tenantId,
                        userId,
                        title: sessionData.title,
                        summary: sessionData.summary,
                        status: sessionData.status,
                        syncStatus: 'pending',
                        createdAt: sessionData.createdAt,
                        updatedAt: now,
                        messageCount: messages.length,
                    };
                    await idbPutSession(db, idbSession);

                    // Write ChatMessage-shaped records (no AcquisitionData overhead)
                    const chatMessages: ChatMessage[] = messages.map((m) => ({
                        id: m.id,
                        role: m.role,
                        content: m.content,
                        timestamp:
                            m.timestamp instanceof Date
                                ? m.timestamp
                                : new Date(m.timestamp as unknown as string),
                        reasoning: m.reasoning,
                        agent_id: m.agent_id,
                        agent_name: m.agent_name,
                    }));
                    await idbPutMessages(db, currentSessionId, chatMessages, 'pending');
                })();
            } catch (err) {
                console.error('[use-local-cache] saveSession error:', err);
            }
        },
        [currentSessionId, userId, tenantId],
    );

    // ---------------------------------------------------------------------------
    // loadSession — reads from localStorage (synchronous, fast)
    // ---------------------------------------------------------------------------

    const loadSession = useCallback(
        (sessionId: string): SessionData | null => {
            try {
                const stored = localStorage.getItem(STORAGE_KEY);
                if (!stored) return null;

                const allSessions: Record<string, SessionData> = JSON.parse(stored);
                const session = allSessions[sessionId];
                if (!session) return null;

                return {
                    ...session,
                    messages: session.messages.map((m) => {
                        // Timestamps are stored as ISO strings — rehydrate to Date
                        const raw = m as unknown as RawMessage;
                        const result: Message = {
                            id: raw.id,
                            role: raw.role,
                            content: raw.content,
                            timestamp: new Date(raw.timestamp),
                            reasoning: raw.reasoning,
                            agent_id: raw.agent_id,
                            agent_name: raw.agent_name,
                        };
                        return result;
                    }),
                };
            } catch (err) {
                console.error('[use-local-cache] loadSession error:', err);
                return null;
            }
        },
        [],
    );

    // ---------------------------------------------------------------------------
    // createNewSession
    // ---------------------------------------------------------------------------

    const createNewSession = useCallback((): string => {
        const newId = generateUUID();
        setCurrentSessionId(newId);
        localStorage.setItem(CURRENT_SESSION_KEY, newId);
        return newId;
    }, []);

    // ---------------------------------------------------------------------------
    // deleteSession
    // ---------------------------------------------------------------------------

    const deleteSession = useCallback(
        (sessionId: string): void => {
            try {
                const stored = localStorage.getItem(STORAGE_KEY);
                if (!stored) return;

                const allSessions: Record<string, SessionData> = JSON.parse(stored);
                delete allSessions[sessionId];
                localStorage.setItem(STORAGE_KEY, JSON.stringify(allSessions));

                setSessions((prev) => prev.filter((s) => s.id !== sessionId));

                if (sessionId === currentSessionId) {
                    createNewSession();
                }

                // Also delete from IDB — fire-and-forget
                void (async () => {
                    const db = dbRef.current;
                    if (!db) return;
                    await idbDeleteSession(db, sessionId);
                })();
            } catch (err) {
                console.error('[use-local-cache] deleteSession error:', err);
            }
        },
        [currentSessionId, createNewSession],
    );

    // ---------------------------------------------------------------------------
    // setCurrentSession
    // ---------------------------------------------------------------------------

    const setCurrentSession = useCallback((sessionId: string): void => {
        setCurrentSessionId(sessionId);
        localStorage.setItem(CURRENT_SESSION_KEY, sessionId);
    }, []);

    // ---------------------------------------------------------------------------
    // markSessionComplete
    // ---------------------------------------------------------------------------

    const markSessionComplete = useCallback(
        (sessionId: string): void => {
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
                                ? {
                                      ...s,
                                      status: 'completed' as const,
                                      updatedAt: new Date(),
                                  }
                                : s,
                        ),
                    );
                }

                // Update IDB — fire-and-forget
                void (async () => {
                    const db = dbRef.current;
                    if (!db) return;
                    const meta = await idbGetSession(db, sessionId);
                    if (meta) {
                        await idbPutSession(db, {
                            ...meta,
                            status: 'completed',
                            updatedAt: new Date().toISOString(),
                        });
                    }
                })();
            } catch (err) {
                console.error('[use-local-cache] markSessionComplete error:', err);
            }
        },
        [],
    );

    // ---------------------------------------------------------------------------
    // renameSession
    // ---------------------------------------------------------------------------

    const renameSession = useCallback(
        (sessionId: string, newTitle: string): void => {
            try {
                const stored = localStorage.getItem(STORAGE_KEY);
                if (!stored) return;

                const allSessions: Record<string, SessionData> = JSON.parse(stored);
                if (allSessions[sessionId]) {
                    allSessions[sessionId].title = newTitle;
                    allSessions[sessionId].updatedAt = new Date().toISOString();
                    localStorage.setItem(STORAGE_KEY, JSON.stringify(allSessions));

                    setSessions((prev) =>
                        prev.map((s) =>
                            s.id === sessionId
                                ? { ...s, title: newTitle, updatedAt: new Date() }
                                : s,
                        ),
                    );

                    // Sync to backend — fire-and-forget
                    fetch(`/api/sessions/${sessionId}`, {
                        method: 'PATCH',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ title: newTitle }),
                    }).catch((err) =>
                        console.error('[use-local-cache] renameSession backend sync error:', err),
                    );

                    // Update IDB — fire-and-forget
                    void (async () => {
                        const db = dbRef.current;
                        if (!db) return;
                        const meta = await idbGetSession(db, sessionId);
                        if (meta) {
                            await idbPutSession(db, {
                                ...meta,
                                title: newTitle,
                                updatedAt: new Date().toISOString(),
                            });
                        }
                    })();
                }
            } catch (err) {
                console.error('[use-local-cache] renameSession error:', err);
            }
        },
        [],
    );

    // ---------------------------------------------------------------------------
    // currentSession (synchronous read from localStorage)
    // ---------------------------------------------------------------------------

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
        setCurrentSession,
        markSessionComplete,
        renameSession,
        writeMessageOptimistic,
        hydrateFromBackend,
    };
}
