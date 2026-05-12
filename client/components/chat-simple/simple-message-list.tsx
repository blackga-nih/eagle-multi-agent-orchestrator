'use client';

import { useEffect, useRef, useState, useMemo, memo, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ChatMessage, DocumentInfo } from '@/types/chat';
import DocumentCard from './document-card';
import ToolUseDisplay from './tool-use-display';
import StateChangeCard from './state-change-card';
import CodeSandboxRenderer from './code-sandbox-renderer';
import MessageFeedback from './message-feedback';
import ThinkingChip from './thinking-chip';
import { ToolCallsByMessageId, TrackedToolCall } from './simple-chat-interface';
import { CodeResult } from '@/lib/client-tools';
import { ThinkingBlock } from '@/types/stream';

/** Shared markdown components — defined once, reused across all messages. */
const mdComponents = {
  p: ({ children }: any) => <p className="mb-3 last:mb-0">{children}</p>,
  ul: ({ children }: any) => <ul className="list-disc ml-5 mb-3 space-y-1">{children}</ul>,
  ol: ({ children }: any) => <ol className="list-decimal ml-5 mb-3 space-y-1">{children}</ol>,
  li: ({ children }: any) => <li className="leading-relaxed">{children}</li>,
  strong: ({ children }: any) => (
    <strong className="font-semibold text-gray-900">{children}</strong>
  ),
  h1: ({ children }: any) => (
    <h1 className="text-lg font-bold text-gray-900 mb-2 mt-4">{children}</h1>
  ),
  h2: ({ children }: any) => (
    <h2 className="text-base font-semibold text-gray-900 mb-2 mt-3">{children}</h2>
  ),
  h3: ({ children }: any) => (
    <h3 className="text-sm font-semibold text-gray-900 mb-1 mt-2">{children}</h3>
  ),
  code: ({ children }: any) => (
    <code className="bg-gray-100 px-1.5 py-0.5 rounded text-xs font-mono text-gray-800">
      {children}
    </code>
  ),
  pre: ({ children }: any) => (
    <pre className="bg-gray-100 p-4 rounded-lg overflow-x-auto my-3 text-xs font-mono">
      {children}
    </pre>
  ),
  blockquote: ({ children }: any) => (
    <blockquote className="border-l-2 border-gray-300 pl-4 italic text-gray-600 my-2">
      {children}
    </blockquote>
  ),
  // Table components — GFM tables need remarkGfm + these elements
  table: ({ children }: any) => (
    <div className="overflow-x-auto my-3 border border-gray-200 rounded-lg">
      <table className="min-w-full divide-y divide-gray-200 text-sm">{children}</table>
    </div>
  ),
  thead: ({ children }: any) => <thead className="bg-gray-50">{children}</thead>,
  tbody: ({ children }: any) => (
    <tbody className="divide-y divide-gray-100 bg-white">{children}</tbody>
  ),
  tr: ({ children }: any) => <tr className="hover:bg-gray-50">{children}</tr>,
  th: ({ children }: any) => (
    <th className="px-3 py-2 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider whitespace-nowrap">
      {children}
    </th>
  ),
  td: ({ children }: any) => <td className="px-3 py-2 text-sm text-gray-700">{children}</td>,
};

const remarkPlugins = [remarkGfm];

/**
 * Memoized markdown renderer for completed (non-streaming) messages.
 * Prevents re-parsing on every parent render when only other messages update.
 */
const MemoizedMarkdown = memo(function MemoizedMarkdown({ content }: { content: string }) {
  return (
    <ReactMarkdown remarkPlugins={remarkPlugins} components={mdComponents}>
      {content}
    </ReactMarkdown>
  );
});

/**
 * Streaming-optimized markdown: splits on paragraph boundaries so only the
 * last (actively growing) block re-renders. Completed blocks are memoized.
 */
const StreamingMarkdown = memo(function StreamingMarkdown({ content }: { content: string }) {
  const blocks = content.split(/\n\n+/);
  return (
    <>
      {blocks.map((block, i) => {
        const isLast = i === blocks.length - 1;
        return isLast ? (
          <ReactMarkdown
            key={`sblock-${i}`}
            remarkPlugins={remarkPlugins}
            components={mdComponents}
          >
            {block + ' ...'}
          </ReactMarkdown>
        ) : (
          <MemoizedMarkdown key={`sblock-${i}`} content={block} />
        );
      })}
    </>
  );
});

interface SimpleMessageListProps {
  messages: ChatMessage[];
  isTyping: boolean;
  documents?: Record<string, DocumentInfo[]>;
  sessionId?: string;
  /** Tool call state keyed by message ID — populated from SSE tool_use events. */
  toolCallsByMsg?: ToolCallsByMessageId;
  /** State change entries keyed by message ID — populated from SSE metadata events. */
  stateChangesByMsg?: Record<string, import('@/contexts/chat-runtime-context').StateChangeEntry[]>;
  /** Extended-thinking blocks keyed by message ID — populated from SSE reasoning events. */
  thinkingBlocksByMsg?: Record<string, ThinkingBlock[]>;
  /** Agent status text shown during model thinking / tool execution. */
  agentStatus?: string | null;
  /** Tool calls for the in-flight streaming message (shown during waiting phase). */
  pendingToolCalls?: TrackedToolCall[];
  /** Thinking blocks for the in-flight streaming message (shown during waiting phase). */
  pendingThinkingBlocks?: ThinkingBlock[];
}

/** Render code sandbox output below a code tool call card, if output exists. */
function CodeOutput({ tc }: { tc: TrackedToolCall }) {
  if (tc.toolName !== 'code') return null;
  if (tc.status !== 'done') return null;
  if (!tc.result?.result) return null;

  const codeResult = tc.result.result as CodeResult;
  const lang = String(tc.input.language ?? 'javascript');

  const hasOutput =
    (Array.isArray(codeResult.logs) && codeResult.logs.length > 0) || Boolean(codeResult.html);

  if (!hasOutput) return null;

  return (
    <CodeSandboxRenderer
      language={lang}
      source={String(tc.input.source ?? '')}
      result={codeResult}
    />
  );
}

function stateChangeKey(entry: import('@/contexts/chat-runtime-context').StateChangeEntry): string {
  if (entry.stateType === 'checklist_update') {
    return `checklist:${entry.packageId ?? ''}`;
  }
  if (entry.stateType === 'sources_summary') {
    return `sources_summary:${entry.textSnapshotLength}:${entry.fetchCount ?? 0}:${
      entry.searchCount ?? 0
    }:${entry.totalCharsRead ?? 0}:${(entry.fetchedKeys ?? []).join('|')}`;
  }
  if (entry.stateType === 'sources_read') {
    return `sources_read:${entry.textSnapshotLength}:${entry.sourceS3Key ?? ''}:${
      entry.sourceTitle ?? ''
    }:${entry.sourceCharsRead ?? 0}`;
  }
  return `${entry.stateType}:${entry.timestamp}:${entry.packageId ?? ''}:${entry.title ?? ''}`;
}

/**
 * Renders text and tool cards interleaved in stream order.
 * Uses textSnapshotLength on each TrackedToolCall to split the accumulated
 * text into segments that appear before/between/after tool cards.
 */
function InterleavedContent({
  content,
  toolCalls,
  stateChanges = [],
  thinkingBlocks = [],
  isStreaming,
  sessionId,
}: {
  content: string;
  toolCalls: TrackedToolCall[];
  stateChanges?: import('@/contexts/chat-runtime-context').StateChangeEntry[];
  thinkingBlocks?: ThinkingBlock[];
  isStreaming: boolean;
  sessionId?: string;
}) {
  // Merge tool calls, state changes, and thinking blocks into a single
  // sorted stream by textSnapshotLength so all three render in stream order.
  type StreamItem =
    | { kind: 'tool'; tc: TrackedToolCall; snapLen: number }
    | {
        kind: 'state';
        entry: import('@/contexts/chat-runtime-context').StateChangeEntry;
        snapLen: number;
      }
    | { kind: 'thinking'; block: ThinkingBlock; snapLen: number };

  const isSummaryItem = (it: StreamItem): boolean =>
    it.kind === 'state' && it.entry.stateType === 'sources_summary';

  const items: StreamItem[] = [
    ...toolCalls.map((tc) => ({ kind: 'tool' as const, tc, snapLen: tc.textSnapshotLength ?? 0 })),
    ...stateChanges.map((entry) => ({
      kind: 'state' as const,
      entry,
      // Force sources_summary to land after all text — it's the closing
      // aggregate chip and must render as the final event, not interleaved
      // with sources_read chips or trailing prose.
      snapLen:
        entry.stateType === 'sources_summary' ? content.length : entry.textSnapshotLength ?? 0,
    })),
    ...thinkingBlocks.map((block) => ({
      kind: 'thinking' as const,
      block,
      snapLen: block.textSnapshotLength ?? 0,
    })),
  ].sort((a, b) => {
    if (a.snapLen !== b.snapLen) return a.snapLen - b.snapLen;
    // Tie-break: summary always sorts last so prior chips at the same
    // snapshot land in their own group before the summary triggers a flush.
    const aSum = isSummaryItem(a);
    const bSum = isSummaryItem(b);
    if (aSum !== bSum) return aSum ? 1 : -1;
    return 0;
  });

  // Build segments: text blocks and groups of consecutive chips/cards
  const segments: React.ReactNode[] = [];
  let cursor = 0;
  let chipGroup: React.ReactNode[] = [];
  let codeOutputs: React.ReactNode[] = [];

  const flushChips = () => {
    if (chipGroup.length > 0) {
      segments.push(
        <div key={`chips-${segments.length}`} className="flex flex-wrap gap-1.5 my-2">
          {chipGroup}
        </div>,
      );
      if (codeOutputs.length > 0) {
        segments.push(...codeOutputs);
        codeOutputs = [];
      }
      chipGroup = [];
    }
  };

  for (const item of items) {
    const snapLen = item.snapLen;
    const isSummary = isSummaryItem(item);

    // Text segment before this item — flush any pending chips first
    if (snapLen > cursor) {
      flushChips();
      const textSlice = content.slice(cursor, snapLen).trim();
      if (textSlice) {
        segments.push(
          <div key={`text-${cursor}`} className="text-sm text-gray-800 leading-relaxed">
            <MemoizedMarkdown content={textSlice} />
          </div>,
        );
      }
      cursor = snapLen;
    } else if (isSummary) {
      // No text gap, but the sources summary must always start its own
      // chip row so it isn't crammed in with sources_read chips that share
      // the same snapshot length.
      flushChips();
    }

    if (item.kind === 'tool') {
      const tc = item.tc;
      // Accumulate tool chip into current group
      chipGroup.push(
        <ToolUseDisplay
          key={tc.toolUseId}
          toolName={tc.toolName}
          input={tc.input}
          status={tc.status}
          result={tc.result}
          isClientSide={tc.isClientSide}
          sessionId={sessionId}
          streamingInput={tc.streamingInput}
        />,
      );
      // CodeOutput renders as a block below the chip group
      const co = <CodeOutput key={`code-${tc.toolUseId}`} tc={tc} />;
      if (tc.toolName === 'code') codeOutputs.push(co);
    } else if (item.kind === 'thinking') {
      chipGroup.push(<ThinkingChip key={`think-${item.block.blockId}`} block={item.block} />);
    } else {
      // State change card — render alongside tool chips
      chipGroup.push(
        <StateChangeCard key={`state-${stateChangeKey(item.entry)}`} entry={item.entry} />,
      );
    }
  }

  // Flush remaining chips
  flushChips();

  // Remaining text after all tools
  const remaining = content.slice(cursor).trim();
  if (remaining) {
    segments.push(
      <div key="text-final" className="text-sm text-gray-800 leading-relaxed">
        {isStreaming ? (
          <StreamingMarkdown content={remaining} />
        ) : (
          <MemoizedMarkdown content={remaining} />
        )}
      </div>,
    );
  } else if (isStreaming) {
    segments.push(
      <div key="text-streaming" className="text-sm text-gray-800 leading-relaxed">
        <ReactMarkdown remarkPlugins={remarkPlugins} components={mdComponents}>
          {' ...'}
        </ReactMarkdown>
      </div>,
    );
  }

  return <>{segments}</>;
}

/**
 * Phase-aware waiting indicator.
 * Shows "Connecting..." before any SSE events, then server-driven status,
 * with an elapsed-seconds counter after 2 s to prove the app is alive.
 */
function WaitingIndicator({
  agentStatus,
  hasToolCalls,
  isActive,
}: {
  agentStatus?: string | null;
  hasToolCalls: boolean;
  isActive: boolean;
}) {
  const [elapsed, setElapsed] = useState(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!isActive) {
      setElapsed(0);
      if (intervalRef.current) clearInterval(intervalRef.current);
      intervalRef.current = null;
      return;
    }
    // Start counting immediately
    const start = Date.now();
    intervalRef.current = setInterval(() => {
      setElapsed(Math.floor((Date.now() - start) / 1000));
    }, 1000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [isActive]);

  // Determine display text based on phase
  const hasServerStatus = Boolean(agentStatus) || hasToolCalls;
  const statusText = agentStatus || (hasServerStatus ? null : 'Connecting...');

  if (!statusText && !hasServerStatus) {
    // Shouldn't happen when isActive, but guard anyway
    return null;
  }

  // If we only have tool calls and no status text, show nothing (tool cards are enough)
  if (!statusText) return null;

  return (
    <div className="flex items-center gap-2 h-5">
      {/* Spinner dot */}
      <span className="relative flex h-2 w-2">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
        <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500" />
      </span>
      <span className="text-xs text-gray-500">
        {statusText}
        {elapsed >= 2 && <span className="text-gray-400 ml-1">{elapsed}s</span>}
      </span>
    </div>
  );
}

export default function SimpleMessageList({
  messages,
  isTyping,
  documents,
  sessionId,
  toolCallsByMsg = {},
  stateChangesByMsg = {},
  thinkingBlocksByMsg = {},
  agentStatus,
  pendingToolCalls = [],
  pendingThinkingBlocks = [],
}: SimpleMessageListProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const prevCountRef = useRef(messages.length);

  useEffect(() => {
    const countChanged = messages.length !== prevCountRef.current;
    prevCountRef.current = messages.length;
    // Scroll on new message or when streaming finishes; skip mid-stream content updates
    if (countChanged || !isTyping) {
      requestAnimationFrame(() => {
        messagesEndRef.current?.scrollIntoView({
          behavior: isTyping ? 'instant' : 'smooth',
          block: 'end',
        });
      });
    }
  }, [messages.length, isTyping]);

  const copyToClipboard = async (text: string, id: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
    } catch {
      // Clipboard API not available
    }
  };

  const lastIdx = messages.length - 1;

  // Show the "waiting" indicator only before any assistant content arrives.
  // Once the streaming message is in the list (last msg = assistant), we show
  // the inline cursor instead — prevents double indicators.
  const isWaitingForFirstToken =
    isTyping && (messages.length === 0 || messages[lastIdx]?.role === 'user');

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-5xl mx-auto px-6 py-8 flex flex-col gap-8">
        {messages.map((message, index) => {
          const isLastMessage = index === lastIdx;
          const isStreamingThis = isTyping && isLastMessage && message.role === 'assistant';

          if (message.role === 'user') {
            return (
              <div key={message.id} className="msg-contain flex flex-col items-end gap-0.5">
                <span className="text-[10px] font-medium text-gray-400 uppercase tracking-wider">
                  You
                </span>
                <p className="text-sm text-gray-700 text-right leading-relaxed max-w-lg whitespace-pre-wrap">
                  {message.content}
                </p>
              </div>
            );
          }

          // Retrieve tool calls, state changes, and thinking blocks associated with this assistant message
          const toolCalls = toolCallsByMsg[message.id] ?? [];
          const stateChanges = stateChangesByMsg[message.id] ?? [];
          const thinkingBlocks = thinkingBlocksByMsg[message.id] ?? [];

          // Build interleaved content: text segments + tool/state/thinking cards in stream order.
          // Each tool/state/thinking entry records textSnapshotLength — how much
          // text existed when it was emitted — letting us split text around them.
          const hasSnapshots =
            (toolCalls.length > 0 && toolCalls.some((tc) => tc.textSnapshotLength != null)) ||
            stateChanges.length > 0 ||
            thinkingBlocks.length > 0;

          return (
            <div key={message.id} className="msg-contain group flex flex-col gap-1.5">
              <span className="text-[10px] font-semibold text-[#003366] uppercase tracking-wider">
                🦅 Eagle
              </span>

              {hasSnapshots ? (
                // Interleaved rendering: text → tool/thinking → text → ... in stream order
                <InterleavedContent
                  content={message.content}
                  toolCalls={toolCalls}
                  stateChanges={stateChanges}
                  thinkingBlocks={thinkingBlocks}
                  isStreaming={isStreamingThis}
                  sessionId={sessionId}
                />
              ) : (
                <>
                  {/* Legacy: tool chips above text (no snapshot data) */}
                  {toolCalls.length > 0 && (
                    <>
                      <div className="flex flex-wrap gap-1.5 mb-2">
                        {toolCalls.map((tc) => (
                          <ToolUseDisplay
                            key={tc.toolUseId}
                            toolName={tc.toolName}
                            input={tc.input}
                            status={tc.status}
                            result={tc.result}
                            isClientSide={tc.isClientSide}
                            sessionId={sessionId}
                            streamingInput={tc.streamingInput}
                          />
                        ))}
                      </div>
                      {toolCalls
                        .filter((tc) => tc.toolName === 'code')
                        .map((tc) => (
                          <CodeOutput key={`code-${tc.toolUseId}`} tc={tc} />
                        ))}
                    </>
                  )}

                  <div className="text-sm text-gray-800 leading-relaxed">
                    {isStreamingThis ? (
                      <StreamingMarkdown content={message.content} />
                    ) : (
                      <MemoizedMarkdown content={message.content} />
                    )}
                  </div>
                </>
              )}

              {/* Copy button — visible on hover after streaming completes */}
              {!isStreamingThis && (
                <button
                  onClick={() => copyToClipboard(message.content, message.id)}
                  className="self-start text-[10px] text-gray-300 hover:text-gray-500 transition-colors opacity-0 group-hover:opacity-100"
                  title="Copy response"
                >
                  {copiedId === message.id ? '✓ Copied' : '⎘ Copy'}
                </button>
              )}

              {/* Thumbs up/down feedback */}
              {!isStreamingThis && sessionId && (
                <MessageFeedback messageId={message.id} sessionId={sessionId} />
              )}

              {/* Document cards attached to this message */}
              {documents?.[message.id]?.map((doc, idx) => (
                <div key={`${message.id}-doc-${idx}`} className="mt-2">
                  <DocumentCard document={doc} sessionId={sessionId || ''} />
                </div>
              ))}
            </div>
          );
        })}

        {/* Waiting for first token — show tool cards + status during the wait */}
        {isWaitingForFirstToken && (
          <div className="flex flex-col gap-1.5">
            <span className="text-[10px] font-semibold text-[#003366] uppercase tracking-wider">
              Eagle
            </span>

            {/* Pending tool + thinking chips — rendered as they arrive from SSE */}
            {(pendingToolCalls.length > 0 || pendingThinkingBlocks.length > 0) && (
              <>
                <div className="flex flex-wrap gap-1.5 mb-2">
                  {pendingThinkingBlocks.map((block) => (
                    <ThinkingChip key={`pending-think-${block.blockId}`} block={block} />
                  ))}
                  {pendingToolCalls.map((tc) => (
                    <ToolUseDisplay
                      key={tc.toolUseId}
                      toolName={tc.toolName}
                      input={tc.input}
                      status={tc.status}
                      result={tc.result}
                      isClientSide={tc.isClientSide}
                      sessionId={sessionId}
                      streamingInput={tc.streamingInput}
                    />
                  ))}
                </div>
                {pendingToolCalls
                  .filter((tc) => tc.toolName === 'code')
                  .map((tc) => (
                    <CodeOutput key={`code-${tc.toolUseId}`} tc={tc} />
                  ))}
              </>
            )}

            {/* Phase-aware status indicator */}
            <WaitingIndicator
              agentStatus={agentStatus}
              hasToolCalls={
                pendingToolCalls.length > 0 || pendingThinkingBlocks.length > 0
              }
              isActive={isWaitingForFirstToken}
            />
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>
    </div>
  );
}
