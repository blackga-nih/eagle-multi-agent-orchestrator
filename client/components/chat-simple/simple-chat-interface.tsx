'use client';

import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import SimpleMessageList from './simple-message-list';
import SimpleWelcome from './simple-welcome';
import SimpleQuickActions from './simple-quick-actions';
import SlashCommandPicker from '@/components/chat/slash-command-picker';
import CommandPalette from './command-palette';
import { useSlashCommands } from '@/hooks/use-slash-commands';
import { useCommands } from '@/hooks/use-commands';
import { useSession } from '@/contexts/session-context';
import { useAuth } from '@/contexts/auth-context';
import { useFeedback } from '@/contexts/feedback-context';
import { useChatRuntimeContext } from '@/contexts/chat-runtime-context';
import { useChatRuntime } from '@/hooks/use-chat-runtime';
import { getChatStreamManager } from '@/lib/chat-stream-manager';
import { SlashCommand } from '@/lib/slash-commands';
import { ChatMessage, DocumentInfo, Message } from '@/types/chat';
import { AuditLogEntry } from '@/types/stream';
import { saveGeneratedDocument } from '@/lib/document-store';
import { ClientToolResult } from '@/lib/client-tools';
import { ToolStatus } from './tool-use-display';
import { loadCheckpoint, clearCheckpoint } from '@/lib/streaming-checkpoint';
import type { StateChangeEntry } from '@/contexts/chat-runtime-context';
import ActivityPanel from './activity-panel';
import ChatUploadButton from './chat-upload-button';
import PackageSelectorModal from './package-selector-modal';
import ContractMatrixModal from '../contract-matrix/contract-matrix-modal';
import type { MatrixTab } from '../contract-matrix/matrix-types';
import { UploadResult, assignToPackage } from '@/lib/document-api';
import { usePackageState } from '@/hooks/use-package-state';
import { useAnalytics } from '@/hooks/use-analytics';
import { useUsageSummary } from '@/hooks/use-usage-summary';

// -----------------------------------------------------------------------
// Types for per-message tool call tracking
// -----------------------------------------------------------------------

export interface TrackedToolCall {
  /** Unique tool invocation ID (from SSE event or generated). */
  toolUseId: string;
  toolName: string;
  input: Record<string, unknown>;
  status: ToolStatus;
  isClientSide: boolean;
  result?: ClientToolResult | null;
  /** Length of accumulated text at the moment this tool was invoked.
   *  Used to interleave text segments and tool cards in stream order. */
  textSnapshotLength?: number;
  /** Raw JSON being composed by the model as tool input (streamed via contentBlockDelta). */
  streamingInput?: string;
}

/** Tool calls keyed by the parent message ID they belong to. */
export type ToolCallsByMessageId = Record<string, TrackedToolCall[]>;

function buildSessionPersistenceSignature(
  messages: Message[],
  documents: Record<string, DocumentInfo[]>,
  toolCallsByMsg: ToolCallsByMessageId,
  stateChangesByMsg: Record<string, StateChangeEntry[]>,
): string {
  return JSON.stringify({
    messages: messages.map((message) => ({
      ...message,
      timestamp:
        message.timestamp instanceof Date ? message.timestamp.toISOString() : message.timestamp,
    })),
    documents,
    toolCallsByMsg,
    stateChangesByMsg,
  });
}

function documentIdentity(doc: DocumentInfo): string {
  if (doc.s3_key) return `s3:${doc.s3_key}`;
  if (doc.document_id) return `id:${doc.document_id}`;
  const generatedAt = doc.generated_at ?? '';
  return `fallback:${doc.document_type}:${doc.title}:${generatedAt}`;
}

function dedupeDocuments(docs: DocumentInfo[]): DocumentInfo[] {
  const seen = new Set<string>();
  const unique: DocumentInfo[] = [];
  for (const doc of docs) {
    const key = documentIdentity(doc);
    if (seen.has(key)) continue;
    seen.add(key);
    unique.push(doc);
  }
  return unique;
}

export default function SimpleChatInterface() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [isLoadingSession, setIsLoadingSession] = useState(true);
  const [documents, setDocuments] = useState<Record<string, DocumentInfo[]>>({});
  const [feedbackStatus, setFeedbackStatus] = useState<'idle' | 'sending' | 'done' | 'error'>(
    'idle',
  );
  // Agent logs for the activity panel
  const [logs, setLogs] = useState<AuditLogEntry[]>([]);

  const { currentSessionId, saveSession, loadSession, writeMessageOptimistic, renameSession } =
    useSession();
  const { getToken } = useAuth();
  const { setSnapshot } = useFeedback();

  // Chat runtime — per-session streaming state via reducer
  const { dispatch } = useChatRuntimeContext();
  const runtime = useChatRuntime(currentSessionId);
  const streamManagerRef = useRef(getChatStreamManager());

  // Derived streaming state from runtime
  const streamingMsg = runtime.streamingMessage;
  const toolCallsByMsg = runtime.toolCallsByMsg;
  const stateChangesByMsg = runtime.stateChangesByMsg;
  const agentStatus = runtime.agentStatus;
  const isStreaming = runtime.isStreaming;

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const lastAssistantIdRef = useRef<string | null>(null);
  const lastPersistedSignatureRef = useRef('');
  /** Track whether AI title has been generated for this session. */
  const titleGeneratedRef = useRef<Set<string>>(new Set());
  /** Store the first user message for title generation. */
  const firstUserMsgRef = useRef<string | null>(null);
  /** Ctrl+K command palette state. */
  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false);
  /** Ctrl+M contract matrix modal state. */
  const [isMatrixOpen, setIsMatrixOpen] = useState(false);
  const [matrixInitialTab, setMatrixInitialTab] = useState<MatrixTab>('explorer');
  /** Document upload state. */
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null);
  const [isPackageSelectorOpen, setIsPackageSelectorOpen] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const dragDepthRef = useRef(0);

  // Global Ctrl+K / Ctrl+M keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        setIsCommandPaletteOpen((v) => !v);
      }
      if ((e.ctrlKey || e.metaKey) && e.key === 'm') {
        e.preventDefault();
        setMatrixInitialTab('explorer');
        setIsMatrixOpen((v) => !v);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  /** Right panel state. */
  const [isPanelOpen, setIsPanelOpen] = useState(true);

  /** Package state — driven by SSE state_update metadata events. */
  const {
    state: packageState,
    handleMetadata: handlePackageMetadata,
    reset: resetPackageState,
  } = usePackageState();

  const { track } = useAnalytics();
  const usage = useUsageSummary(getToken);

  // Load session data
  useEffect(() => {
    if (!currentSessionId) {
      setIsLoadingSession(false);
      return;
    }
    // Clear transient state from previous session
    lastAssistantIdRef.current = null;
    setLogs([]);

    const sessionData = loadSession(currentSessionId);
    if (sessionData) {
      setMessages(sessionData.messages);
      setDocuments(sessionData.documents || {});
      lastPersistedSignatureRef.current = buildSessionPersistenceSignature(
        sessionData.messages,
        sessionData.documents || {},
        sessionData.toolCallsByMsg || {},
        sessionData.stateChangesByMsg || {},
      );
      // Mark existing sessions as already titled (don't re-generate)
      if (sessionData.messages.length > 0) {
        titleGeneratedRef.current.add(currentSessionId);
      }
    } else {
      setMessages([]);
      setDocuments({});
      lastPersistedSignatureRef.current = '';
    }
    resetPackageState();
    firstUserMsgRef.current = null;
    setIsLoadingSession(false);

    // Restore mid-stream checkpoint (if user refreshed during SSE streaming)
    const checkpoint = loadCheckpoint(currentSessionId);
    if (checkpoint) {
      const restoredMsg: ChatMessage = {
        id: checkpoint.streamingMsgId,
        role: 'assistant',
        content: checkpoint.text + '\n\n---\n*Response interrupted — please resend your message.*',
        timestamp: new Date(checkpoint.updatedAt),
      };
      setMessages((prev) => [...prev, restoredMsg]);

      const restoredToolCalls: ToolCallsByMessageId = {};
      if (checkpoint.toolCalls.length > 0) {
        restoredToolCalls[checkpoint.streamingMsgId] = checkpoint.toolCalls.map((tc) => ({
          ...tc,
          status: (tc.status === 'done' ? 'done' : 'interrupted') as ToolStatus,
        }));
      }
      const restoredStateChanges: Record<string, StateChangeEntry[]> = {};
      if (checkpoint.stateChanges.length > 0) {
        restoredStateChanges[checkpoint.streamingMsgId] = checkpoint.stateChanges;
      }
      const restoredDocs: Record<string, DocumentInfo[]> = {};
      if (checkpoint.documents.length > 0) {
        restoredDocs[checkpoint.streamingMsgId] = checkpoint.documents;
      }
      dispatch({
        type: 'generation/restore',
        sessionId: currentSessionId,
        toolCallsByMsg: restoredToolCalls,
        stateChangesByMsg: restoredStateChanges,
        documentsByMsg: restoredDocs,
      });

      clearCheckpoint(currentSessionId);
    }

    // Restore persisted tool calls and state changes from session history
    if (sessionData) {
      const hasToolCalls =
        sessionData.toolCallsByMsg && Object.keys(sessionData.toolCallsByMsg).length > 0;
      const hasStateChanges =
        sessionData.stateChangesByMsg && Object.keys(sessionData.stateChangesByMsg).length > 0;
      const hasDocs = sessionData.documents && Object.keys(sessionData.documents).length > 0;
      if (hasToolCalls || hasStateChanges || hasDocs) {
        dispatch({
          type: 'generation/restore',
          sessionId: currentSessionId,
          toolCallsByMsg: sessionData.toolCallsByMsg || {},
          stateChangesByMsg: sessionData.stateChangesByMsg || {},
          documentsByMsg: sessionData.documents || {},
        });
      }
    }

    // Background: preload context from backend (non-blocking)
    void (async () => {
      try {
        const token = await getToken();
        if (!token) return;
        const resp = await fetch(`/api/sessions/${encodeURIComponent(currentSessionId)}/context`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!resp.ok) return;
        const ctx = await resp.json();
        if (ctx.package) {
          const cl = ctx.package.checklist;
          handlePackageMetadata({
            state_type: 'checklist_update',
            package_id: ctx.package.package_id,
            phase: ctx.package.status,
            checklist: cl,
            progress_pct: cl
              ? Math.round(
                  ((cl.completed?.length ?? 0) /
                    Math.max(cl.required?.length ?? 1, 1)) *
                    100,
                )
              : undefined,
          });
        }
      } catch {
        // Non-blocking — swallow errors
      }
    })();
  }, [currentSessionId, loadSession, resetPackageState, getToken, handlePackageMetadata, dispatch]);

  // Auto-save session (includes tool calls and state changes for persistence across refresh)
  const saveSessionDebounced = useCallback(() => {
    if (messages.length > 0 && currentSessionId) {
      const nextSignature = buildSessionPersistenceSignature(
        messages,
        documents,
        toolCallsByMsg,
        stateChangesByMsg,
      );
      if (nextSignature === lastPersistedSignatureRef.current) {
        return;
      }
      saveSession(currentSessionId, messages, {}, documents, toolCallsByMsg, stateChangesByMsg);
      lastPersistedSignatureRef.current = nextSignature;
    }
  }, [currentSessionId, messages, documents, toolCallsByMsg, stateChangesByMsg, saveSession]);

  useEffect(() => {
    const timeoutId = setTimeout(saveSessionDebounced, 500);
    return () => clearTimeout(timeoutId);
  }, [saveSessionDebounced]);

  // Keep feedback context in sync so the modal can include conversation state
  useEffect(() => {
    setSnapshot({
      messages: messages.map((m) => ({
        role: m.role,
        content: m.content,
        id: m.id,
        timestamp: m.timestamp,
      })),
      lastMessageId: lastAssistantIdRef.current,
    });
  }, [messages, setSnapshot]);

  // Slash command handling — commands fetched from backend registry
  const { commands: registryCommands } = useCommands();

  const handleCommandSelect = (command: SlashCommand) => {
    // Intercept matrix commands — open modal instead of inserting text
    if (command.id === 'matrix') {
      setMatrixInitialTab('explorer');
      setIsMatrixOpen(true);
      return;
    }
    if (command.id === 'contract-type') {
      setMatrixInitialTab('selector');
      setIsMatrixOpen(true);
      return;
    }
    setInput(command.name + ' ');
    textareaRef.current?.focus();
  };

  const {
    isOpen: isCommandPickerOpen,
    filteredCommands,
    selectedIndex,
    handleInputChange: handleSlashInputChange,
    handleKeyDown: handleSlashKeyDown,
    selectCommand,
    closeCommandPicker,
  } = useSlashCommands({ commands: registryCommands, onCommandSelect: handleCommandSelect });

  // Streaming error from runtime
  const error = runtime.error;

  /** Refresh-package-from-chat state */
  const [isRefreshingPackage, setIsRefreshingPackage] = useState(false);

  // Log helpers
  const clearLogs = useCallback(() => setLogs([]), []);
  const addUserInputLog = useCallback((content: string) => {
    const entry: AuditLogEntry = {
      id: `log-${Date.now()}`,
      type: 'user_input',
      agent_id: 'user',
      agent_name: 'User',
      content,
      timestamp: new Date().toISOString(),
    };
    setLogs((prev) => [...prev, entry]);
  }, []);

  // -----------------------------------------------------------------------
  // Refresh active package by scanning chat documents
  // -----------------------------------------------------------------------
  const handleRefreshPackage = useCallback(async () => {
    if (!currentSessionId) return;
    setIsRefreshingPackage(true);
    try {
      const token = await getToken();
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = `Bearer ${token}`;

      // 1. Ask the backend to detect the package from session messages
      const detectRes = await fetch('/api/packages/resolve-context', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          session_id: currentSessionId,
          action: 'detect',
        }),
      });
      if (!detectRes.ok) return;

      const detected = await detectRes.json();
      if (detected.mode === 'workspace' || !detected.package_id) return;

      // 2. Fetch full session context to get checklist state
      const ctxRes = await fetch(`/api/sessions/${encodeURIComponent(currentSessionId)}/context`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (ctxRes.ok) {
        const ctx = await ctxRes.json();
        if (ctx.package) {
          handlePackageMetadata({
            state_type: 'checklist_update',
            package_id: ctx.package.package_id,
            phase: ctx.package.status,
            checklist: ctx.package.checklist,
            progress_pct: ctx.package.checklist
              ? Math.round(
                  ((ctx.package.checklist.completed?.length ?? 0) /
                    Math.max(ctx.package.checklist.required?.length ?? 1, 1)) *
                    100,
                )
              : 0,
          });
        }
      }
    } catch (err) {
      console.error('Package refresh failed:', err);
    } finally {
      setIsRefreshingPackage(false);
    }
  }, [currentSessionId, getToken, handlePackageMetadata]);

  // -----------------------------------------------------------------------
  // Commit streaming message when generation completes
  // -----------------------------------------------------------------------
  const prevStatusRef = useRef(runtime.status);
  useEffect(() => {
    const wasStreaming =
      prevStatusRef.current === 'streaming' || prevStatusRef.current === 'stopping';
    prevStatusRef.current = runtime.status;

    if (wasStreaming && runtime.status === 'idle') {
      // The reducer stores the final message in completedMessage (set
      // atomically in the same dispatch that transitions status→idle).
      const finalMsg = runtime.completedMessage;
      if (finalMsg) {
        lastAssistantIdRef.current = finalMsg.id;
        setMessages((prev) => [...prev, finalMsg]);
      }

      // Merge runtime documents into local documents state
      for (const [msgId, docs] of Object.entries(runtime.documentsByMsg)) {
        setDocuments((prev) => {
          const existing = prev[msgId] ?? [];
          const merged = dedupeDocuments([...existing, ...docs]);
          if (merged.length === existing.length) return prev;
          return { ...prev, [msgId]: merged };
        });
      }

      // Post-stream: refresh package checklist from authoritative backend state
      if (packageState.packageId && currentSessionId) {
        void (async () => {
          try {
            const token = await getToken();
            const resp = await fetch(
              `/api/sessions/${encodeURIComponent(currentSessionId)}/context`,
              { headers: token ? { Authorization: `Bearer ${token}` } : {} },
            );
            if (!resp.ok) return;
            const ctx = await resp.json();
            if (ctx.package?.checklist) {
              handlePackageMetadata({
                state_type: 'checklist_update',
                package_id: ctx.package.package_id,
                phase: ctx.package.status,
                checklist: ctx.package.checklist,
                progress_pct: Math.round(
                  ((ctx.package.checklist.completed?.length ?? 0) /
                    Math.max(ctx.package.checklist.required?.length ?? 1, 1)) *
                    100,
                ),
              });
            }
          } catch {
            /* best-effort */
          }
        })();
      }

      // AI title generation — fire-and-forget on first assistant response
      const sid = currentSessionId;
      const userMsg = firstUserMsgRef.current;
      if (sid && userMsg && finalMsg && !titleGeneratedRef.current.has(sid)) {
        titleGeneratedRef.current.add(sid);
        fetch('/api/sessions/generate-title', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: userMsg,
            response_snippet: finalMsg.content.slice(0, 200),
          }),
        })
          .then((res) => res.json())
          .then((data) => {
            if (data.title && data.title !== 'New Session') {
              renameSession(sid, data.title);
            }
          })
          .catch(() => {
            /* title generation is best-effort */
          });
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runtime.status]);

  // Stop generation handler
  const handleStopGeneration = useCallback(() => {
    streamManagerRef.current.stopQuery(currentSessionId);
    dispatch({ type: 'generation/stopping', sessionId: currentSessionId });
  }, [currentSessionId, dispatch]);

  // Esc to stop — only for the visible session
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isStreaming) {
        handleStopGeneration();
      }
    };
    window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, [isStreaming, handleStopGeneration]);

  const clearDragState = useCallback(() => {
    dragDepthRef.current = 0;
    setIsDragging(false);
  }, []);

  useEffect(() => {
    const handleWindowDragEnd = () => clearDragState();
    const handleWindowDrop = () => clearDragState();
    const handleWindowBlur = () => clearDragState();

    window.addEventListener('dragend', handleWindowDragEnd);
    window.addEventListener('drop', handleWindowDrop);
    window.addEventListener('blur', handleWindowBlur);

    return () => {
      window.removeEventListener('dragend', handleWindowDragEnd);
      window.removeEventListener('drop', handleWindowDrop);
      window.removeEventListener('blur', handleWindowBlur);
    };
  }, [clearDragState]);

  // Auto-resize textarea — show scrollbar only when content exceeds max height
  const adjustTextareaHeight = () => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = 'auto';
      const clamped = Math.min(el.scrollHeight, 160);
      el.style.height = clamped + 'px';
      el.style.overflowY = el.scrollHeight > 160 ? 'auto' : 'hidden';
    }
  };

  useEffect(() => {
    adjustTextareaHeight();
  }, [input]);

  const handleSend = async () => {
    if (!input.trim() || isStreaming) return;

    // Intercept /feedback command — bypass AI entirely
    if (input.trim().toLowerCase().startsWith('/feedback')) {
      const feedbackText = input.replace(/^\/feedback\s*/i, '').trim();
      if (!feedbackText) return;
      setInput('');
      setFeedbackStatus('sending');
      const token = await getToken();
      try {
        await fetch('/api/feedback', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({
            session_id: currentSessionId,
            feedback_text: feedbackText,
            conversation_snapshot: messages.slice(-20).map((m) => ({
              role: m.role,
              content:
                m.content.length > 2000 ? m.content.slice(0, 2000) + '… [truncated]' : m.content,
              timestamp: m.timestamp,
            })),
          }),
        });
        setFeedbackStatus('done');
      } catch {
        setFeedbackStatus('error');
      }
      setTimeout(() => setFeedbackStatus('idle'), 4000);
      return;
    }

    track('chat_send', { message_length: input.length });

    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: input,
      timestamp: new Date(),
    };
    lastAssistantIdRef.current = null;
    // Capture first user message for AI title generation
    if (messages.length === 0) {
      firstUserMsgRef.current = input;
    }
    setMessages((prev) => [...prev, userMessage]);
    // Log user input to agent logs panel
    addUserInputLog(input);
    // Optimistic write to IndexedDB — fire-and-forget, never blocks send
    writeMessageOptimistic(currentSessionId, userMessage);
    const query = input;
    setInput('');

    // Start streaming via the ChatStreamManager — dispatches to runtime reducer
    streamManagerRef.current.startQuery({
      sessionId: currentSessionId,
      query,
      packageId: packageState.packageId ?? undefined,
      getToken: async () => {
        const t = await getToken();
        return t ?? '';
      },
      dispatch,
      onLog: (entry) => setLogs((prev) => [...prev, entry]),
      onDocumentGenerated: (sid, doc) => {
        const title =
          messages.find((m) => m.role === 'user')?.content.slice(0, 80) || 'Untitled Package';
        saveGeneratedDocument(doc, sid, title);
      },
      onStateUpdate: handlePackageMetadata,
    });
  };

  const insertText = (text: string) => {
    setInput(text);
    textareaRef.current?.focus();
  };

  const displayMessages = useMemo(
    () => (streamingMsg ? [...messages, streamingMsg] : messages),
    [messages, streamingMsg],
  );
  const hasMessages = displayMessages.length > 0;

  // Merge local documents (uploads) with runtime documents (streaming)
  const mergedDocuments = useMemo(() => {
    const result = { ...documents };
    for (const [msgId, docs] of Object.entries(runtime.documentsByMsg)) {
      const existing = result[msgId] ?? [];
      result[msgId] = dedupeDocuments([...existing, ...docs]);
    }
    return result;
  }, [documents, runtime.documentsByMsg]);

  const handlePaletteSelect = (cmd: SlashCommand) => {
    setInput(cmd.name + ' ');
    textareaRef.current?.focus();
  };

  // Upload handlers
  const handleUploadComplete = (result: UploadResult) => {
    setUploadResult(result);
    setIsPackageSelectorOpen(true);
  };

  const handlePackageAssignment = async (
    packageId: string | null,
    docType: string,
    title: string,
  ) => {
    if (!uploadResult) return;

    const msgId = `upload-${Date.now()}`;
    const token = await getToken();

    try {
      let docInfo: DocumentInfo;

      if (packageId) {
        // Assign to package - get back document details
        const result = await assignToPackage(
          uploadResult.upload_id,
          packageId,
          docType,
          title,
          token,
        );
        docInfo = {
          document_id: result.document_id,
          package_id: result.package_id,
          document_type: result.doc_type || docType,
          doc_type: result.doc_type || docType,
          title: result.title || title,
          s3_key: result.s3_key || uploadResult.key,
          mode: 'package',
          status: result.status || 'draft',
          version: result.version || 1,
          content_type: uploadResult.content_type,
          is_binary:
            uploadResult.content_type !== 'text/plain' &&
            uploadResult.content_type !== 'text/markdown',
          generated_at: new Date().toISOString(),
        };

        // Add system message
        const systemMsg: ChatMessage = {
          id: msgId,
          role: 'assistant',
          content: `Document uploaded and assigned to package **${packageId}**.`,
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, systemMsg]);
      } else {
        // Keep in workspace
        docInfo = {
          document_type: docType,
          doc_type: docType,
          title: title,
          s3_key: uploadResult.key,
          mode: 'workspace',
          status: 'draft',
          version: 1,
          content_type: uploadResult.content_type,
          is_binary:
            uploadResult.content_type !== 'text/plain' &&
            uploadResult.content_type !== 'text/markdown',
          generated_at: new Date().toISOString(),
        };

        // Add system message
        const systemMsg: ChatMessage = {
          id: msgId,
          role: 'assistant',
          content: `Document uploaded to your workspace.`,
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, systemMsg]);
      }

      // Add document card to the message
      setDocuments((prev) => ({
        ...prev,
        [msgId]: [...(prev[msgId] || []), docInfo],
      }));

      // Persist to localStorage
      if (currentSessionId) {
        saveGeneratedDocument(docInfo, currentSessionId, title);
      }

      setUploadResult(null);
    } catch (err) {
      throw err;
    }
  };

  const isFileDrag = (e: React.DragEvent) =>
    Array.from(e.dataTransfer?.types ?? []).includes('Files');

  // Drag-drop handlers
  const handleDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    if (!isFileDrag(e)) return;
    dragDepthRef.current += 1;
    setIsDragging(true);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    if (!isFileDrag(e)) return;
    e.dataTransfer.dropEffect = 'copy';
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    if (!isFileDrag(e)) return;
    dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
    if (dragDepthRef.current === 0) {
      setIsDragging(false);
    }
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    clearDragState();

    const files = e.dataTransfer.files;
    if (files.length === 0) return;

    const file = files[0];
    // Validate file type
    const validTypes = [
      'application/pdf',
      'application/msword',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      'application/vnd.ms-excel',
      'text/plain',
      'text/markdown',
    ];
    if (!validTypes.includes(file.type)) {
      // Show error in chat
      const errorMsg: ChatMessage = {
        id: `upload-error-${Date.now()}`,
        role: 'assistant',
        content: `Unsupported file type: ${file.type || 'unknown'}. Please upload PDF, Word, Excel, or text documents.`,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMsg]);
      return;
    }

    // Use the upload API
    try {
      const token = await getToken();
      const { uploadDocument } = await import('@/lib/document-api');
      const result = await uploadDocument(
        file,
        currentSessionId || undefined,
        packageState.packageId ?? undefined,
        token,
      );
      handleUploadComplete(result);
    } catch (err) {
      const errorMsg: ChatMessage = {
        id: `upload-error-${Date.now()}`,
        role: 'assistant',
        content: `Upload failed: ${err instanceof Error ? err.message : 'Unknown error'}`,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMsg]);
    }
  };

  return (
    <div className="h-full flex bg-[#F5F7FA]">
      {/* Left: main chat area */}
      <div
        className="flex-1 flex flex-col min-w-0 relative"
        onDragEnter={handleDragEnter}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {/* Drag overlay */}
        {isDragging && (
          <div className="absolute inset-0 z-40 bg-blue-500/10 border-2 border-dashed border-blue-500 rounded-lg flex items-center justify-center pointer-events-none">
            <div className="bg-white px-6 py-4 rounded-xl shadow-lg">
              <p className="text-blue-600 font-medium">Drop document to upload</p>
              <p className="text-sm text-gray-500">PDF, Word, or text files</p>
            </div>
          </div>
        )}

        {/* Ctrl+K command palette */}
        <CommandPalette
          isOpen={isCommandPaletteOpen}
          onClose={() => setIsCommandPaletteOpen(false)}
          onSelect={handlePaletteSelect}
          commands={registryCommands}
        />

        {/* Main content area */}
        {!hasMessages && !isLoadingSession ? (
          <SimpleWelcome onAction={insertText} />
        ) : (
          <SimpleMessageList
            messages={displayMessages}
            isTyping={isStreaming}
            documents={mergedDocuments}
            sessionId={currentSessionId}
            toolCallsByMsg={toolCallsByMsg}
            stateChangesByMsg={stateChangesByMsg}
            agentStatus={agentStatus}
            pendingToolCalls={
              runtime.streamingMessageId ? (toolCallsByMsg[runtime.streamingMessageId] ?? []) : []
            }
          />
        )}

        {/* Input footer */}
        <footer className="bg-white border-t border-[#D8DEE6] px-6 py-3 shrink-0">
          <div className="max-w-4xl mx-auto">
            {error && (
              <div className="mb-2 px-3 py-1.5 bg-red-50 border border-red-200 rounded-lg text-red-700 text-xs">
                {error}
              </div>
            )}
            {feedbackStatus === 'sending' && (
              <div className="mb-2 px-3 py-1.5 bg-blue-50 border border-blue-200 rounded-lg text-blue-700 text-xs">
                Submitting feedback…
              </div>
            )}
            {feedbackStatus === 'done' && (
              <div className="mb-2 px-3 py-1.5 bg-green-50 border border-green-200 rounded-lg text-green-700 text-xs">
                ✓ Feedback received. Thank you!
              </div>
            )}
            {feedbackStatus === 'error' && (
              <div className="mb-2 px-3 py-1.5 bg-red-50 border border-red-200 rounded-lg text-red-700 text-xs">
                Failed to submit feedback. Please try again.
              </div>
            )}

            {/* Quick action pills — above the input */}
            <SimpleQuickActions onAction={insertText} />

            <div className="relative flex items-end gap-3">
              {/* Slash command picker */}
              {isCommandPickerOpen && (
                <SlashCommandPicker
                  commands={filteredCommands}
                  selectedIndex={selectedIndex}
                  onSelect={selectCommand}
                  onClose={closeCommandPicker}
                />
              )}
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => {
                  setInput(e.target.value);
                  handleSlashInputChange(e.target.value, e.target.selectionStart || 0);
                }}
                onKeyDown={(e) => {
                  if (isCommandPickerOpen) {
                    handleSlashKeyDown(e);
                    if (['ArrowUp', 'ArrowDown', 'Enter', 'Escape', 'Tab'].includes(e.key)) return;
                  }
                  if (e.key === 'Enter' && !e.shiftKey && !isStreaming && !isCommandPickerOpen) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
                placeholder={
                  isStreaming
                    ? 'Waiting for response\u2026'
                    : 'Ask EAGLE about acquisitions, type / or press Ctrl+K for commands\u2026'
                }
                disabled={isStreaming}
                rows={1}
                className={`flex-1 resize-none overflow-hidden px-4 py-3 bg-white border border-[#D8DEE6] rounded-xl focus:outline-none focus:ring-2 focus:ring-[#2196F3]/30 focus:border-[#2196F3] transition-all text-sm leading-relaxed ${isStreaming ? 'opacity-50' : ''}`}
                style={{ maxHeight: 160 }}
              />
              <ChatUploadButton
                onUploadComplete={handleUploadComplete}
                sessionId={currentSessionId || undefined}
                disabled={isStreaming}
                getToken={getToken}
              />
              {isStreaming ? (
                <button
                  onClick={handleStopGeneration}
                  className="p-3 bg-red-500 text-white rounded-xl hover:bg-red-600 transition-all shadow-md shrink-0"
                  title="Stop generating (Esc)"
                >
                  <span className="text-base">&#9632;</span>
                </button>
              ) : (
                <button
                  onClick={handleSend}
                  disabled={!input.trim()}
                  className="p-3 bg-[#003366] text-white rounded-xl hover:bg-[#004488] disabled:opacity-30 transition-all shadow-md shrink-0"
                >
                  <span className="text-base">&#10148;</span>
                </button>
              )}
            </div>
            <div className="flex items-center justify-between mt-2 text-[10px] text-[#8896A6]">
              <div className="flex items-center gap-3">
                {usage && (
                  <>
                    <span title="Total cost (30 days)">${usage.totalCostUsd.toFixed(2)}</span>
                    <span className="opacity-40">|</span>
                    <span title="Total requests (30 days)">{usage.totalRequests.toLocaleString()} requests</span>
                    <span className="opacity-40">|</span>
                    <span title="Total tokens (30 days)">{(usage.totalTokens / 1000).toFixed(0)}K tokens</span>
                  </>
                )}
              </div>
              <span>EAGLE &middot; National Cancer Institute</span>
            </div>
          </div>
        </footer>
      </div>

      {/* Right: activity panel (includes package checklist as default tab) */}
      <ActivityPanel
        logs={logs}
        clearLogs={clearLogs}
        documents={mergedDocuments}
        sessionId={currentSessionId ?? ''}
        isStreaming={isStreaming}
        isOpen={isPanelOpen}
        onToggle={() => setIsPanelOpen((v) => !v)}
        packageState={packageState}
        getToken={getToken}
        onRefreshPackage={handleRefreshPackage}
        isRefreshingPackage={isRefreshingPackage}
        stateChangesByMsg={stateChangesByMsg}
      />

      {/* Package selector modal for uploaded documents */}
      <PackageSelectorModal
        isOpen={isPackageSelectorOpen}
        onClose={() => {
          setIsPackageSelectorOpen(false);
          setUploadResult(null);
        }}
        uploadResult={uploadResult}
        onAssign={handlePackageAssignment}
        getToken={getToken}
      />

      {/* Contract requirements matrix modal (Ctrl+M) */}
      <ContractMatrixModal
        isOpen={isMatrixOpen}
        onClose={() => setIsMatrixOpen(false)}
        onApply={insertText}
        initialTab={matrixInitialTab}
      />
    </div>
  );
}
