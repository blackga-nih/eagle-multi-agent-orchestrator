/**
 * idb-cache.ts
 *
 * Low-level IndexedDB access layer for EAGLE chat message caching.
 * Uses the `idb` package for a promise-based API over the raw IDB API.
 *
 * Database: `eagle-cache-{tenantId}-{userId}` (version 1)
 *
 * Stores:
 *   sessions  — keyPath: "id"
 *               indexes: tenantId, userId, updatedAt, syncStatus
 *   messages  — keyPath: "id"
 *               indexes: sessionId, timestamp, syncStatus
 *
 * All functions guard against SSR (window undefined) and swallow errors
 * gracefully — they log and return null/empty rather than throwing.
 */

import { openDB, IDBPDatabase } from 'idb';
import { ChatMessage } from '@/types/chat';

// ---------------------------------------------------------------------------
// Schema types
// ---------------------------------------------------------------------------

export interface IDBSession {
    id: string;
    tenantId: string;
    userId: string;
    title: string;
    summary?: string;
    status: 'in_progress' | 'completed' | 'draft';
    syncStatus: 'synced' | 'pending' | 'error';
    createdAt: string;
    updatedAt: string;
    messageCount: number;
}

export interface IDBMessage {
    /** Globally unique — `{sessionId}#{messageId}` */
    id: string;
    sessionId: string;
    role: 'user' | 'assistant';
    content: string;
    timestamp: string; // ISO string — IDB cannot store Date objects in indexes
    reasoning?: string;
    agent_id?: string;
    agent_name?: string;
    syncStatus: 'synced' | 'pending' | 'error';
}

type EagleDB = IDBPDatabase<{
    sessions: {
        key: string;
        value: IDBSession;
        indexes: {
            tenantId: string;
            userId: string;
            updatedAt: string;
            syncStatus: string;
        };
    };
    messages: {
        key: string;
        value: IDBMessage;
        indexes: {
            sessionId: string;
            timestamp: string;
            syncStatus: string;
        };
    };
}>;

// ---------------------------------------------------------------------------
// Singleton DB handles (one per database name)
// ---------------------------------------------------------------------------

const dbHandles = new Map<string, Promise<EagleDB>>();

function dbName(userId: string, tenantId: string): string {
    return `eagle-cache-${tenantId}-${userId}`;
}

/**
 * Returns (and caches) an open DB handle for the given user/tenant pair.
 * Safe to call multiple times — only one `openDB` call is issued per name.
 * Returns null when called during SSR (no `window` object).
 */
export async function getEagleDB(
    userId: string,
    tenantId: string,
): Promise<EagleDB | null> {
    if (typeof window === 'undefined') return null;

    const name = dbName(userId, tenantId);

    if (!dbHandles.has(name)) {
        const handle = openDB<{
            sessions: {
                key: string;
                value: IDBSession;
                indexes: {
                    tenantId: string;
                    userId: string;
                    updatedAt: string;
                    syncStatus: string;
                };
            };
            messages: {
                key: string;
                value: IDBMessage;
                indexes: {
                    sessionId: string;
                    timestamp: string;
                    syncStatus: string;
                };
            };
        }>(name, 1, {
            upgrade(db) {
                // sessions store
                if (!db.objectStoreNames.contains('sessions')) {
                    const sessionStore = db.createObjectStore('sessions', {
                        keyPath: 'id',
                    });
                    sessionStore.createIndex('tenantId', 'tenantId');
                    sessionStore.createIndex('userId', 'userId');
                    sessionStore.createIndex('updatedAt', 'updatedAt');
                    sessionStore.createIndex('syncStatus', 'syncStatus');
                }

                // messages store
                if (!db.objectStoreNames.contains('messages')) {
                    const msgStore = db.createObjectStore('messages', {
                        keyPath: 'id',
                    });
                    msgStore.createIndex('sessionId', 'sessionId');
                    msgStore.createIndex('timestamp', 'timestamp');
                    msgStore.createIndex('syncStatus', 'syncStatus');
                }
            },
        }) as unknown as Promise<EagleDB>;

        dbHandles.set(name, handle);
    }

    try {
        return await dbHandles.get(name)!;
    } catch (err) {
        console.error('[idb-cache] Failed to open DB:', err);
        dbHandles.delete(name); // allow retry next time
        return null;
    }
}

// ---------------------------------------------------------------------------
// Session operations
// ---------------------------------------------------------------------------

export async function idbGetSession(
    db: EagleDB,
    sessionId: string,
): Promise<IDBSession | null> {
    try {
        return (await db.get('sessions', sessionId)) ?? null;
    } catch (err) {
        console.error('[idb-cache] idbGetSession error:', err);
        return null;
    }
}

export async function idbPutSession(
    db: EagleDB,
    session: IDBSession,
): Promise<void> {
    try {
        await db.put('sessions', session);
    } catch (err) {
        console.error('[idb-cache] idbPutSession error:', err);
    }
}

export async function idbGetAllSessions(
    db: EagleDB,
    userId: string,
): Promise<IDBSession[]> {
    try {
        return await db.getAllFromIndex('sessions', 'userId', userId);
    } catch (err) {
        console.error('[idb-cache] idbGetAllSessions error:', err);
        return [];
    }
}

export async function idbDeleteSession(
    db: EagleDB,
    sessionId: string,
): Promise<void> {
    try {
        // Delete session record
        await db.delete('sessions', sessionId);

        // Delete all associated messages via cursor on the sessionId index
        const tx = db.transaction('messages', 'readwrite');
        const index = tx.store.index('sessionId');
        let cursor = await index.openCursor(sessionId);
        while (cursor) {
            await cursor.delete();
            cursor = await cursor.continue();
        }
        await tx.done;
    } catch (err) {
        console.error('[idb-cache] idbDeleteSession error:', err);
    }
}

// ---------------------------------------------------------------------------
// Message operations
// ---------------------------------------------------------------------------

/**
 * Compound key for a message record: `{sessionId}#{messageId}`.
 * Keeps the keyspace unique across sessions without a composite keyPath.
 */
function messageKey(sessionId: string, messageId: string): string {
    return `${sessionId}#${messageId}`;
}

export async function idbGetMessages(
    db: EagleDB,
    sessionId: string,
): Promise<IDBMessage[]> {
    try {
        const rows = await db.getAllFromIndex('messages', 'sessionId', sessionId);
        // Sort ascending by ISO timestamp string (lexicographic sort works for ISO-8601)
        rows.sort((a, b) => (a.timestamp < b.timestamp ? -1 : 1));
        return rows;
    } catch (err) {
        console.error('[idb-cache] idbGetMessages error:', err);
        return [];
    }
}

export async function idbPutMessage(
    db: EagleDB,
    sessionId: string,
    message: ChatMessage,
    syncStatus: IDBMessage['syncStatus'] = 'pending',
): Promise<void> {
    try {
        const record: IDBMessage = {
            id: messageKey(sessionId, message.id),
            sessionId,
            role: message.role,
            content: message.content,
            timestamp:
                message.timestamp instanceof Date
                    ? message.timestamp.toISOString()
                    : String(message.timestamp),
            reasoning: message.reasoning,
            agent_id: message.agent_id,
            agent_name: message.agent_name,
            syncStatus,
        };
        await db.put('messages', record);
    } catch (err) {
        console.error('[idb-cache] idbPutMessage error:', err);
    }
}

export async function idbPutMessages(
    db: EagleDB,
    sessionId: string,
    messages: ChatMessage[],
    syncStatus: IDBMessage['syncStatus'] = 'synced',
): Promise<void> {
    try {
        const tx = db.transaction('messages', 'readwrite');
        const puts = messages.map((msg) => {
            const record: IDBMessage = {
                id: messageKey(sessionId, msg.id),
                sessionId,
                role: msg.role,
                content: msg.content,
                timestamp:
                    msg.timestamp instanceof Date
                        ? msg.timestamp.toISOString()
                        : String(msg.timestamp),
                reasoning: msg.reasoning,
                agent_id: msg.agent_id,
                agent_name: msg.agent_name,
                syncStatus,
            };
            return tx.store.put(record);
        });
        await Promise.all(puts);
        await tx.done;
    } catch (err) {
        console.error('[idb-cache] idbPutMessages error:', err);
    }
}

/**
 * Convert an IDBMessage record back to the app's ChatMessage shape.
 */
export function idbMessageToChatMessage(row: IDBMessage): ChatMessage {
    return {
        id: row.id.replace(`${row.sessionId}#`, ''),
        role: row.role,
        content: row.content,
        timestamp: new Date(row.timestamp),
        reasoning: row.reasoning,
        agent_id: row.agent_id,
        agent_name: row.agent_name,
    };
}
