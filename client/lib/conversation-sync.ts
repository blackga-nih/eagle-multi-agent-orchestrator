/**
 * Conversation Sync Service
 *
 * Handles two-way synchronization between localStorage (local cache)
 * and the backend API (source of truth).
 *
 * Sync Strategy:
 * 1. On page load: Fetch from backend, merge with localStorage
 * 2. On message: Update localStorage immediately, queue backend sync
 * 3. Conflict resolution: Use timestamps, prefer newer data
 * 4. Offline: Queue changes, sync when online
 */

import { AgentType } from '@/types/mcp';
import {
  AgentSession,
  SharedContext,
  UserConversationStore,
  createEmptyStore,
} from '@/types/conversation';
import { loadConversationStore, saveConversationStore } from './conversation-store';

const API_BASE = '/api/conversations';

// Sync queue for offline support
interface SyncQueueItem {
  type: 'session' | 'context';
  agentId?: AgentType;
  data: unknown;
  timestamp: string;
}

let syncQueue: SyncQueueItem[] = [];
let isSyncing = false;

/**
 * Fetch user's conversations from the backend API.
 */
export async function fetchFromBackend(userId: string): Promise<UserConversationStore | null> {
  try {
    const response = await fetch(`${API_BASE}?user_id=${userId}`, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
      signal: AbortSignal.timeout(5000),
    });

    if (!response.ok) {
      console.warn('Backend fetch failed:', response.status);
      return null;
    }

    const data = await response.json();
    return {
      userId: data.userId,
      sessions: data.sessions || {
        frontend: null,
        backend: null,
        aws_admin: null,
        analyst: null,
      },
      sharedContext: data.sharedContext || {},
      lastUpdated: data.lastUpdated || new Date().toISOString(),
    };
  } catch (error) {
    console.warn('Backend unavailable:', error);
    return null;
  }
}

/**
 * Push local store to backend.
 */
export async function pushToBackend(store: UserConversationStore): Promise<boolean> {
  try {
    const response = await fetch(API_BASE, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(store),
      signal: AbortSignal.timeout(5000),
    });

    return response.ok;
  } catch (error) {
    console.warn('Backend push failed:', error);
    return false;
  }
}

/**
 * Sync a specific agent session to backend.
 */
export async function syncSessionToBackend(
  userId: string,
  agentId: AgentType,
  session: AgentSession | null,
): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE}/${agentId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ userId, session }),
      signal: AbortSignal.timeout(5000),
    });

    return response.ok;
  } catch (error) {
    console.warn(`Session sync failed for ${agentId}:`, error);

    // Add to offline queue
    syncQueue.push({
      type: 'session',
      agentId,
      data: { userId, session },
      timestamp: new Date().toISOString(),
    });

    return false;
  }
}

/**
 * Sync shared context to backend.
 */
export async function syncContextToBackend(
  userId: string,
  context: SharedContext,
): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE}/context`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ userId, context }),
      signal: AbortSignal.timeout(5000),
    });

    return response.ok;
  } catch (error) {
    console.warn('Context sync failed:', error);

    // Add to offline queue
    syncQueue.push({
      type: 'context',
      data: { userId, context },
      timestamp: new Date().toISOString(),
    });

    return false;
  }
}

/**
 * Merge backend data with local data.
 * Uses timestamp to resolve conflicts (newer wins).
 */
export function mergeStores(
  local: UserConversationStore,
  remote: UserConversationStore,
): UserConversationStore {
  const localTime = new Date(local.lastUpdated).getTime();
  const remoteTime = new Date(remote.lastUpdated).getTime();

  // If remote is newer, prefer remote but preserve any local-only data
  if (remoteTime > localTime) {
    return {
      ...remote,
      sessions: {
        frontend: mergeSession(local.sessions.frontend, remote.sessions.frontend),
        backend: mergeSession(local.sessions.backend, remote.sessions.backend),
        aws_admin: mergeSession(local.sessions.aws_admin, remote.sessions.aws_admin),
        analyst: mergeSession(local.sessions.analyst, remote.sessions.analyst),
      },
      sharedContext: {
        ...local.sharedContext,
        ...remote.sharedContext,
      },
    };
  }

  // Local is newer, keep local
  return local;
}

/**
 * Merge two sessions, preferring the one with more recent messages.
 */
function mergeSession(
  local: AgentSession | null,
  remote: AgentSession | null,
): AgentSession | null {
  if (!local) return remote;
  if (!remote) return local;

  const localTime = new Date(local.updatedAt).getTime();
  const remoteTime = new Date(remote.updatedAt).getTime();

  // If timestamps are very close, prefer the one with more messages
  if (Math.abs(localTime - remoteTime) < 1000) {
    return local.messageCount >= remote.messageCount ? local : remote;
  }

  return localTime > remoteTime ? local : remote;
}

/**
 * Full sync: fetch from backend, merge with local, save both.
 */
export async function fullSync(userId: string): Promise<UserConversationStore> {
  // Load local store
  const localResult = loadConversationStore(userId);
  const localStore =
    localResult.success && localResult.data ? localResult.data : createEmptyStore(userId);

  // Fetch from backend
  const remoteStore = await fetchFromBackend(userId);

  if (!remoteStore) {
    // Backend unavailable - just use local
    return localStore;
  }

  // Merge stores
  const mergedStore = mergeStores(localStore, remoteStore);

  // Save merged result to both
  saveConversationStore(mergedStore);
  await pushToBackend(mergedStore);

  return mergedStore;
}

/**
 * Process offline sync queue.
 * Called when connection is restored.
 */
export async function processOfflineQueue(userId: string): Promise<void> {
  if (isSyncing || syncQueue.length === 0) return;

  isSyncing = true;

  try {
    const queue = [...syncQueue];
    syncQueue = [];

    for (const item of queue) {
      if (item.type === 'session' && item.agentId) {
        const { session } = item.data as { userId: string; session: AgentSession | null };
        await syncSessionToBackend(userId, item.agentId, session);
      } else if (item.type === 'context') {
        const { context } = item.data as { userId: string; context: SharedContext };
        await syncContextToBackend(userId, context);
      }
    }
  } finally {
    isSyncing = false;
  }
}

/**
 * Check if there are pending offline changes.
 */
export function hasPendingSync(): boolean {
  return syncQueue.length > 0;
}

/**
 * Get the number of pending sync items.
 */
export function getPendingSyncCount(): number {
  return syncQueue.length;
}

/**
 * Set up online/offline event listeners for auto-sync.
 */
export function setupSyncListeners(userId: string): () => void {
  const handleOnline = () => {
    console.log('[Sync] Connection restored, processing offline queue...');
    processOfflineQueue(userId);
  };

  if (typeof window !== 'undefined') {
    window.addEventListener('online', handleOnline);

    return () => {
      window.removeEventListener('online', handleOnline);
    };
  }

  return () => {};
}
