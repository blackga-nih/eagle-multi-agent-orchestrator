/**
 * ChatStreamManager — multi-request SSE transport.
 *
 * Replaces the singleton `useAgentStream` hook for request lifecycle management.
 * Each session gets at most one active SSE request. Events are dispatched as
 * ChatRuntimeAction actions to the chat-runtime-context reducer.
 */

import { Dispatch } from 'react';
import { ChatRuntimeAction } from '@/contexts/chat-runtime-context';
import { StreamEvent, parseStreamEvent, AuditLogEntry } from '@/types/stream';
import { Message, DocumentInfo } from '@/types/chat';
import { CLIENT_SIDE_TOOLS, executeClientTool, ClientToolResult } from '@/lib/client-tools';
import { generateUUID } from '@/lib/uuid';
import { saveGeneratedDocument } from '@/lib/document-store';
import {
  saveCheckpoint,
  clearCheckpoint,
  type StreamingCheckpoint,
} from '@/lib/streaming-checkpoint';
import type { TrackedToolCall } from '@/components/chat-simple/simple-chat-interface';
import type { StateChangeEntry } from '@/contexts/chat-runtime-context';

const API_URL = '/api/invoke';

/** Known document type prefixes in S3 filenames. */
const DOC_TYPE_MAP: Record<string, { type: string; label: string }> = {
  ige: { type: 'igce', label: 'Independent Government Cost Estimate' },
  sow: { type: 'sow', label: 'Statement of Work' },
  igce: { type: 'igce', label: 'Independent Government Cost Estimate' },
  market_research: { type: 'market_research', label: 'Market Research Report' },
  justification: { type: 'justification', label: 'Justification & Approval' },
  acquisition_plan: { type: 'acquisition_plan', label: 'Acquisition Plan' },
  eval_criteria: { type: 'eval_criteria', label: 'Evaluation Criteria' },
  security_checklist: { type: 'security_checklist', label: 'Security Checklist' },
  section_508: { type: 'section_508', label: 'Section 508 Compliance' },
  cor_certification: { type: 'cor_certification', label: 'COR Certification' },
  contract_type_justification: {
    type: 'contract_type_justification',
    label: 'Contract Type Justification',
  },
};

function parseDocumentToolResult(event: StreamEvent): DocumentInfo | null {
  if (event.type !== 'tool_result') return null;
  const tr = event.tool_result;
  if (!tr || tr.name !== 'create_document') return null;
  try {
    const data = typeof tr.result === 'string' ? JSON.parse(tr.result) : tr.result;
    if (!data || typeof data !== 'object') return null;
    if (data.error) return null;
    const normalizedDocType = data.doc_type ?? data.document_type;
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

function parseDocumentsFromText(text: string): DocumentInfo[] {
  const docs: DocumentInfo[] = [];
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

export interface StartQueryParams {
  sessionId: string;
  query: string;
  packageId?: string;
  getToken: () => Promise<string>;
  dispatch: Dispatch<ChatRuntimeAction>;
  /** Callback to add audit log entries for the agent-logs panel. */
  onLog?: (entry: AuditLogEntry) => void;
  /** Callback when a message is committed (for persisting to IDB / sidebar title). */
  onMessageCommit?: (sessionId: string, message: Message) => void;
  /** Callback when document is generated (for localStorage persistence). */
  onDocumentGenerated?: (sessionId: string, doc: DocumentInfo) => void;
  /** Callback when a state_update metadata event arrives (package state). */
  onStateUpdate?: (metadata: Record<string, unknown>) => void;
}

interface ActiveRequest {
  sessionId: string;
  abortController: AbortController;
}

export class ChatStreamManager {
  private requests = new Map<string, ActiveRequest>(); // keyed by requestId
  private sessionToRequest = new Map<string, string>(); // sessionId → requestId

  /**
   * Start a new SSE request for a session.
   * Throws if the session already has an active request.
   * Returns the requestId.
   */
  startQuery(params: StartQueryParams): string {
    const {
      sessionId,
      query,
      packageId,
      getToken,
      dispatch,
      onLog,
      onDocumentGenerated,
      onStateUpdate,
    } = params;

    if (this.sessionToRequest.has(sessionId)) {
      throw new Error(`Session ${sessionId} already has an active request`);
    }

    const requestId = generateUUID();
    const streamingMsgId = `stream-${Date.now()}`;
    const abortController = new AbortController();

    this.requests.set(requestId, { sessionId, abortController });
    this.sessionToRequest.set(sessionId, requestId);

    dispatch({ type: 'generation/start', sessionId, requestId, streamingMsgId });

    // Fire-and-forget the async work
    this._runStream(requestId, streamingMsgId, params, abortController)
      .catch((err) => {
        if (err instanceof Error && err.name === 'AbortError') {
          // User clicked stop — transition state back to idle
          dispatch({ type: 'generation/complete', sessionId, requestId });
          return;
        }
        dispatch({
          type: 'generation/error',
          sessionId,
          requestId,
          error: err instanceof Error ? err.message : 'Unknown error',
        });
      })
      .finally(() => {
        this.requests.delete(requestId);
        if (this.sessionToRequest.get(sessionId) === requestId) {
          this.sessionToRequest.delete(sessionId);
        }
      });

    return requestId;
  }

  /** Abort the active request for a session. */
  stopQuery(sessionId: string): void {
    const requestId = this.sessionToRequest.get(sessionId);
    if (!requestId) return;
    const req = this.requests.get(requestId);
    if (!req) return;
    req.abortController.abort();
  }

  /** Check if a session has an active request. */
  isActive(sessionId: string): boolean {
    return this.sessionToRequest.has(sessionId);
  }

  // -----------------------------------------------------------------------
  // Internal streaming logic (extracted from use-agent-stream.ts)
  // -----------------------------------------------------------------------

  private async _runStream(
    requestId: string,
    streamingMsgId: string,
    params: StartQueryParams,
    abortController: AbortController,
  ) {
    const {
      sessionId,
      query,
      packageId,
      getToken,
      dispatch,
      onLog,
      onDocumentGenerated,
      onStateUpdate,
    } = params;
    let accumulatedText = '';
    let eventCount = 0;
    /** True after a tool_use/tool_result event — next text chunk needs a separator. */
    let toolBoundarySeen = false;
    /** RAF-based batching: coalesce rapid text chunks into fewer React state updates. */
    let pendingTextFlush = false;
    let latestTextEvent: {
      reasoning?: string;
      agent_id?: string;
      agent_name?: string;
      timestamp: string;
    } | null = null;
    const emittedDocKeys = new Set<string>();
    let shouldFetchDocs = false;
    const queryStartTime = new Date();
    /** ID of the last committed assistant message (set in generation/message). */
    let lastAssistantMsgId: string | null = null;

    // --- Streaming checkpoint tracking ---
    const cpToolCalls = new Map<string, TrackedToolCall>();
    const cpStateChanges: StateChangeEntry[] = [];
    const cpDocuments: DocumentInfo[] = [];
    let lastCheckpointTime = 0;
    const CHECKPOINT_INTERVAL_MS = 2_000;

    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    const token = await getToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const response = await fetch(API_URL, {
      method: 'POST',
      headers,
      body: JSON.stringify({ query, session_id: sessionId, package_id: packageId }),
      signal: abortController.signal,
    });

    if (!response.ok) {
      if (response.status === 401) {
        const { fireSessionExpired } = await import('@/contexts/auth-context');
        fireSessionExpired();
      }
      const errorText = await response.text();
      throw new Error(`Backend error: ${response.status} - ${errorText}`);
    }

    const contentType = response.headers.get('content-type');

    /** Write a checkpoint if enough time has elapsed. */
    const maybeCheckpoint = () => {
      const now = Date.now();
      if (now - lastCheckpointTime < CHECKPOINT_INTERVAL_MS) return;
      lastCheckpointTime = now;
      const cp: StreamingCheckpoint = {
        sessionId,
        requestId,
        streamingMsgId,
        text: accumulatedText,
        toolCalls: Array.from(cpToolCalls.values()),
        stateChanges: cpStateChanges,
        documents: cpDocuments,
        updatedAt: now,
      };
      saveCheckpoint(cp);
    };

    const processEvent = async (data: string) => {
      const event = parseStreamEvent(data);
      if (!event) return;

      // Emit log entry for the activity panel
      if (onLog) {
        const logEntry: AuditLogEntry = {
          ...event,
          id: `log-${eventCount++}`,
        };
        onLog(logEntry);
      }

      // --- Text ---
      if (event.type === 'text') {
        const chunk = event.content || '';
        if (!chunk && !accumulatedText) return;
        // Insert paragraph break when text resumes after a tool boundary
        if (chunk && toolBoundarySeen && accumulatedText && !/\s$/.test(accumulatedText)) {
          accumulatedText += '\n\n';
        }
        toolBoundarySeen = false;
        accumulatedText += chunk;
        if (!accumulatedText) return;
        lastAssistantMsgId = streamingMsgId;
        latestTextEvent = event;
        maybeCheckpoint();
        // Batch rapid text chunks into a single React state update per animation frame
        if (!pendingTextFlush) {
          pendingTextFlush = true;
          requestAnimationFrame(() => {
            pendingTextFlush = false;
            const ev = latestTextEvent;
            if (!ev) return;
            const message: Message = {
              id: streamingMsgId,
              role: 'assistant',
              content: accumulatedText,
              timestamp: new Date(ev.timestamp),
              reasoning: ev.reasoning,
              agent_id: ev.agent_id,
              agent_name: ev.agent_name,
            };
            dispatch({ type: 'generation/message', sessionId, requestId, message });
          });
        }
      }

      // --- Tool use ---
      if (event.type === 'tool_use' && event.tool_use) {
        const toolName = event.tool_use.name;
        const toolInput = (event.tool_use.input ?? {}) as Record<string, unknown>;
        const toolUseId = event.tool_use.tool_use_id ?? `tool-${Date.now()}`;
        const isClientSide = CLIENT_SIDE_TOOLS.has(toolName);
        const msgId = streamingMsgId;
        toolBoundarySeen = true;

        dispatch({
          type: 'generation/toolUse',
          sessionId,
          requestId,
          msgId,
          toolUseId,
          patch: {
            toolName,
            input: toolInput,
            status: isClientSide ? 'running' : 'pending',
            isClientSide,
            textSnapshotLength: accumulatedText.length,
          },
        });

        // Track for checkpoint
        cpToolCalls.set(toolUseId, {
          toolUseId,
          toolName,
          input: toolInput,
          status: isClientSide ? 'running' : 'pending',
          isClientSide,
          textSnapshotLength: accumulatedText.length,
        });
        maybeCheckpoint();

        if (isClientSide) {
          const result = await executeClientTool(toolName, toolInput, sessionId);
          dispatch({
            type: 'generation/toolUse',
            sessionId,
            requestId,
            msgId,
            toolUseId,
            patch: { status: result.success ? 'done' : 'error', result },
          });
          // Update checkpoint tracking
          const tracked = cpToolCalls.get(toolUseId);
          if (tracked) {
            tracked.status = result.success ? 'done' : 'error';
            tracked.result = result;
          }
        }
      }

      // --- Tool result ---
      if (event.type === 'tool_result' && event.tool_result) {
        const tr = event.tool_result;
        const msgId = streamingMsgId;

        dispatch({
          type: 'generation/toolResult',
          sessionId,
          requestId,
          msgId,
          toolName: tr.name,
          result: { success: true, result: tr.result },
        });

        // Update checkpoint: mark matching tool as done
        for (const [id, tc] of cpToolCalls) {
          if (tc.toolName === tr.name && tc.status !== 'done') {
            tc.status = 'done';
            tc.result = { success: true, result: tr.result };
            break;
          }
        }
        maybeCheckpoint();

        // Extract document info
        const docInfo = parseDocumentToolResult(event);
        if (docInfo) {
          if (docInfo.s3_key) emittedDocKeys.add(docInfo.s3_key);
          if (docInfo.document_id) emittedDocKeys.add(docInfo.document_id);
          const attachTo = lastAssistantMsgId ?? streamingMsgId;
          dispatch({
            type: 'generation/document',
            sessionId,
            requestId,
            msgId: attachTo,
            document: docInfo,
          });
          onDocumentGenerated?.(sessionId, docInfo);
          cpDocuments.push(docInfo);
        }

        // Auto-open HTML playground in new tab
        if (tr.name === 'generate_html_playground') {
          try {
            const data = typeof tr.result === 'string' ? JSON.parse(tr.result) : tr.result;
            if (data?.presigned_url && data?.open_in_tab) {
              window.open(data.presigned_url, '_blank');
            }
          } catch {
            /* ignore parse errors */
          }
        }
      }

      // --- Tool input delta (streaming tool composition) ---
      if (event.type === 'tool_input_delta' && event.metadata) {
        const toolUseId = String(event.metadata.tool_use_id ?? '');
        const delta = String(event.metadata.delta ?? '');
        if (toolUseId && delta) {
          dispatch({
            type: 'generation/toolInputDelta',
            sessionId,
            requestId,
            msgId: streamingMsgId,
            toolUseId,
            delta,
          });
        }
      }

      // --- Agent status ---
      if (event.type === 'agent_status') {
        dispatch({
          type: 'generation/status',
          sessionId,
          requestId,
          status: event.metadata?.status ?? '',
        });
      }
      if (event.type === 'reasoning') {
        dispatch({ type: 'generation/status', sessionId, requestId, status: 'Reasoning...' });
      }
      if (event.type === 'handoff' && event.metadata) {
        const target = String(event.metadata.target_agent ?? 'specialist');
        dispatch({
          type: 'generation/status',
          sessionId,
          requestId,
          status: `Handing off to ${target}`,
        });
      }

      // --- State update metadata ---
      if (event.type === 'metadata' && event.metadata?.state_type) {
        onStateUpdate?.(event.metadata as Record<string, unknown>);
        const scEntry: StateChangeEntry = {
          stateType: String(event.metadata.state_type),
          packageId: event.metadata.package_id as string | undefined,
          phase: event.metadata.phase as string | undefined,
          title: event.metadata.title as string | undefined,
          acquisitionMethod: event.metadata.acquisition_method as string | undefined,
          contractType: event.metadata.contract_type as string | undefined,
          contractVehicle: event.metadata.contract_vehicle as string | undefined,
          checklist: event.metadata.checklist as
            | { required: string[]; completed: string[] }
            | undefined,
          progressPct: event.metadata.progress_pct as number | undefined,
          textSnapshotLength: accumulatedText.length,
          timestamp: Date.now(),
        };
        dispatch({
          type: 'generation/stateChange',
          sessionId,
          requestId,
          msgId: streamingMsgId,
          stateChange: scEntry,
        });
        cpStateChanges.push(scEntry);
        maybeCheckpoint();
      }

      // --- Complete ---
      if (event.type === 'complete') {
        // Clear checkpoint — normal save path takes over
        clearCheckpoint(sessionId);

        const toolsCalled = event.metadata?.tools_called;
        if (Array.isArray(toolsCalled) && toolsCalled.includes('create_document')) {
          const expectedCount = toolsCalled.filter((t: string) => t === 'create_document').length;
          if (emittedDocKeys.size < expectedCount) {
            const docs = parseDocumentsFromText(accumulatedText);
            for (const doc of docs) {
              const name = doc.s3_key || '';
              const alreadyEmitted = [...emittedDocKeys].some((k) => k.endsWith(name));
              if (alreadyEmitted) continue;
              if (doc.s3_key) emittedDocKeys.add(doc.s3_key);
              const attachTo = lastAssistantMsgId ?? streamingMsgId;
              dispatch({
                type: 'generation/document',
                sessionId,
                requestId,
                msgId: attachTo,
                document: doc,
              });
              onDocumentGenerated?.(sessionId, doc);
            }
            if (emittedDocKeys.size < expectedCount) {
              shouldFetchDocs = true;
            }
          }
        }
      }

      // --- Error ---
      if (event.type === 'error') {
        // Keep checkpoint on error — partial text survives for recovery
        maybeCheckpoint();
        dispatch({
          type: 'generation/error',
          sessionId,
          requestId,
          error: event.content || 'Unknown error',
        });
      }
    };

    // Parse SSE events
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
            if (data) await processEvent(data);
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
          if (data) await processEvent(data);
        } else if (trimmed.startsWith('{')) {
          await processEvent(trimmed);
        }
      }
    }

    // Fetch documents from API if needed (S3 fallback)
    if (shouldFetchDocs) {
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
            last_modified?: string;
            type?: string;
          }> = data.documents || [];
          for (const doc of docs) {
            const key = doc.key || '';
            const name = doc.name || '';
            if (emittedDocKeys.has(name) || emittedDocKeys.has(key)) continue;
            if (doc.last_modified) {
              const modified = new Date(doc.last_modified);
              if (modified < queryStartTime) continue;
            }
            const prefixMatch = name.match(/^(\w+?)_\d/);
            const prefix = prefixMatch?.[1]?.toLowerCase() || '';
            const typeInfo = DOC_TYPE_MAP[prefix];
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
            emittedDocKeys.add(name || key);
            const attachTo = lastAssistantMsgId ?? streamingMsgId;
            dispatch({
              type: 'generation/document',
              sessionId,
              requestId,
              msgId: attachTo,
              document: docInfo,
            });
            onDocumentGenerated?.(sessionId, docInfo);
          }
        }
      } catch {
        // S3/backend unavailable — ignore
      }
    }

    // Mark generation complete
    const finalMsg = accumulatedText
      ? {
          id: streamingMsgId,
          role: 'assistant' as const,
          content: accumulatedText,
          timestamp: new Date(),
        }
      : undefined;

    dispatch({ type: 'generation/complete', sessionId, requestId, finalMessage: finalMsg });
  }
}

/** Singleton instance — created once, shared across the app. */
let _instance: ChatStreamManager | null = null;

export function getChatStreamManager(): ChatStreamManager {
  if (!_instance) {
    _instance = new ChatStreamManager();
  }
  return _instance;
}
