/**
 * Conversation Store
 *
 * Utilities for persisting agent conversations to localStorage.
 * Supports cross-agent context sharing and session management.
 */

import { AgentType, AgentMessage, ToolResult } from '@/types/mcp';
import {
  AgentSession,
  SharedContext,
  UserConversationStore,
  StorageResult,
  ConversationOptions,
  AgentInsight,
  STORAGE_KEYS,
  STORAGE_VERSION,
  DEFAULT_CONVERSATION_OPTIONS,
  createEmptySession,
  createEmptyStore,
} from '@/types/conversation';

/**
 * In-memory store for server-side API routes (development only).
 * This is used when localStorage isn't available (server-side rendering).
 */
export const memoryStore: Map<
  string,
  {
    sessions: Record<AgentType, AgentSession | null>;
    sharedContext: SharedContext;
    lastUpdated: string;
  }
> = new Map();

/**
 * Check if localStorage is available.
 */
function isStorageAvailable(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    const test = '__storage_test__';
    localStorage.setItem(test, test);
    localStorage.removeItem(test);
    return true;
  } catch {
    return false;
  }
}

/**
 * Check and migrate storage version if needed.
 */
function checkStorageVersion(): void {
  if (!isStorageAvailable()) return;

  const versionKey = STORAGE_KEYS.version();
  const storedVersion = localStorage.getItem(versionKey);

  if (!storedVersion || parseInt(storedVersion, 10) < STORAGE_VERSION) {
    // Future: Add migration logic here
    localStorage.setItem(versionKey, String(STORAGE_VERSION));
  }
}

/**
 * Load user's conversation store from localStorage.
 */
export function loadConversationStore(userId: string): StorageResult<UserConversationStore> {
  if (!isStorageAvailable()) {
    return { success: false, error: 'localStorage not available' };
  }

  checkStorageVersion();

  try {
    const key = STORAGE_KEYS.sessions(userId);
    const stored = localStorage.getItem(key);

    if (!stored) {
      const emptyStore = createEmptyStore(userId);
      return { success: true, data: emptyStore };
    }

    const store = JSON.parse(stored) as UserConversationStore;
    return { success: true, data: store };
  } catch (err) {
    console.error('Failed to load conversation store:', err);
    return {
      success: false,
      error: err instanceof Error ? err.message : 'Unknown error',
    };
  }
}

/**
 * Save user's conversation store to localStorage.
 */
export function saveConversationStore(store: UserConversationStore): StorageResult<void> {
  if (!isStorageAvailable()) {
    return { success: false, error: 'localStorage not available' };
  }

  try {
    const key = STORAGE_KEYS.sessions(store.userId);
    store.lastUpdated = new Date().toISOString();
    localStorage.setItem(key, JSON.stringify(store));
    return { success: true };
  } catch (err) {
    console.error('Failed to save conversation store:', err);
    return {
      success: false,
      error: err instanceof Error ? err.message : 'Unknown error',
    };
  }
}

/**
 * Get or create a session for a specific agent.
 */
export function getOrCreateSession(store: UserConversationStore, agentId: AgentType): AgentSession {
  if (store.sessions[agentId]) {
    return store.sessions[agentId]!;
  }

  const newSession = createEmptySession(store.userId, agentId);
  store.sessions[agentId] = newSession;
  return newSession;
}

/**
 * Add a message to an agent session.
 */
export function addMessageToSession(
  session: AgentSession,
  message: AgentMessage,
  options: ConversationOptions = DEFAULT_CONVERSATION_OPTIONS,
): AgentSession {
  const updatedMessages = [...session.messages, message];

  // Trim to max messages if needed
  const maxMessages = options.maxMessages ?? 100;
  const trimmedMessages =
    updatedMessages.length > maxMessages ? updatedMessages.slice(-maxMessages) : updatedMessages;

  return {
    ...session,
    messages: trimmedMessages,
    messageCount: session.messageCount + 1,
    updatedAt: new Date().toISOString(),
  };
}

/**
 * Add a tool result to an agent session.
 */
export function addToolResultToSession(
  session: AgentSession,
  toolResult: ToolResult,
  options: ConversationOptions = DEFAULT_CONVERSATION_OPTIONS,
): AgentSession {
  const updatedResults = [...session.toolResults, toolResult];

  // Trim to max tool results if needed
  const maxToolResults = options.maxToolResults ?? 50;
  const trimmedResults =
    updatedResults.length > maxToolResults ? updatedResults.slice(-maxToolResults) : updatedResults;

  return {
    ...session,
    toolResults: trimmedResults,
    updatedAt: new Date().toISOString(),
  };
}

/**
 * Clear a specific agent session.
 */
export function clearSession(
  store: UserConversationStore,
  agentId: AgentType,
): UserConversationStore {
  return {
    ...store,
    sessions: {
      ...store.sessions,
      [agentId]: null,
    },
    lastUpdated: new Date().toISOString(),
  };
}

/**
 * Clear all sessions for a user.
 */
export function clearAllSessions(store: UserConversationStore): UserConversationStore {
  return {
    ...store,
    sessions: {
      frontend: null,
      backend: null,
      aws_admin: null,
      analyst: null,
    },
    sharedContext: {},
    lastUpdated: new Date().toISOString(),
  };
}

/**
 * Update shared context.
 */
export function updateSharedContext(
  store: UserConversationStore,
  context: Partial<SharedContext>,
): UserConversationStore {
  return {
    ...store,
    sharedContext: {
      ...store.sharedContext,
      ...context,
    },
    lastUpdated: new Date().toISOString(),
  };
}

/**
 * Add an insight to shared context.
 */
export function addInsight(
  store: UserConversationStore,
  insight: AgentInsight,
  maxInsights: number = 10,
): UserConversationStore {
  const currentInsights = store.sharedContext.recentInsights ?? [];
  const updatedInsights = [insight, ...currentInsights].slice(0, maxInsights);

  return updateSharedContext(store, {
    recentInsights: updatedInsights,
  });
}

/**
 * Get insights relevant to a specific agent.
 */
export function getInsightsForAgent(
  store: UserConversationStore,
  agentId: AgentType,
): AgentInsight[] {
  const insights = store.sharedContext.recentInsights ?? [];
  return insights.filter(
    (insight) =>
      insight.agentId !== agentId && // Not from the same agent
      (!insight.relevantTo || insight.relevantTo.includes(agentId)),
  );
}

/**
 * Export a session as Markdown.
 */
export function exportSessionAsMarkdown(session: AgentSession): string {
  const lines: string[] = [
    `# ${session.agentId.replace('_', ' ').toUpperCase()} Conversation`,
    '',
    `**Session ID:** ${session.id}`,
    `**Created:** ${new Date(session.createdAt).toLocaleString()}`,
    `**Messages:** ${session.messageCount}`,
    '',
    '---',
    '',
  ];

  for (const message of session.messages) {
    const role = message.role === 'user' ? '**You**' : '**Agent**';
    const time = new Date(message.timestamp).toLocaleTimeString();

    lines.push(`### ${role} (${time})`);
    lines.push('');
    lines.push(message.content);
    lines.push('');

    if (message.toolCalls && message.toolCalls.length > 0) {
      lines.push('**Tool Calls:**');
      for (const tc of message.toolCalls) {
        lines.push(`- \`${tc.name}\`: ${JSON.stringify(tc.args)}`);
      }
      lines.push('');
    }
  }

  return lines.join('\n');
}

/**
 * Export a session as JSON.
 */
export function exportSessionAsJSON(session: AgentSession): string {
  return JSON.stringify(session, null, 2);
}

/**
 * Get storage usage statistics.
 */
export function getStorageStats(userId: string): {
  used: number;
  available: number;
  sessionCount: number;
  messageCount: number;
} {
  if (!isStorageAvailable()) {
    return { used: 0, available: 0, sessionCount: 0, messageCount: 0 };
  }

  const key = STORAGE_KEYS.sessions(userId);
  const stored = localStorage.getItem(key);
  const usedBytes = stored ? new Blob([stored]).size : 0;

  // Estimate available (localStorage typically ~5MB)
  const maxBytes = 5 * 1024 * 1024;
  const availableBytes = maxBytes - usedBytes;

  let sessionCount = 0;
  let messageCount = 0;

  if (stored) {
    try {
      const store = JSON.parse(stored) as UserConversationStore;
      for (const agentId of Object.keys(store.sessions)) {
        const session = store.sessions[agentId as AgentType];
        if (session) {
          sessionCount++;
          messageCount += session.messages.length;
        }
      }
    } catch {
      // Ignore parse errors
    }
  }

  return {
    used: usedBytes,
    available: availableBytes,
    sessionCount,
    messageCount,
  };
}

/**
 * Build context string for agent prompt from shared context and relevant insights.
 */
export function buildContextPrompt(
  store: UserConversationStore,
  agentId: AgentType,
): string | undefined {
  const parts: string[] = [];

  // Add current workflow context
  if (store.sharedContext.currentWorkflow) {
    const wf = store.sharedContext.currentWorkflow;
    parts.push(
      `Current Workflow: "${wf.title}" (Status: ${wf.status}${wf.acquisitionType ? `, Type: ${wf.acquisitionType}` : ''})`,
    );
  }

  // Add recent documents
  if (store.sharedContext.recentDocuments?.length) {
    const docs = store.sharedContext.recentDocuments.slice(0, 3);
    parts.push(`Recent Documents: ${docs.map((d) => d.title).join(', ')}`);
  }

  // Add relevant insights from other agents
  const insights = getInsightsForAgent(store, agentId);
  if (insights.length > 0) {
    parts.push('Recent Insights from Other Agents:');
    for (const insight of insights.slice(0, 3)) {
      parts.push(`- ${insight.agentName}: ${insight.summary}`);
    }
  }

  return parts.length > 0 ? parts.join('\n') : undefined;
}
