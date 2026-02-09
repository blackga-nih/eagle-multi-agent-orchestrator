/**
 * Conversation Persistence Types
 *
 * Types for managing persistent agent conversations
 * with cross-agent context sharing.
 */

import { AgentType, AgentMessage, ToolResult } from './mcp';
import { UserRole } from './schema';

/**
 * A persistent conversation session with a specific agent.
 */
export interface AgentSession {
  id: string;
  userId: string;
  agentId: AgentType;
  messages: AgentMessage[];
  toolResults: ToolResult[];
  createdAt: string; // ISO string for serialization
  updatedAt: string;
  messageCount: number;
}

/**
 * Context that can be shared across agent conversations.
 */
export interface SharedContext {
  currentWorkflow?: {
    id: string;
    title: string;
    status: string;
    acquisitionType?: string;
  };
  recentDocuments?: {
    id: string;
    title: string;
    type: string;
  }[];
  userPreferences?: Record<string, unknown>;
  recentInsights?: AgentInsight[];
}

/**
 * An insight extracted from an agent conversation
 * that may be relevant to other agents.
 */
export interface AgentInsight {
  agentId: AgentType;
  agentName: string;
  summary: string;
  timestamp: string;
  relevantTo?: AgentType[];
}

/**
 * All conversation sessions for a user.
 */
export interface UserConversationStore {
  userId: string;
  sessions: Record<AgentType, AgentSession | null>;
  sharedContext: SharedContext;
  lastUpdated: string;
}

/**
 * Storage operation result.
 */
export interface StorageResult<T> {
  success: boolean;
  data?: T;
  error?: string;
}

/**
 * Options for conversation operations.
 */
export interface ConversationOptions {
  maxMessages?: number; // Max messages to keep (default: 100)
  maxToolResults?: number; // Max tool results (default: 50)
  autoSave?: boolean; // Auto-save on changes (default: true)
}

/**
 * Default conversation options.
 */
export const DEFAULT_CONVERSATION_OPTIONS: ConversationOptions = {
  maxMessages: 100,
  maxToolResults: 50,
  autoSave: true,
};

/**
 * Storage key generator functions.
 */
export const STORAGE_KEYS = {
  sessions: (userId: string) => `eagle_agent_sessions_${userId}`,
  context: (userId: string) => `eagle_shared_context_${userId}`,
  settings: (userId: string) => `eagle_user_settings_${userId}`,
  version: () => 'eagle_storage_version',
};

/**
 * Current storage schema version.
 * Increment when breaking changes are made.
 */
export const STORAGE_VERSION = 1;

/**
 * Empty session factory.
 */
export function createEmptySession(userId: string, agentId: AgentType): AgentSession {
  const now = new Date().toISOString();
  return {
    id: `${userId}_${agentId}_${Date.now()}`,
    userId,
    agentId,
    messages: [],
    toolResults: [],
    createdAt: now,
    updatedAt: now,
    messageCount: 0,
  };
}

/**
 * Empty store factory.
 */
export function createEmptyStore(userId: string): UserConversationStore {
  return {
    userId,
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
