'use client';

import { useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { ChatMessage, DocumentInfo } from '@/types/chat';
import DocumentCard from './document-card';

interface SimpleMessageListProps {
    messages: ChatMessage[];
    isTyping: boolean;
    documents?: Record<string, DocumentInfo[]>;
    sessionId?: string;
}

export default function SimpleMessageList({ messages, isTyping, documents, sessionId }: SimpleMessageListProps) {
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

                    return (
                        <div key={message.id} className="group flex flex-col gap-1.5">
                            <span className="text-[10px] font-semibold text-[#003366] uppercase tracking-wider">
                                🦅 Eagle
                            </span>
                            <div className="text-sm text-gray-800 leading-relaxed">
                                <ReactMarkdown
                                    components={{
                                        p: ({ children }) => (
                                            <p className="mb-3 last:mb-0">{children}</p>
                                        ),
                                        ul: ({ children }) => (
                                            <ul className="list-disc ml-5 mb-3 space-y-1">{children}</ul>
                                        ),
                                        ol: ({ children }) => (
                                            <ol className="list-decimal ml-5 mb-3 space-y-1">{children}</ol>
                                        ),
                                        li: ({ children }) => (
                                            <li className="leading-relaxed">{children}</li>
                                        ),
                                        strong: ({ children }) => (
                                            <strong className="font-semibold text-gray-900">{children}</strong>
                                        ),
                                        h1: ({ children }) => (
                                            <h1 className="text-lg font-bold text-gray-900 mb-2 mt-4">{children}</h1>
                                        ),
                                        h2: ({ children }) => (
                                            <h2 className="text-base font-semibold text-gray-900 mb-2 mt-3">{children}</h2>
                                        ),
                                        h3: ({ children }) => (
                                            <h3 className="text-sm font-semibold text-gray-900 mb-1 mt-2">{children}</h3>
                                        ),
                                        code: ({ children }) => (
                                            <code className="bg-gray-100 px-1.5 py-0.5 rounded text-xs font-mono text-gray-800">
                                                {children}
                                            </code>
                                        ),
                                        pre: ({ children }) => (
                                            <pre className="bg-gray-100 p-4 rounded-lg overflow-x-auto my-3 text-xs font-mono">
                                                {children}
                                            </pre>
                                        ),
                                        blockquote: ({ children }) => (
                                            <blockquote className="border-l-2 border-gray-300 pl-4 italic text-gray-600 my-2">
                                                {children}
                                            </blockquote>
                                        ),
                                    }}
                                >
                                    {/* Append block cursor character inline with content while streaming.
                                        This naturally lands at the end of the last rendered line. */}
                                    {isStreamingThis ? message.content + '▌' : message.content}
                                </ReactMarkdown>
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

                            {/* Document cards attached to this message */}
                            {documents?.[message.id]?.map((doc, idx) => (
                                <div key={`${message.id}-doc-${idx}`} className="mt-2">
                                    <DocumentCard document={doc} sessionId={sessionId || ''} />
                                </div>
                            ))}
                        </div>
                    );
                })}

                {/* Waiting for first token — shown only before any assistant text arrives */}
                {isWaitingForFirstToken && (
                    <div className="flex flex-col gap-1.5">
                        <span className="text-[10px] font-semibold text-[#003366] uppercase tracking-wider">
                            🦅 Eagle
                        </span>
                        <div className="flex items-center h-5">
                            <span className="inline-block w-[2px] h-4 bg-[#003366] rounded-sm animate-pulse" />
                        </div>
                    </div>
                )}

                <div ref={messagesEndRef} />
            </div>
        </div>
    );
}
