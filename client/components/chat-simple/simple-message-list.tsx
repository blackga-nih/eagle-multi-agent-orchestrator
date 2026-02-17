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

    return (
        <div className="flex-1 overflow-y-auto px-6 py-5 flex flex-col gap-4">
            {messages.map((message) => (
                <div key={message.id}>
                    <div
                        className={`max-w-[80%] msg-slide-in ${
                            message.role === 'user' ? 'self-end ml-auto' : 'self-start'
                        }`}
                    >
                        {/* Label */}
                        <div className={`text-[11px] font-semibold uppercase tracking-wide mb-1 ${
                            message.role === 'user'
                                ? 'text-[#8896A6] text-right'
                                : 'text-[#003366]'
                        }`}>
                            {message.role === 'user' ? 'You' : '\uD83E\uDD85 EAGLE'}
                        </div>

                        {/* Bubble */}
                        <div className={`relative group rounded-xl px-4 py-3 text-sm leading-relaxed shadow-sm ${
                            message.role === 'user'
                                ? 'bg-[#E3F2FD] border border-[#BBDEFB] text-[#1A1A2E] rounded-br-sm'
                                : 'bg-white border border-[#E8ECF1] text-[#1A1A2E] rounded-bl-sm'
                        }`}>
                            {/* Copy button for assistant messages */}
                            {message.role === 'assistant' && (
                                <button
                                    onClick={() => copyToClipboard(message.content, message.id)}
                                    className="absolute top-2 right-2 text-xs px-1.5 py-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity hover:bg-gray-100"
                                    title="Copy"
                                >
                                    {copiedId === message.id ? '\u2713' : '\uD83D\uDCCB'}
                                </button>
                            )}

                            <div className={`msg-bubble ${message.role === 'assistant' ? 'pr-8' : ''}`}>
                                <ReactMarkdown
                                    components={{
                                        p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                                        ul: ({ children }) => <ul className="list-disc ml-5 mb-2 space-y-1">{children}</ul>,
                                        ol: ({ children }) => <ol className="list-decimal ml-5 mb-2 space-y-1">{children}</ol>,
                                        strong: ({ children }) => <strong className="font-bold">{children}</strong>,
                                        code: ({ children }) => <code className="bg-gray-100 px-1 py-0.5 rounded text-xs font-mono">{children}</code>,
                                        pre: ({ children }) => <pre className="bg-gray-100 p-3 rounded-lg overflow-x-auto my-2 text-xs">{children}</pre>,
                                    }}
                                >
                                    {message.content}
                                </ReactMarkdown>
                            </div>
                        </div>

                        {/* Timestamp */}
                        <div className={`text-[10px] text-[#B0BEC5] mt-1.5 ${
                            message.role === 'user' ? 'text-right' : ''
                        }`}>
                            {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </div>
                    </div>

                    {/* Document cards - shown below assistant messages that generated documents */}
                    {message.role === 'assistant' && documents?.[message.id]?.map((doc, idx) => (
                        <div key={`${message.id}-doc-${idx}`} className="max-w-[80%] mt-2 self-start">
                            <DocumentCard
                                document={doc}
                                sessionId={sessionId || ''}
                            />
                        </div>
                    ))}
                </div>
            ))}

            {/* Typing indicator */}
            {isTyping && (
                <div className="self-start max-w-[80%] msg-slide-in">
                    <div className="text-[11px] font-semibold uppercase tracking-wide mb-1 text-[#003366]">
                        {'\uD83E\uDD85'} EAGLE
                    </div>
                    <div className="rounded-xl rounded-bl-sm px-4 py-3 bg-white border border-[#E8ECF1] shadow-sm">
                        <div className="flex items-center gap-1.5 px-1 py-1">
                            <div className="typing-dot"></div>
                            <div className="typing-dot"></div>
                            <div className="typing-dot"></div>
                        </div>
                    </div>
                </div>
            )}

            <div ref={messagesEndRef} />
        </div>
    );
}
