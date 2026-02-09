'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { AgentType, AgentMessage, ToolResult } from '@/types/mcp';
import {
  AgentSession,
  SharedContext,
  UserConversationStore,
  AgentInsight,
  ConversationOptions,
  DEFAULT_CONVERSATION_OPTIONS,
  createEmptySession,
  createEmptyStore,
} from '@/types/conversation';
import {
  loadConversationStore,
  saveConversationStore,
  getOrCreateSession,
  addMessageToSession,
  addToolResultToSession,
  clearSession,
  updateSharedContext,
  addInsight,
  buildContextPrompt,
  exportSessionAsMarkdown,
  exportSessionAsJSON,
  getStorageStats,
} from '@/lib/conversation-store';
import {
  fullSync,
  syncSessionToBackend,
  syncContextToBackend,
  setupSyncListeners,
  hasPendingSync,
} from '@/lib/conversation-sync';

interface UseAgentSessionOptions {
  userId: string;
  agentId: AgentType;
  options?: ConversationOptions;
  enableSync?: boolean; // Enable backend sync (default: true)
  onLoad?: (session: AgentSession) => void;
  onSave?: () => void;
  onError?: (error: string) => void;
}

interface UseAgentSessionReturn {
  // Session state
  session: AgentSession;
  isLoading: boolean;
  error: string | null;

  // Message operations
  addMessage: (message: AgentMessage) => void;
  addToolResult: (result: ToolResult) => void;
  clearHistory: () => void;

  // Context operations
  sharedContext: SharedContext;
  updateContext: (context: Partial<SharedContext>) => void;
  addAgentInsight: (summary: string, relevantTo?: AgentType[]) => void;
  getContextPrompt: () => string | undefined;

  // Export operations
  exportAsMarkdown: () => string;
  exportAsJSON: () => string;

  // Storage stats
  storageStats: {
    used: number;
    available: number;
    sessionCount: number;
    messageCount: number;
  };

  // Sync status
  isSynced: boolean;
  hasPendingChanges: boolean;

  // Force save/sync
  save: () => void;
  forceSync: () => Promise<void>;
}

/**
 * Hook for managing a persistent agent conversation session.
 *
 * Features:
 * - Auto-loads previous conversation on mount
 * - Auto-saves on every change (debounced)
 * - Supports cross-agent context sharing
 * - Handles storage limits gracefully
 */
export function useAgentSession(options: UseAgentSessionOptions): UseAgentSessionReturn {
  const {
    userId,
    agentId,
    options: convOptions = DEFAULT_CONVERSATION_OPTIONS,
    enableSync = true,
    onLoad,
    onSave,
    onError,
  } = options;

  const [store, setStore] = useState<UserConversationStore>(() => createEmptyStore(userId));
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isSynced, setIsSynced] = useState(false);
  const [storageStats, setStorageStats] = useState({
    used: 0,
    available: 0,
    sessionCount: 0,
    messageCount: 0,
  });

  const saveTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const syncTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Load store on mount with backend sync
  useEffect(() => {
    async function loadAndSync() {
      setIsLoading(true);

      try {
        if (enableSync) {
          // Full sync: fetch from backend, merge with local
          const syncedStore = await fullSync(userId);
          setStore(syncedStore);
          setIsSynced(true);

          const session = getOrCreateSession(syncedStore, agentId);
          onLoad?.(session);
        } else {
          // Local only
          const result = loadConversationStore(userId);
          if (result.success && result.data) {
            setStore(result.data);
            const session = getOrCreateSession(result.data, agentId);
            onLoad?.(session);
          }
        }

        setStorageStats(getStorageStats(userId));
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : 'Failed to load conversations';
        setError(errorMsg);
        onError?.(errorMsg);

        // Fallback to local storage
        const result = loadConversationStore(userId);
        if (result.success && result.data) {
          setStore(result.data);
        }
      } finally {
        setIsLoading(false);
      }
    }

    loadAndSync();

    // Set up online/offline listeners for auto-sync
    const cleanup = enableSync ? setupSyncListeners(userId) : () => {};

    return cleanup;
  }, [userId, agentId, enableSync, onLoad, onError]);

  // Debounced save function with backend sync
  const debouncedSave = useCallback(
    (storeToSave: UserConversationStore, changedAgentId?: AgentType) => {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
      }

      saveTimeoutRef.current = setTimeout(() => {
        // Save to localStorage immediately
        const result = saveConversationStore(storeToSave);

        if (result.success) {
          onSave?.();
          setStorageStats(getStorageStats(userId));

          // Sync to backend (debounced separately for network efficiency)
          if (enableSync && changedAgentId) {
            if (syncTimeoutRef.current) {
              clearTimeout(syncTimeoutRef.current);
            }

            syncTimeoutRef.current = setTimeout(async () => {
              const session = storeToSave.sessions[changedAgentId];
              const synced = await syncSessionToBackend(userId, changedAgentId, session);
              setIsSynced(synced);
            }, 1000); // 1s debounce for backend sync
          }
        } else {
          setError(result.error ?? 'Failed to save conversations');
          onError?.(result.error ?? 'Failed to save conversations');
        }
      }, 300); // 300ms debounce for localStorage
    },
    [userId, enableSync, onSave, onError]
  );

  // Get current session
  const session = store.sessions[agentId] ?? createEmptySession(userId, agentId);

  // Add message to session
  const addMessage = useCallback(
    (message: AgentMessage) => {
      setStore((prevStore) => {
        const currentSession = getOrCreateSession(prevStore, agentId);
        const updatedSession = addMessageToSession(currentSession, message, convOptions);

        const newStore: UserConversationStore = {
          ...prevStore,
          sessions: {
            ...prevStore.sessions,
            [agentId]: updatedSession,
          },
          lastUpdated: new Date().toISOString(),
        };

        if (convOptions.autoSave !== false) {
          debouncedSave(newStore, agentId);
        }

        return newStore;
      });
    },
    [agentId, convOptions, debouncedSave]
  );

  // Add tool result to session
  const addToolResult = useCallback(
    (result: ToolResult) => {
      setStore((prevStore) => {
        const currentSession = getOrCreateSession(prevStore, agentId);
        const updatedSession = addToolResultToSession(currentSession, result, convOptions);

        const newStore: UserConversationStore = {
          ...prevStore,
          sessions: {
            ...prevStore.sessions,
            [agentId]: updatedSession,
          },
          lastUpdated: new Date().toISOString(),
        };

        if (convOptions.autoSave !== false) {
          debouncedSave(newStore, agentId);
        }

        return newStore;
      });
    },
    [agentId, convOptions, debouncedSave]
  );

  // Clear session history
  const clearHistory = useCallback(() => {
    setStore((prevStore) => {
      const newStore = clearSession(prevStore, agentId);

      if (convOptions.autoSave !== false) {
        debouncedSave(newStore, agentId);
      }

      return newStore;
    });
  }, [agentId, convOptions, debouncedSave]);

  // Update shared context
  const updateContext = useCallback(
    (context: Partial<SharedContext>) => {
      setStore((prevStore) => {
        const newStore = updateSharedContext(prevStore, context);

        if (convOptions.autoSave !== false) {
          debouncedSave(newStore);
        }

        return newStore;
      });
    },
    [convOptions, debouncedSave]
  );

  // Add an insight from this agent
  const addAgentInsight = useCallback(
    (summary: string, relevantTo?: AgentType[]) => {
      const insight: AgentInsight = {
        agentId,
        agentName: agentId.replace('_', ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
        summary,
        timestamp: new Date().toISOString(),
        relevantTo,
      };

      setStore((prevStore) => {
        const newStore = addInsight(prevStore, insight);

        if (convOptions.autoSave !== false) {
          debouncedSave(newStore);
        }

        return newStore;
      });
    },
    [agentId, convOptions, debouncedSave]
  );

  // Get context prompt for agent
  const getContextPrompt = useCallback(() => {
    return buildContextPrompt(store, agentId);
  }, [store, agentId]);

  // Export as Markdown
  const exportAsMarkdown = useCallback(() => {
    return exportSessionAsMarkdown(session);
  }, [session]);

  // Export as JSON
  const exportAsJSON = useCallback(() => {
    return exportSessionAsJSON(session);
  }, [session]);

  // Force save
  const save = useCallback(() => {
    const result = saveConversationStore(store);

    if (result.success) {
      onSave?.();
      setStorageStats(getStorageStats(userId));
    } else {
      setError(result.error ?? 'Failed to save conversations');
      onError?.(result.error ?? 'Failed to save conversations');
    }
  }, [store, userId, onSave, onError]);

  // Force full sync with backend
  const forceSync = useCallback(async () => {
    if (!enableSync) return;

    try {
      setIsLoading(true);
      const syncedStore = await fullSync(userId);
      setStore(syncedStore);
      setIsSynced(true);
      setStorageStats(getStorageStats(userId));
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Sync failed';
      setError(errorMsg);
      onError?.(errorMsg);
      setIsSynced(false);
    } finally {
      setIsLoading(false);
    }
  }, [userId, enableSync, onError]);

  // Cleanup timeouts on unmount
  useEffect(() => {
    return () => {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
      }
      if (syncTimeoutRef.current) {
        clearTimeout(syncTimeoutRef.current);
      }
    };
  }, []);

  return {
    session,
    isLoading,
    error,
    addMessage,
    addToolResult,
    clearHistory,
    sharedContext: store.sharedContext,
    updateContext,
    addAgentInsight,
    getContextPrompt,
    exportAsMarkdown,
    exportAsJSON,
    storageStats,
    save,
    isSynced,
    hasPendingChanges: hasPendingSync(),
    forceSync,
  };
}
