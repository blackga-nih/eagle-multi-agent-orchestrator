'use client';

import { useEffect, useRef, useState, useMemo, memo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ChatMessage, DocumentInfo } from '@/types/chat';
import DocumentCard from './document-card';
import ToolUseDisplay from './tool-use-display';
import CodeSandboxRenderer from './code-sandbox-renderer';
import { ToolCallsByMessageId, TrackedToolCall } from './simple-chat-interface';
import { CodeResult } from '@/lib/client-tools';

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

export default function SimpleMessageList({
    messages,
    isTyping,
    documents,
    sessionId,
    toolCallsByMsg = {},
}: SimpleMessageListProps) {
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const [copiedId, setCopiedId] = useState<string | null>(null);

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
                                        {message.content + ' ...'}
                                    </ReactMarkdown>
                                ) : (
                                    // Completed: memoized — won't re-render when other messages update
                                    <MemoizedMarkdown content={message.content} />
                                )}
                            </div>

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
        </div>
    );
}
