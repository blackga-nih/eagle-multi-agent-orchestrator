'use client';

import { useState, useCallback, useRef } from 'react';
import { StreamEvent, AuditLogEntry, parseStreamEvent, streamEventToMessage, Message } from '@/types/stream';
import { generateUUID } from '@/lib/uuid';

const API_URL = '/api/invoke';

export interface UseAgentStreamOptions {
  onMessage?: (message: Message) => void;
  onEvent?: (event: StreamEvent) => void;
  onComplete?: () => void;
  onError?: (error: string) => void;
  getToken?: () => Promise<string>;
}

export interface UseAgentStreamReturn {
  sendQuery: (query: string, sessionId?: string) => Promise<void>;
  isStreaming: boolean;
  logs: AuditLogEntry[];
  lastMessage: Message | null;
  clearLogs: () => void;
  error: string | null;
  addUserInputLog: (content: string) => void;
  addFormSubmitLog: (formType: string, data: Record<string, unknown>, summary?: string) => void;
}

/**
 * Custom hook for streaming multi-agent events from the FastAPI backend.
 *
 * Handles:
 * - SSE streaming via /api/invoke proxy route
 * - Parsing events into typed StreamEvent objects
 * - Converting text events to Message objects
 * - JWT authentication via getToken callback
 * - Collecting all events for audit logging
 */
export function useAgentStream(options: UseAgentStreamOptions = {}): UseAgentStreamReturn {
  const [isStreaming, setIsStreaming] = useState(false);
  const [logs, setLogs] = useState<AuditLogEntry[]>([]);
  const [lastMessage, setLastMessage] = useState<Message | null>(null);
  const [error, setError] = useState<string | null>(null);

  const eventCountRef = useRef(0);
  const abortControllerRef = useRef<AbortController | null>(null);

  const clearLogs = useCallback(() => {
    setLogs([]);
    setLastMessage(null);
    setError(null);
    eventCountRef.current = 0;
  }, []);

  const sendQuery = useCallback(async (query: string, sessionId?: string) => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    abortControllerRef.current = new AbortController();
    setIsStreaming(true);
    setError(null);

    const finalSessionId = sessionId || generateUUID();

    try {
      // Build headers with JWT if available
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
      };

      if (options.getToken) {
        const token = await options.getToken();
        if (token) {
          headers['Authorization'] = `Bearer ${token}`;
        }
      }

      const response = await fetch(API_URL, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          query,
          session_id: finalSessionId,
        }),
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Backend error: ${response.status} - ${errorText}`);
      }

      const contentType = response.headers.get('content-type');

      if (contentType?.includes('text/event-stream')) {
        const reader = response.body?.getReader();
        if (!reader) throw new Error('No response body');

        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const data = line.slice(6).trim();
              if (data) {
                processEventData(data);
              }
            }
          }
        }
      } else {
        const text = await response.text();
        const lines = text.split('\n');

        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed.startsWith('data: ')) {
            const data = trimmed.slice(6);
            if (data) {
              processEventData(data);
            }
          } else if (trimmed.startsWith('{')) {
            processEventData(trimmed);
          }
        }
      }

      options.onComplete?.();
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') {
        return;
      }

      const errorMessage = err instanceof Error ? err.message : 'Unknown error';
      setError(errorMessage);
      options.onError?.(errorMessage);
    } finally {
      setIsStreaming(false);
    }

    function processEventData(data: string) {
      const event = parseStreamEvent(data);
      if (!event) return;

      const logEntry: AuditLogEntry = {
        ...event,
        id: `log-${eventCountRef.current++}`,
      };

      setLogs(prev => [...prev, logEntry]);
      options.onEvent?.(event);

      if (event.type === 'text') {
        const message = streamEventToMessage(event, logEntry.id);
        if (message) {
          setLastMessage(message);
          options.onMessage?.(message);
        }
      }

      if (event.type === 'error') {
        setError(event.content || 'Unknown error');
        options.onError?.(event.content || 'Unknown error');
      }
    }
  }, [options]);

  const addUserInputLog = useCallback((content: string) => {
    const entry: AuditLogEntry = {
      id: `log-${eventCountRef.current++}`,
      type: 'text',
      agent_id: 'user',
      agent_name: 'User',
      content,
      timestamp: new Date().toISOString(),
    };
    setLogs(prev => [...prev, entry]);
  }, []);

  const addFormSubmitLog = useCallback((formType: string, data: Record<string, unknown>, summary?: string) => {
    const entry: AuditLogEntry = {
      id: `log-${eventCountRef.current++}`,
      type: 'metadata',
      agent_id: 'user',
      agent_name: 'User',
      content: summary || `Form submitted: ${formType}`,
      metadata: { formType, ...data },
      timestamp: new Date().toISOString(),
    };
    setLogs(prev => [...prev, entry]);
  }, []);

  return {
    sendQuery,
    isStreaming,
    logs,
    lastMessage,
    clearLogs,
    error,
    addUserInputLog,
    addFormSubmitLog,
  };
}

/**
 * Check if the backend is healthy via the API route.
 */
export async function checkBackendHealth(): Promise<boolean> {
  try {
    const response = await fetch(API_URL, {
      method: 'GET',
      signal: AbortSignal.timeout(5000),
    });
    if (response.ok) {
      const data = await response.json();
      return data.status === 'healthy';
    }
    return false;
  } catch {
    return false;
  }
}
