'use client';

import { useState, useEffect, useCallback } from 'react';
import { ChatSession } from '@/components/layout/chat-history-dropdown';
import { DocumentInfo, Message } from '@/types/chat';
import { AcquisitionData } from '@/types/schema';
import { generateUUID } from '@/lib/uuid';

const STORAGE_KEY = 'eagle_chat_sessions';
const CURRENT_SESSION_KEY = 'eagle_current_session';

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

interface UseSessionPersistenceReturn {
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
}

interface ParsedIntent {
  projectName?: string;
  documentType?: string;
  action?: 'document' | 'plan' | 'intake' | 'question';
}

function parseUserIntent(message: string): ParsedIntent {
  const result: ParsedIntent = {};

  // Detect slash commands
  if (message.startsWith('/document')) {
    result.action = 'document';
  } else if (message.startsWith('/plan') || message.startsWith('/quick-plan')) {
    result.action = 'plan';
  } else if (message.startsWith('/oa-intake')) {
    result.action = 'intake';
  }

  // Extract document type from keywords
  const docTypePatterns: Record<string, string> = {
    'sow|statement of work': 'SOW',
    'ige|igce|cost estimate': 'IGCE',
    'acquisition plan': 'Acquisition Plan',
    'market research': 'Market Research',
    'justification|j&a': 'Justification',
  };

  const lowerMsg = message.toLowerCase();
  for (const [pattern, label] of Object.entries(docTypePatterns)) {
    if (new RegExp(pattern).test(lowerMsg)) {
      result.documentType = label;
      break;
    }
  }

  // Extract project name using patterns like:
  // "for a project called X", "for X project", "called X", "named X"
  const projectPatterns = [
    /(?:project|program)\s+(?:called|named)\s+["']?([^"'.,]+)["']?/i,
    /(?:called|named)\s+["']?([^"'.,]+)["']?/i,
    /for\s+(?:the\s+)?["']?([A-Z][A-Za-z0-9\s]+?)["']?\s+(?:project|program|initiative)/i,
    /["']([^"']+)["']\s+(?:sow|igce|ige|acquisition)/i,
  ];

  for (const pattern of projectPatterns) {
    const match = message.match(pattern);
    if (match) {
      result.projectName = match[1].trim();
      break;
    }
  }

  return result;
}

function formatDocType(type: string): string {
  const labels: Record<string, string> = {
    sow: 'SOW',
    igce: 'IGCE',
    acquisition_plan: 'Acquisition Plan',
    market_research: 'Market Research',
    justification: 'Justification',
    funding_doc: 'Funding Document',
  };
  return labels[type] || type.toUpperCase();
}

function generateSessionTitle(
  messages: Message[],
  acquisitionData: AcquisitionData,
  documents?: Record<string, { document_type?: string; title?: string }[]>,
): string {
  // Priority 1: If we have documents, use document metadata
  if (documents && Object.keys(documents).length > 0) {
    const allDocs = Object.values(documents).flat();
    const firstDoc = allDocs[0];
    if (firstDoc && firstDoc.document_type) {
      const docLabel = formatDocType(firstDoc.document_type);
      const projectName = firstDoc.title?.replace(/\s*(SOW|IGCE|Plan).*$/i, '').trim();
      if (projectName && projectName !== docLabel) {
        return `${projectName} - ${docLabel}`;
      }
      return docLabel;
    }
  }

  // Priority 2: Parse first user message for intent
  const firstUserMessage = messages.find((m) => m.role === 'user');
  if (firstUserMessage) {
    const parsed = parseUserIntent(firstUserMessage.content);

    if (parsed.projectName && parsed.documentType) {
      return `${parsed.projectName} - ${parsed.documentType}`;
    }
    if (parsed.projectName) {
      return parsed.projectName;
    }
    if (parsed.documentType) {
      return `New ${parsed.documentType}`;
    }
  }

  // Priority 3: Use acquisition requirement (cleaned)
  if (acquisitionData.requirement) {
    // Remove slash commands and extract meaningful content
    const cleaned = acquisitionData.requirement
      .replace(/^\/\w+\s*/, '') // Remove slash command
      .replace(/^I need (an?|the)\s*/i, '') // Remove "I need a/an/the"
      .trim();

    if (cleaned.length > 0) {
      const words = cleaned.split(' ').slice(0, 4).join(' ');
      return words + (cleaned.length > words.length ? '...' : '');
    }
  }

  // Fallback
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

  const saveSession = useCallback(
    (
      messages: Message[],
      acquisitionData: AcquisitionData,
      documents?: Record<string, DocumentInfo[]>,
    ) => {
      if (!currentSessionId || messages.length === 0) return;

      try {
        const stored = localStorage.getItem(STORAGE_KEY);
        const allSessions: Record<string, SessionData> = stored ? JSON.parse(stored) : {};

        const existingSession = allSessions[currentSessionId];
        const now = new Date().toISOString();

        // Strip content from documents to avoid localStorage bloat —
        // card rendering only needs metadata; full content lives in sessionStorage.
        let strippedDocs: Record<string, DocumentInfo[]> | undefined;
        if (documents && Object.keys(documents).length > 0) {
          strippedDocs = {};
          for (const [msgId, docs] of Object.entries(documents)) {
            strippedDocs[msgId] = docs.map(({ content, ...meta }) => meta);
          }
        }

        const sessionData: SessionData = {
          id: currentSessionId,
          title:
            existingSession?.title || generateSessionTitle(messages, acquisitionData, strippedDocs),
          summary: generateSessionSummary(acquisitionData),
          messages: messages.map((m) => ({
            ...m,
            timestamp: m.timestamp instanceof Date ? m.timestamp.toISOString() : m.timestamp,
          })) as any,
          acquisitionData,
          documents: strippedDocs,
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
    },
    [currentSessionId],
  );

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

  const deleteSession = useCallback(
    (sessionId: string) => {
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

        // Delete from backend (also detaches linked packages) — fire-and-forget
        fetch(`/api/sessions/${encodeURIComponent(sessionId)}`, {
          method: 'DELETE',
        }).catch((err) =>
          console.error('[use-session-persistence] deleteSession backend sync error:', err),
        );
      } catch (error) {
        console.error('Error deleting session:', error);
      }
    },
    [currentSessionId, createNewSession],
  );

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
            s.id === sessionId ? { ...s, status: 'completed' as const, updatedAt: new Date() } : s,
          ),
        );
      }
    } catch (error) {
      console.error('Error marking session complete:', error);
    }
  }, []);

  const renameSession = useCallback((sessionId: string, newTitle: string) => {
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
            s.id === sessionId ? { ...s, title: newTitle, updatedAt: new Date() } : s,
          ),
        );

        // Sync to backend if available
        fetch(`/api/sessions/${sessionId}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title: newTitle }),
        }).catch((err) => console.error('Error syncing session title to backend:', err));
      }
    } catch (error) {
      console.error('Error renaming session:', error);
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
    renameSession,
  };
}
