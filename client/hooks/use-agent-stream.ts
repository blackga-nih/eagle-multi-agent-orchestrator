'use client';

import { useState, useCallback, useRef } from 'react';
import { StreamEvent, AuditLogEntry, parseStreamEvent, streamEventToMessage } from '@/types/stream';
import { Message, DocumentInfo } from '@/types/chat';
import { generateUUID } from '@/lib/uuid';
import {
  CLIENT_SIDE_TOOLS,
  executeClientTool,
  ClientToolResult,
} from '@/lib/client-tools';

const API_URL = '/api/invoke';

/** Payload emitted to onToolUse for every tool invocation detected in the stream. */
export interface ToolUseEvent {
  toolName: string;
  input: Record<string, unknown>;
  toolUseId: string;
  isClientSide: boolean;
  /** Undefined while running; populated once execution completes (client-side only). */
  result?: ClientToolResult;
  /** Execution target tag. */
  executionTarget: 'client' | 'server';
}

/** Server-side tool result received via SSE tool_result event. */
export interface ServerToolResult {
  toolName: string;
  result: { success: boolean; result: unknown; error?: string };
}

export interface UseAgentStreamOptions {
  onMessage?: (message: Message) => void;
  onEvent?: (event: StreamEvent) => void;
  /** Called when the stream finishes. Includes accumulated server-side tool results. */
  onComplete?: (toolResults?: ServerToolResult[]) => void;
  onError?: (error: string) => void;
  onDocumentGenerated?: (doc: DocumentInfo) => void;
  /**
   * Called for every tool_use event.
   * Fired first with result=undefined (tool is starting), then again once
   * a client-side tool finishes (result is populated).
   */
  onToolUse?: (event: ToolUseEvent) => void;
  getToken?: () => Promise<string>;
  /** Active session ID — forwarded to client tools for localStorage namespacing. */
  sessionId?: string;
  /** Optional active package context to route create_document into package mode. */
  packageId?: string;
}

export interface UseAgentStreamReturn {
  sendQuery: (query: string, sessionId?: string, packageId?: string) => Promise<void>;
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

    // Reject error responses (e.g. "Unknown document type")
    if (data.error) return null;

    const normalizedDocType = data.doc_type ?? data.document_type;
    // Require at least a real title or document type — reject empty/stub results
    if (!data.title && !normalizedDocType && !data.s3_key) return null;

    return {
      document_id: data.document_id ?? data.s3_key ?? undefined,
      package_id: data.package_id ?? undefined,
      document_type: normalizedDocType ?? 'unknown',
      doc_type: normalizedDocType ?? undefined,
      title: data.title ?? normalizedDocType ?? 'Document',
      content: data.content ?? undefined,
      mode: data.mode ?? undefined,
      status: data.status ?? undefined,
      version: data.version ?? undefined,
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
 * - Client-side tool execution (think, code, editor) via executeClientTool()
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

  const sendQuery = useCallback(async (query: string, sessionId?: string, packageId?: string) => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    abortControllerRef.current = new AbortController();
    setIsStreaming(true);
    setError(null);

    const finalSessionId = sessionId || generateUUID();
    const activePackageId = packageId || options.packageId;
    const queryStartTime = new Date();
    let accumulatedText = '';
    // Stable ID used for the single streaming assistant message.
    // All text chunks for one response share this ID so the UI upserts
    // rather than appending a new bubble per chunk.
    const streamingMsgId = `stream-${Date.now()}`;
    let shouldFetchDocs = false;
    const emittedDocKeys = new Set<string>();
    // Accumulate server-side tool results during streaming — merged at onComplete
    const serverToolResults: ServerToolResult[] = [];

    // The session to use for client tool localStorage namespacing.
    // Prefer the sessionId passed to sendQuery; fall back to options.sessionId.
    const activeSessionId = finalSessionId || options.sessionId;

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
          package_id: activePackageId,
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
                await processEventData(data, activeSessionId);
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
              await processEventData(data, activeSessionId);
            }
          } else if (trimmed.startsWith('{')) {
            await processEventData(trimmed, activeSessionId);
          }
        }
      }

      // After event processing: fetch documents from S3 via API if
      // create_document was called but tool_result events were not received
      // (REST fallback path where tool results are lost).
      if (shouldFetchDocs && options.onDocumentGenerated) {
        await fetchCreatedDocuments(headers, queryStartTime, emittedDocKeys);
      }

      options.onComplete?.(serverToolResults.length > 0 ? serverToolResults : undefined);
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

    async function processEventData(data: string, sid: string | undefined) {
      const event = parseStreamEvent(data);
      if (!event) return;

      const logEntry: AuditLogEntry = {
        ...event,
        id: `log-${eventCountRef.current++}`,
      };

      setLogs(prev => [...prev, logEntry]);
      options.onEvent?.(event);

      // Handle text messages — accumulate into a single streaming bubble.
      // The backend sends one event per text chunk (and an empty one as a
      // connection handshake). We use a stable streamingMsgId so the UI can
      // upsert the same message rather than appending a new one each chunk.
      if (event.type === 'text') {
        accumulatedText += event.content || '';
        if (!accumulatedText) return; // skip empty handshake event
        const message: Message = {
          id: streamingMsgId,
          role: 'assistant',
          content: accumulatedText,
          timestamp: new Date(event.timestamp),
          reasoning: event.reasoning,
          agent_id: event.agent_id,
          agent_name: event.agent_name,
        };
        setLastMessage(message);
        options.onMessage?.(message);
      }

      // Handle tool_use events — dispatch client-side tools or emit server notification.
      if (event.type === 'tool_use' && event.tool_use) {
        const toolName = event.tool_use.name;
        const toolInput = (event.tool_use.input ?? {}) as Record<string, unknown>;
        const toolUseId = event.tool_use.tool_use_id ?? `tool-${Date.now()}`;
        const isClientSide = CLIENT_SIDE_TOOLS.has(toolName);

        // Notify UI that the tool is starting
        options.onToolUse?.({
          toolName,
          input: toolInput,
          toolUseId,
          isClientSide,
          executionTarget: isClientSide ? 'client' : 'server',
          result: undefined,
        });

        if (isClientSide) {
          // Execute the tool in the browser and then notify UI with the result
          const result = await executeClientTool(toolName, toolInput, sid);
          options.onToolUse?.({
            toolName,
            input: toolInput,
            toolUseId,
            isClientSide: true,
            executionTarget: 'client',
            result,
          });
        }
      }

      // Handle tool_result events — accumulate for merge at onComplete
      if (event.type === 'tool_result' && event.tool_result) {
        const tr = event.tool_result;

        // Accumulate for batch merge when stream completes
        serverToolResults.push({
          toolName: tr.name,
          result: { success: true, result: tr.result },
        });

        // Extract document info for create_document
        const docInfo = parseDocumentToolResult(event);
        if (docInfo) {
          if (docInfo.s3_key) emittedDocKeys.add(docInfo.s3_key);
          if (docInfo.document_id) emittedDocKeys.add(docInfo.document_id);
          setLastDocument(docInfo);
          options.onDocumentGenerated?.(docInfo);
        }
      }

      // Handle complete event — REST/fallback path
      // When tool_result events were already received (streaming path), skip
      // text-based parsing to avoid duplicate document cards.
      if (event.type === 'complete') {
        const toolsCalled = event.metadata?.tools_called;
        if (Array.isArray(toolsCalled) && toolsCalled.includes('create_document')) {
          const expectedCount = toolsCalled.filter((t: string) => t === 'create_document').length;

          // Skip text parsing if tool_result events already provided the docs
          if (emittedDocKeys.size < expectedCount) {
            const docs = parseDocumentsFromText(accumulatedText);
            for (const doc of docs) {
              // Skip if this filename matches an already-emitted key
              const name = doc.s3_key || '';
              const alreadyEmitted = [...emittedDocKeys].some(k => k.endsWith(name));
              if (alreadyEmitted) continue;

              if (doc.s3_key) emittedDocKeys.add(doc.s3_key);
              setLastDocument(doc);
              options.onDocumentGenerated?.(doc);
            }

            // If still fewer docs than expected, flag for API fallback
            if (emittedDocKeys.size < expectedCount) {
              shouldFetchDocs = true;
            }
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

            // Skip documents without a recognizable type — avoids "unknown / Untitled" cards
            const docType = typeInfo?.type || doc.type;
            if (!docType) continue;

            const docInfo: DocumentInfo = {
              document_id: name || key,
              document_type: docType,
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
