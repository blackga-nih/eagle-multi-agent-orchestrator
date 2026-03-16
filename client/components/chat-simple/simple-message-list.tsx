'use client';

import { useEffect, useRef, useState, useMemo, memo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ChatMessage, DocumentInfo } from '@/types/chat';
import DocumentCard from './document-card';
import ToolUseDisplay, { extractKnowledgeSources, KnowledgeSource } from './tool-use-display';
import CodeSandboxRenderer from './code-sandbox-renderer';
import TraceStory from './trace-story';
import { ToolCallsByMessageId, TrackedToolCall } from './simple-chat-interface';
import { CodeResult } from '@/lib/client-tools';

/** Strip <thinking>...</thinking> blocks from model output. */
function stripThinkingBlocks(text: string): string {
  return text
    .replace(/<thinking>[\s\S]*?<\/thinking>/g, '')
    .replace(/<thinking>[\s\S]*$/g, '')  // unclosed mid-stream
    .trim();
}

/** Shared markdown components — defined once, reused across all messages. */
const mdComponents = {
    p: ({ children }: any) => (
        <p className="mb-3 last:mb-0">{children}</p>
    ),
    ul: ({ children }: any) => (
        <ul className="list-disc ml-5 mb-3 space-y-1">{children}</ul>
    ),
    ol: ({ children }: any) => (
        <ol className="list-decimal ml-5 mb-3 space-y-1">{children}</ol>
    ),
    li: ({ children }: any) => (
        <li className="leading-relaxed">{children}</li>
    ),
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
            <table className="min-w-full divide-y divide-gray-200 text-sm">
                {children}
            </table>
        </div>
    ),
    thead: ({ children }: any) => (
        <thead className="bg-gray-50">{children}</thead>
    ),
    tbody: ({ children }: any) => (
        <tbody className="divide-y divide-gray-100 bg-white">{children}</tbody>
    ),
    tr: ({ children }: any) => (
        <tr className="hover:bg-gray-50">{children}</tr>
    ),
    th: ({ children }: any) => (
        <th className="px-3 py-2 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider whitespace-nowrap">
            {children}
        </th>
    ),
    td: ({ children }: any) => (
        <td className="px-3 py-2 text-sm text-gray-700">{children}</td>
    ),
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

interface SimpleMessageListProps {
    messages: ChatMessage[];
    isTyping: boolean;
    documents?: Record<string, DocumentInfo[]>;
    sessionId?: string;
    /** Tool call state keyed by message ID — populated from SSE tool_use events. */
    toolCallsByMsg?: ToolCallsByMessageId;
}

/** Render code sandbox output below a code tool call card, if output exists. */
function CodeOutput({ tc }: { tc: TrackedToolCall }) {
    if (tc.toolName !== 'code') return null;
    if (tc.status !== 'done') return null;
    if (!tc.result?.result) return null;

    const codeResult = tc.result.result as CodeResult;
    const lang = String(tc.input.language ?? 'javascript');

    const hasOutput =
        (Array.isArray(codeResult.logs) && codeResult.logs.length > 0) ||
        Boolean(codeResult.html);

    if (!hasOutput) return null;

    return (
        <CodeSandboxRenderer
            language={lang}
            source={String(tc.input.source ?? '')}
            result={codeResult}
        />
    );
}

/** Source authority → chip color */
const AUTHORITY_CHIP: Record<string, string> = {
    mandatory:   'bg-red-50 text-red-700 border-red-200',
    regulatory:  'bg-orange-50 text-orange-700 border-orange-200',
    policy:      'bg-blue-50 text-blue-700 border-blue-200',
    guidance:    'bg-green-50 text-green-700 border-green-200',
    template:    'bg-violet-50 text-violet-700 border-violet-200',
    reference:   'bg-gray-50 text-gray-600 border-gray-200',
    far_regulation: 'bg-amber-50 text-amber-700 border-amber-200',
};

function SourceChips({ toolCalls }: { toolCalls: TrackedToolCall[] }) {
    // Collect all unique knowledge sources from the message's tool calls
    const sources = useMemo<KnowledgeSource[]>(() => {
        const seen = new Set<string>();
        const result: KnowledgeSource[] = [];
        for (const tc of toolCalls) {
            if (tc.status !== 'done') continue;
            if (!['knowledge_search', 'knowledge_fetch', 'search_far', 'query_compliance_matrix'].includes(tc.toolName)) continue;
            for (const src of extractKnowledgeSources(tc.toolName, tc.result ?? null)) {
                const key = src.document_id || src.title;
                if (!seen.has(key)) {
                    seen.add(key);
                    result.push(src);
                }
            }
        }
        return result;
    }, [toolCalls]);

    if (sources.length === 0) return null;

    return (
        <div className="flex items-center gap-1 flex-wrap mt-1.5">
            <span className="text-[9px] text-gray-400 font-medium uppercase tracking-wider shrink-0">Sources</span>
            {sources.map((src, i) => {
                const authority = src.source_tool === 'search_far' ? 'far_regulation' : (src.authority_level ?? 'reference');
                const chipClass = AUTHORITY_CHIP[authority] ?? AUTHORITY_CHIP.reference;
                const title = src.title.length > 28 ? src.title.slice(0, 27) + '…' : src.title;
                const handleClick = () => {
                    if (src.s3_key) {
                        window.open(`/documents/${encodeURIComponent(src.s3_key)}`, '_blank');
                    }
                };
                return (
                    <button
                        key={src.document_id || i}
                        type="button"
                        title={src.title + (src.summary ? '\n' + src.summary.slice(0, 120) : '')}
                        onClick={src.s3_key ? handleClick : undefined}
                        className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-[9px] font-medium transition
                                    ${chipClass}
                                    ${src.s3_key ? 'cursor-pointer hover:opacity-80' : 'cursor-default'}`}
                    >
                        <span>{src.source_tool === 'knowledge_fetch' ? '📖' : src.source_tool === 'search_far' ? '📜' : '📄'}</span>
                        {title}
                        {src.confidence_score ? (
                            <span className="opacity-60">{(src.confidence_score * 100).toFixed(0)}%</span>
                        ) : null}
                    </button>
                );
            })}
        </div>
    );
}

// ---------------------------------------------------------------------------
// TraceModal — full-width slide-over showing the Langfuse trace story
// ---------------------------------------------------------------------------

function TraceModal({ sessionId, onClose }: { sessionId: string; onClose: () => void }) {
    return (
        <div
            className="fixed inset-0 z-50 flex items-stretch justify-end"
            onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
        >
            {/* Backdrop */}
            <div className="absolute inset-0 bg-black/30" onClick={onClose} />

            {/* Panel */}
            <div className="relative z-10 w-full max-w-2xl bg-white shadow-2xl flex flex-col h-full">
                {/* Header */}
                <div className="flex items-center justify-between px-5 py-3.5 border-b border-gray-200 bg-[#F5F7FA] shrink-0">
                    <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-[#003366]">Trace Story</span>
                        <span className="text-[10px] text-gray-400 font-mono truncate max-w-[200px]">{sessionId}</span>
                    </div>
                    <button
                        onClick={onClose}
                        className="text-gray-400 hover:text-gray-600 transition text-lg leading-none px-1"
                        title="Close"
                    >
                        ×
                    </button>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto p-5">
                    <TraceStory sessionId={sessionId} />
                </div>
            </div>
        </div>
    );
}

export default function SimpleMessageList({
    messages,
    isTyping,
    documents,
    sessionId,
    toolCallsByMsg = {},
}: SimpleMessageListProps) {
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const [copiedId, setCopiedId] = useState<string | null>(null);
    const [traceOpen, setTraceOpen] = useState(false);

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }, [messages, isTyping]);

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
            <div className="max-w-2xl mx-auto px-6 py-8 flex flex-col gap-8">
                {messages.map((message, index) => {
                    const isLastMessage = index === lastIdx;
                    const isStreamingThis =
                        isTyping && isLastMessage && message.role === 'assistant';

                    if (message.role === 'user') {
                        return (
                            <div key={message.id} className="flex flex-col items-end gap-0.5">
                                <span className="text-[10px] font-medium text-gray-400 uppercase tracking-wider">
                                    You
                                </span>
                                <p className="text-sm text-gray-700 text-right leading-relaxed max-w-lg whitespace-pre-wrap">
                                    {message.content}
                                </p>
                            </div>
                        );
                    }

                    // Retrieve tool calls associated with this assistant message
                    const toolCalls = toolCallsByMsg[message.id] ?? [];

                    return (
                        <div key={message.id} className="group flex flex-col gap-1.5">
                            <span className="text-[10px] font-semibold text-[#003366] uppercase tracking-wider">
                                🦅 Eagle
                            </span>

                            {/* Tool call indicators rendered above the text response */}
                            {toolCalls.length > 0 && (
                                <div className="flex flex-col gap-1 mb-1">
                                    {toolCalls.map((tc) => (
                                        <div key={tc.toolUseId}>
                                            <ToolUseDisplay
                                                toolName={tc.toolName}
                                                input={tc.input}
                                                status={tc.status}
                                                result={tc.result}
                                                isClientSide={tc.isClientSide}
                                                sessionId={sessionId}
                                            />
                                            <CodeOutput tc={tc} />
                                        </div>
                                    ))}
                                </div>
                            )}

                            <div className="text-sm text-gray-800 leading-relaxed">
                                {isStreamingThis ? (
                                    // Streaming: use inline ReactMarkdown (content changes every token)
                                    <ReactMarkdown remarkPlugins={remarkPlugins} components={mdComponents}>
                                        {stripThinkingBlocks(message.content) + ' ...'}
                                    </ReactMarkdown>
                                ) : (
                                    // Completed: memoized — won't re-render when other messages update
                                    <MemoizedMarkdown content={stripThinkingBlocks(message.content)} />
                                )}
                            </div>

                            {/* Copy + View trace buttons — visible on hover after streaming completes */}
                            {!isStreamingThis && (
                                <div className="flex items-center gap-3 opacity-0 group-hover:opacity-100 transition-opacity">
                                    <button
                                        onClick={() => copyToClipboard(stripThinkingBlocks(message.content), message.id)}
                                        className="text-[10px] text-gray-300 hover:text-gray-500 transition-colors"
                                        title="Copy response"
                                    >
                                        {copiedId === message.id ? '✓ Copied' : '⎘ Copy'}
                                    </button>
                                    {sessionId && (
                                        <button
                                            onClick={() => setTraceOpen(true)}
                                            className="text-[10px] text-gray-300 hover:text-[#003366] transition-colors"
                                            title="View Langfuse trace story"
                                        >
                                            ⎆ Trace
                                        </button>
                                    )}
                                </div>
                            )}

                            {/* Inline source chips — KB documents & FAR sections cited */}
                            {!isStreamingThis && toolCalls.length > 0 && (
                                <SourceChips toolCalls={toolCalls} />
                            )}

                            {/* Document cards attached to this message —
                                skip docs already rendered inline by ToolUseDisplay's
                                DocumentResultCard (create_document tool calls with results). */}
                            {(() => {
                                const hasCreateDocTool = toolCalls.some(
                                    (tc) => tc.toolName === 'create_document' && tc.status === 'done' && tc.result,
                                );
                                if (hasCreateDocTool) return null;
                                return documents?.[message.id]?.map((doc, idx) => (
                                    <div key={`${message.id}-doc-${idx}`} className="mt-2">
                                        <DocumentCard document={doc} sessionId={sessionId || ''} />
                                    </div>
                                ));
                            })()}
                        </div>
                    );
                })}

                {/* Waiting for first token — shown only before any assistant text arrives */}
                {isWaitingForFirstToken && (
                    <div className="flex flex-col gap-1.5">
                        <span className="text-[10px] font-semibold text-[#003366] uppercase tracking-wider">
                            🦅 Eagle
                        </span>
                        <div className="flex items-center gap-1 h-5">
                            <div className="typing-dot" />
                            <div className="typing-dot" />
                            <div className="typing-dot" />
                        </div>
                    </div>
                )}

                <div ref={messagesEndRef} />
            </div>

            {traceOpen && sessionId && (
                <TraceModal sessionId={sessionId} onClose={() => setTraceOpen(false)} />
            )}
        </div>
    );
}
