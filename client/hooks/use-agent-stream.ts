'use client';

import { useState, useCallback, useRef } from 'react';
import { StreamEvent, AuditLogEntry, parseStreamEvent, streamEventToMessage } from '@/types/stream';
import { Message, DocumentInfo } from '@/types/chat';
import { generateUUID } from '@/lib/uuid';

const API_URL = '/api/invoke';

export interface UseAgentStreamOptions {
  onMessage?: (message: Message) => void;
  onEvent?: (event: StreamEvent) => void;
  onComplete?: () => void;
  onError?: (error: string) => void;
  onDocumentGenerated?: (doc: DocumentInfo) => void;
  getToken?: () => Promise<string>;
}

export interface UseAgentStreamReturn {
  sendQuery: (query: string, sessionId?: string) => Promise<void>;
  isStreaming: boolean;
  logs: AuditLogEntry[];
  lastMessage: Message | null;
  lastDocument: DocumentInfo | null;
  clearLogs: () => void;
  error: string | null;
  addUserInputLog: (content: string) => void;
  addFormSubmitLog: (formType: string, data: Record<string, unknown>, summary?: string) => void;
}

/**
 * Try to parse a create_document tool_result into a DocumentInfo.
 * Works when the streaming endpoint sends real tool_result events.
 */
function parseDocumentToolResult(event: StreamEvent): DocumentInfo | null {
  if (event.type !== 'tool_result') return null;

  const tr = event.tool_result;
  if (!tr || tr.name !== 'create_document') return null;

  try {
    const data = typeof tr.result === 'string' ? JSON.parse(tr.result) : tr.result;
    if (!data || typeof data !== 'object') return null;

    return {
      document_id: data.document_id ?? data.s3_key ?? undefined,
      document_type: data.document_type ?? 'unknown',
      title: data.title ?? 'Untitled Document',
      content: data.content ?? undefined,
      status: data.status ?? undefined,
      word_count: data.word_count ?? undefined,
      generated_at: data.generated_at ?? undefined,
      s3_key: data.s3_key ?? undefined,
      s3_location: data.s3_location ?? undefined,
    };
  } catch {
    return null;
  }
}

/** Known document type prefixes in S3 filenames. */
const DOC_TYPE_MAP: Record<string, { type: string; label: string }> = {
  sow: { type: 'sow', label: 'Statement of Work' },
  igce: { type: 'igce', label: 'Independent Government Cost Estimate' },
  market_research: { type: 'market_research', label: 'Market Research Report' },
  justification: { type: 'justification', label: 'Justification & Approval' },
  acquisition_plan: { type: 'acquisition_plan', label: 'Acquisition Plan' },
  eval_criteria: { type: 'eval_criteria', label: 'Evaluation Criteria' },
  security_checklist: { type: 'security_checklist', label: 'Security Checklist' },
  section_508: { type: 'section_508', label: 'Section 508 Compliance' },
  cor_certification: { type: 'cor_certification', label: 'COR Certification' },
  contract_type_justification: { type: 'contract_type_justification', label: 'Contract Type Justification' },
};

/**
 * Fallback: extract DocumentInfo from the assistant's text response when
 * the REST endpoint was used (no tool_result events, only final text + complete).
 *
 * Parses S3 location references like "sow_20260212_124538.md" from the text
 * and infers document type from the filename prefix.
 */
function parseDocumentsFromText(text: string): DocumentInfo[] {
  const docs: DocumentInfo[] = [];
  // Match S3 filenames like sow_20260212_124538.md or igce_20260212_124539.md
  const filePattern = /(\w+?)_(\d{8}_\d{6})\.md/g;
  let match: RegExpExecArray | null;

  while ((match = filePattern.exec(text)) !== null) {
    const prefix = match[1].toLowerCase();
    const filename = match[0];
    const typeInfo = DOC_TYPE_MAP[prefix];

    if (typeInfo) {
      docs.push({
        document_id: filename,
        document_type: typeInfo.type,
        title: typeInfo.label,
        s3_key: filename,
        status: 'saved',
        generated_at: new Date().toISOString(),
      });
    }
  }

  return docs;
}

/** Map of keyword patterns to document types for text-based detection. */
const DOC_KEYWORD_PATTERNS: Array<{ pattern: RegExp; type: string; label: string; template: string }> = [
  { pattern: /statement\s+of\s+work|(\b)sow(\b)/i, type: 'sow', label: 'Statement of Work', template: 'sow-template.md' },
  { pattern: /igce|cost\s+estimate|independent\s+government/i, type: 'igce', label: 'Cost Estimate (IGCE)', template: 'igce-template.md' },
  { pattern: /market\s+research/i, type: 'market_research', label: 'Market Research Report', template: 'market-research-template.md' },
  { pattern: /acquisition\s+plan/i, type: 'acquisition_plan', label: 'Acquisition Plan', template: 'acquisition-plan-template.md' },
  { pattern: /justification\s*((&|and)\s*approval)?|(\b)j\s*(&|and)\s*a(\b)|sole\s*source/i, type: 'justification', label: 'Justification & Approval', template: 'justification-template.md' },
];

/**
 * Detect document types mentioned in the response text via keyword matching.
 * Used as a last-resort fallback when S3 is unavailable and no filenames
 * appear in the text. Returns DocumentInfo objects pointing to local templates.
 */
function detectDocumentTypesFromText(text: string): DocumentInfo[] {
  const docs: DocumentInfo[] = [];
  const seen = new Set<string>();

  for (const { pattern, type, label, template } of DOC_KEYWORD_PATTERNS) {
    if (pattern.test(text) && !seen.has(type)) {
      seen.add(type);
      docs.push({
        document_id: template,
        document_type: type,
        title: label,
        s3_key: template,
        status: 'template',
        generated_at: new Date().toISOString(),
      });
    }
  }

  return docs;
}

/**
 * Custom hook for streaming multi-agent events from the FastAPI backend.
 *
 * Handles:
 * - SSE streaming via /api/invoke proxy route
 * - Parsing events into typed StreamEvent objects
 * - Converting text events to Message objects
 * - Detecting create_document tool results and emitting DocumentInfo
 * - JWT authentication via getToken callback
 * - Collecting all events for audit logging
 */
export function useAgentStream(options: UseAgentStreamOptions = {}): UseAgentStreamReturn {
  const [isStreaming, setIsStreaming] = useState(false);
  const [logs, setLogs] = useState<AuditLogEntry[]>([]);
  const [lastMessage, setLastMessage] = useState<Message | null>(null);
  const [lastDocument, setLastDocument] = useState<DocumentInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  const eventCountRef = useRef(0);
  const abortControllerRef = useRef<AbortController | null>(null);

  const clearLogs = useCallback(() => {
    setLogs([]);
    setLastMessage(null);
    setLastDocument(null);
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
    const queryStartTime = new Date();
    let accumulatedText = '';
    let shouldFetchDocs = false;
    const emittedDocKeys = new Set<string>();

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

      // After event processing: fetch documents from S3 via API if
      // create_document was called but tool_result events were not received
      // (REST fallback path where tool results are lost).
      if (shouldFetchDocs && options.onDocumentGenerated) {
        await fetchCreatedDocuments(headers, queryStartTime, emittedDocKeys);
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

      // Handle text messages
      if (event.type === 'text') {
        accumulatedText += event.content || '';
        const message = streamEventToMessage(event, logEntry.id);
        if (message) {
          setLastMessage(message);
          options.onMessage?.(message);
        }
      }

      // Handle create_document tool results (streaming path)
      if (event.type === 'tool_result') {
        const docInfo = parseDocumentToolResult(event);
        if (docInfo) {
          if (docInfo.s3_key) emittedDocKeys.add(docInfo.s3_key);
          if (docInfo.document_id) emittedDocKeys.add(docInfo.document_id);
          setLastDocument(docInfo);
          options.onDocumentGenerated?.(docInfo);
        }
      }

      // Handle complete event — REST fallback path
      // When streaming fails and the REST endpoint is used, tool_result events
      // are not sent. Instead the complete event carries tools_called metadata.
      if (event.type === 'complete') {
        const toolsCalled = event.metadata?.tools_called;
        if (Array.isArray(toolsCalled) && toolsCalled.includes('create_document')) {
          const expectedCount = toolsCalled.filter((t: string) => t === 'create_document').length;

          // Try immediate text-based parsing first (S3 filename patterns)
          const docs = parseDocumentsFromText(accumulatedText);
          for (const doc of docs) {
            if (doc.s3_key) emittedDocKeys.add(doc.s3_key);
            setLastDocument(doc);
            options.onDocumentGenerated?.(doc);
          }

          // If text parsing found fewer docs than expected, flag for API + template fallback
          if (docs.length < expectedCount) {
            shouldFetchDocs = true;
          }
        }
      }

      if (event.type === 'error') {
        setError(event.content || 'Unknown error');
        options.onError?.(event.content || 'Unknown error');
      }
    }

    async function fetchCreatedDocuments(
      headers: Record<string, string>,
      startTime: Date,
      alreadyEmitted: Set<string>,
    ) {
      let foundFromApi = false;

      // Phase 1: Try fetching real documents from the backend (S3)
      try {
        const res = await fetch('/api/documents', {
          method: 'GET',
          headers,
          signal: AbortSignal.timeout(10000),
        });

        if (res.ok) {
          const data = await res.json();
          const docs: Array<{
            key?: string;
            name?: string;
            size_bytes?: number;
            last_modified?: string;
            type?: string;
          }> = data.documents || [];

          for (const doc of docs) {
            const key = doc.key || '';
            const name = doc.name || '';

            // Skip already emitted via streaming or text parsing
            if (alreadyEmitted.has(name) || alreadyEmitted.has(key)) continue;

            // Only include documents modified after the query started
            if (doc.last_modified) {
              const modified = new Date(doc.last_modified);
              if (modified < startTime) continue;
            }

            // Infer type from filename prefix
            const prefixMatch = name.match(/^(\w+?)_\d/);
            const prefix = prefixMatch?.[1]?.toLowerCase() || '';
            const typeInfo = DOC_TYPE_MAP[prefix];

            const docInfo: DocumentInfo = {
              document_id: name || key,
              document_type: typeInfo?.type || doc.type || 'unknown',
              title: typeInfo?.label || name || 'Document',
              s3_key: key,
              status: 'saved',
              generated_at: doc.last_modified,
            };

            alreadyEmitted.add(name || key);
            setLastDocument(docInfo);
            options.onDocumentGenerated?.(docInfo);
            foundFromApi = true;
          }
        }
      } catch {
        // S3/backend unavailable — fall through to template fallback
      }

      // Phase 2: Template fallback — detect document types from text
      // when S3 is unavailable or returned no new documents.
      if (!foundFromApi && accumulatedText) {
        const templateDocs = detectDocumentTypesFromText(accumulatedText);
        for (const doc of templateDocs) {
          if (doc.document_id && alreadyEmitted.has(doc.document_id)) continue;
          if (doc.document_id) alreadyEmitted.add(doc.document_id);
          setLastDocument(doc);
          options.onDocumentGenerated?.(doc);
        }
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
    lastDocument,
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
