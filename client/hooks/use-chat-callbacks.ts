'use client';

import { useCallback, useRef } from 'react';
import { ChatMessage, DocumentInfo } from '@/types/chat';
import {
  TrackedToolCall,
  ToolCallsByMessageId,
} from '@/components/chat-simple/simple-chat-interface';
import { ToolStatus } from '@/components/chat-simple/tool-use-display';
import { ToolUseEvent, StreamCompleteInfo, ServerToolResult } from '@/hooks/use-agent-stream';
import { ClientToolResult } from '@/lib/client-tools';
import { saveGeneratedDocument } from '@/lib/document-store';

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

interface UseChatCallbacksParams {
  currentSessionId: string | null;
  messages: ChatMessage[];
  streamingMsgIdRef: React.MutableRefObject<string>;
  lastAssistantIdRef: React.MutableRefObject<string | null>;
  streamingMsgRef: React.MutableRefObject<ChatMessage | null>;
  titleGeneratedRef: React.MutableRefObject<Set<string>>;
  firstUserMsgRef: React.MutableRefObject<string | null>;
  setMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>;
  setStreamingMsg: React.Dispatch<React.SetStateAction<ChatMessage | null>>;
  setDocuments: React.Dispatch<React.SetStateAction<Record<string, DocumentInfo[]>>>;
  setToolCallsByMsg: React.Dispatch<React.SetStateAction<ToolCallsByMessageId>>;
  setAgentStatus: React.Dispatch<React.SetStateAction<string | null>>;
  handlePackageMetadata: (metadata: Record<string, unknown>) => void;
  renameSession: (sessionId: string, title: string) => void;
}

export function useChatCallbacks({
  currentSessionId,
  messages,
  streamingMsgIdRef,
  lastAssistantIdRef,
  streamingMsgRef,
  titleGeneratedRef,
  firstUserMsgRef,
  setMessages,
  setStreamingMsg,
  setDocuments,
  setToolCallsByMsg,
  setAgentStatus,
  handlePackageMetadata,
  renameSession,
}: UseChatCallbacksParams) {
  const upsertToolCall = useCallback(
    (msgId: string, toolUseId: string, patch: Partial<TrackedToolCall>) => {
      setToolCallsByMsg((prev) => {
        const existing = prev[msgId] ?? [];
        const idx = existing.findIndex((t) => t.toolUseId === toolUseId);
        if (idx === -1) {
          const newEntry: TrackedToolCall = {
            toolUseId,
            toolName: patch.toolName ?? '',
            input: patch.input ?? {},
            status: patch.status ?? 'pending',
            isClientSide: patch.isClientSide ?? false,
            result: patch.result,
          };
          return { ...prev, [msgId]: [...existing, newEntry] };
        }
        const updated = existing.slice();
        updated[idx] = { ...updated[idx], ...patch };
        return { ...prev, [msgId]: updated };
      });
    },
    [setToolCallsByMsg],
  );

  const onMessage = useCallback(
    (msg: {
      id: string;
      content: string;
      timestamp: Date;
      reasoning?: string;
      agent_id?: string;
      agent_name?: string;
    }) => {
      const newMessage: ChatMessage = {
        id: msg.id,
        role: 'assistant',
        content: msg.content,
        timestamp: msg.timestamp,
        reasoning: msg.reasoning,
        agent_id: msg.agent_id,
        agent_name: msg.agent_name,
      };
      lastAssistantIdRef.current = msg.id;
      streamingMsgRef.current = newMessage;
      setStreamingMsg(newMessage);
    },
    [lastAssistantIdRef, streamingMsgRef, setStreamingMsg],
  );

  const onComplete = useCallback(
    (info?: StreamCompleteInfo) => {
      setAgentStatus(null);
      const toolResults = info?.toolResults;
      if (info?.durationMs) {
        console.debug(`[EAGLE] Response completed in ${info.durationMs}ms`, info.toolTimings);
      }
      const completedMsg = streamingMsgRef.current;
      if (completedMsg) {
        lastAssistantIdRef.current = completedMsg.id;
        setMessages((prev) => [...prev, completedMsg]);

        // Migrate tool calls from streaming ID to committed message ID
        const streamId = streamingMsgIdRef.current;
        setToolCallsByMsg((prev) => {
          const calls = prev[streamId] ?? prev[completedMsg.id] ?? [];
          if (calls.length === 0) return prev;

          const resultsByName = new Map<string, ServerToolResult[]>();
          if (toolResults) {
            for (const tr of toolResults) {
              const arr = resultsByName.get(tr.toolName) ?? [];
              arr.push(tr);
              resultsByName.set(tr.toolName, arr);
            }
          }

          const finalized = calls.map((tc) => {
            if (tc.isClientSide) return tc;
            const pending = resultsByName.get(tc.toolName);
            const matched = pending?.shift();
            if (matched) {
              return { ...tc, status: 'done' as const, result: matched.result as ClientToolResult };
            }
            if (tc.status === 'pending' || tc.status === 'running') {
              return { ...tc, status: 'done' as const };
            }
            return tc;
          });

          const next = { ...prev };
          delete next[streamId];
          next[completedMsg.id] = finalized;
          return next;
        });

        // Migrate document cards
        setDocuments((prev) => {
          const streamDocs = prev[streamId] ?? [];
          const committedDocs = prev[completedMsg.id] ?? [];
          if (streamDocs.length === 0 && committedDocs.length === 0) {
            return prev;
          }
          const merged = dedupeDocuments([...committedDocs, ...streamDocs]);
          const next = { ...prev, [completedMsg.id]: merged };
          if (streamId !== completedMsg.id) {
            delete next[streamId];
          }
          return next;
        });

        // AI title generation
        const sid = currentSessionId;
        const userMsg = firstUserMsgRef.current;
        if (sid && userMsg && !titleGeneratedRef.current.has(sid)) {
          titleGeneratedRef.current.add(sid);
          fetch('/api/sessions/generate-title', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              message: userMsg,
              response_snippet: completedMsg.content.slice(0, 200),
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
      streamingMsgRef.current = null;
      setStreamingMsg(null);
    },
    [
      currentSessionId,
      streamingMsgRef,
      streamingMsgIdRef,
      lastAssistantIdRef,
      firstUserMsgRef,
      titleGeneratedRef,
      setMessages,
      setToolCallsByMsg,
      setDocuments,
      setAgentStatus,
      setStreamingMsg,
      renameSession,
    ],
  );

  const onError = useCallback(() => {
    setAgentStatus(null);
    streamingMsgRef.current = null;
    setStreamingMsg(null);
  }, [streamingMsgRef, setAgentStatus, setStreamingMsg]);

  const onDocumentGenerated = useCallback(
    (doc: DocumentInfo) => {
      const attachTo = lastAssistantIdRef.current ?? streamingMsgIdRef.current;
      setDocuments((prev) => {
        const existing = prev[attachTo] ?? [];
        const merged = dedupeDocuments([...existing, doc]);
        return { ...prev, [attachTo]: merged };
      });

      if (currentSessionId) {
        const title =
          messages.find((m) => m.role === 'user')?.content.slice(0, 80) || 'Untitled Package';
        saveGeneratedDocument(doc, currentSessionId, title);
      }
    },
    [currentSessionId, messages, lastAssistantIdRef, streamingMsgIdRef, setDocuments],
  );

  const onToolUse = useCallback(
    (toolEvent: ToolUseEvent) => {
      const parentId = streamingMsgIdRef.current;

      if (toolEvent.result === undefined) {
        upsertToolCall(parentId, toolEvent.toolUseId, {
          toolName: toolEvent.toolName,
          input: toolEvent.input,
          status: toolEvent.isClientSide ? 'running' : 'pending',
          isClientSide: toolEvent.isClientSide,
          result: undefined,
        });
      } else {
        const status: ToolStatus = toolEvent.result.success ? 'done' : 'error';
        upsertToolCall(parentId, toolEvent.toolUseId, {
          status,
          result: toolEvent.result,
        });
      }
    },
    [streamingMsgIdRef, upsertToolCall],
  );

  const onToolResult = useCallback(
    (toolName: string, result: unknown) => {
      const parentId = streamingMsgIdRef.current;
      setToolCallsByMsg((prev) => {
        const calls = prev[parentId] ?? [];
        const idx = calls.findIndex((tc) => tc.toolName === toolName && tc.status !== 'done');
        if (idx === -1) return prev;
        const updated = calls.slice();
        updated[idx] = { ...updated[idx], status: 'done', result: result as ClientToolResult };
        return { ...prev, [parentId]: updated };
      });
    },
    [streamingMsgIdRef, setToolCallsByMsg],
  );

  const onAgentStatus = useCallback(
    (status: string | null) => {
      setAgentStatus(status);
    },
    [setAgentStatus],
  );

  const onStateUpdate = useCallback(
    (metadata: Record<string, unknown>) => {
      handlePackageMetadata(metadata);
    },
    [handlePackageMetadata],
  );

  return {
    onMessage,
    onComplete,
    onError,
    onDocumentGenerated,
    onToolUse,
    onToolResult,
    onAgentStatus,
    onStateUpdate,
    upsertToolCall,
  };
}
