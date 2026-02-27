import { useEffect, useRef, useState } from 'react';
import { Message } from './chat-interface';
import ReactMarkdown from 'react-markdown';
import { Brain, ChevronDown, ChevronUp, Copy, Check } from 'lucide-react';
import InitialIntakeForm from '../forms/initial-intake-form';
import InlineEquipmentForm from './inline-equipment-form';
import InlineFundingForm from './inline-funding-form';
import WelcomeMessage from './welcome-message';
import SuggestedPrompts from './suggested-prompts';

interface MessageListProps {
    messages: Message[];
    isTyping: boolean;
    streamingMessageId?: string;
    activeForm?: 'initial' | 'equipment' | 'funding' | null;
    onInitialIntakeSubmit?: (data: any) => void;
    onEquipmentSubmit?: (data: any) => void;
    onFundingSubmit?: (data: any) => void;
    onFormDismiss?: () => void;
    onSuggestedPromptSelect?: (prompt: string) => void;
    showWelcome?: boolean;
}

export default function MessageList({
    messages,
    isTyping,
    streamingMessageId,
    activeForm,
    onInitialIntakeSubmit,
    onEquipmentSubmit,
    onFundingSubmit,
    onFormDismiss,
    onSuggestedPromptSelect,
    showWelcome = true
}: MessageListProps) {
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const [expandedReasoning, setExpandedReasoning] = useState<Record<string, boolean>>({});
    const [copiedId, setCopiedId] = useState<string | null>(null);

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({
            // Use instant scroll while streaming so the view tracks new tokens
            // without the jitter that smooth causes on rapid updates
            behavior: streamingMessageId ? 'instant' : 'smooth',
            block: 'end',
        });
    }, [messages, isTyping, activeForm, streamingMessageId]);

    const toggleReasoning = (id: string) => {
        setExpandedReasoning(prev => ({ ...prev, [id]: !prev[id] }));
    };

    const copyToClipboard = async (text: string, id: string) => {
        try {
            await navigator.clipboard.writeText(text);
            setCopiedId(id);
            setTimeout(() => setCopiedId(null), 2000);
        } catch {
            // Clipboard API not available
        }
    };

    const hasMessages = messages.length > 0;

    return (
        <div className="h-full overflow-y-auto bg-gray-50/50 p-6 custom-scrollbar">
            <div className="container mx-auto max-w-4xl space-y-6">
                {/* Welcome message and large prompts when no messages */}
                {showWelcome && !hasMessages && !activeForm && (
                    <>
                        <WelcomeMessage />
                        {onSuggestedPromptSelect && (
                            <div className="py-4">
                                <SuggestedPrompts onSelect={onSuggestedPromptSelect} compact={false} />
                            </div>
                        )}
                    </>
                )}

                {messages.map((message) => (
                    <div
                        key={message.id}
                        className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'} msg-slide-in`}
                    >
                        {/* User messages */}
                        {message.role === 'user' && (
                            <div className="max-w-[85%]">
                                <div className="text-[10px] font-bold uppercase tracking-wider text-gray-400 text-right mb-1 mr-1">
                                    You
                                </div>
                                <div className="rounded-2xl rounded-br-sm shadow-sm bg-nci-user-bubble border border-nci-user-border p-4">
                                    <div className="msg-bubble msg-bubble-user text-gray-900 leading-relaxed">
                                        <ReactMarkdown
                                            components={{
                                                p: ({ children }) => <p className="mb-3 last:mb-0">{children}</p>,
                                                ul: ({ children }) => <ul className="list-disc ml-5 mb-3 space-y-1">{children}</ul>,
                                                ol: ({ children }) => <ol className="list-decimal ml-5 mb-3 space-y-1">{children}</ol>,
                                                strong: ({ children }) => <strong className="font-bold">{children}</strong>,
                                            }}
                                        >
                                            {message.content}
                                        </ReactMarkdown>
                                    </div>
                                    <div className="text-[10px] mt-3 font-medium text-gray-500">
                                        {message.timestamp.toLocaleTimeString([], {
                                            hour: '2-digit',
                                            minute: '2-digit',
                                        })}
                                    </div>
                                </div>
                            </div>
                        )}

                        {/* Assistant messages */}
                        {message.role === 'assistant' && (
                            <div className="max-w-[85%] msg-wrapper">
                                <div className="rounded-2xl rounded-bl-sm shadow-sm bg-white border border-gray-200 p-5 relative">
                                    {/* Header with EAGLE badge and copy button */}
                                    <div className="flex items-center justify-between mb-3">
                                        <div className="flex items-center gap-2">
                                            <div className="w-8 h-8 rounded-xl bg-nci-blue flex items-center justify-center text-white text-xs font-bold shadow-sm">
                                                E
                                            </div>
                                            <div>
                                                <div className="text-xs font-bold text-gray-900 tracking-tight">EAGLE</div>
                                                <div className="text-[9px] text-nci-info font-bold uppercase tracking-wider">Assistant</div>
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-1">
                                            {message.reasoning && (
                                                <button
                                                    onClick={() => toggleReasoning(message.id)}
                                                    className="flex items-center gap-1.5 px-2 py-1 rounded-md hover:bg-gray-50 text-[10px] font-bold text-gray-400 hover:text-nci-blue transition-colors"
                                                >
                                                    <Brain className="w-3 h-3" />
                                                    Reasoning {expandedReasoning[message.id] ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                                                </button>
                                            )}
                                            <button
                                                onClick={() => copyToClipboard(message.content, message.id)}
                                                className="copy-btn p-1.5 rounded-md hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors"
                                                title="Copy message"
                                            >
                                                {copiedId === message.id ? (
                                                    <Check className="w-3.5 h-3.5 text-green-500" />
                                                ) : (
                                                    <Copy className="w-3.5 h-3.5" />
                                                )}
                                            </button>
                                        </div>
                                    </div>

                                    {/* Reasoning panel */}
                                    {message.reasoning && expandedReasoning[message.id] && (
                                        <div className="mb-4 p-3 bg-gray-50 border border-gray-100 rounded-xl text-[11px] text-gray-600 leading-relaxed italic animate-in slide-in-from-top-2 duration-200">
                                            <div className="font-bold text-[9px] uppercase tracking-widest text-gray-400 mb-1 flex items-center gap-1">
                                                <Brain className="w-2.5 h-2.5" /> Agent Intent Log
                                            </div>
                                            {message.reasoning}
                                        </div>
                                    )}

                                    {/* Message content */}
                                    <div className="msg-bubble text-gray-700 leading-relaxed">
                                        <ReactMarkdown
                                            components={{
                                                p: ({ children }) => <p className="mb-3 last:mb-0">{children}</p>,
                                                ul: ({ children }) => <ul className="list-disc ml-5 mb-3 space-y-1">{children}</ul>,
                                                ol: ({ children }) => <ol className="list-decimal ml-5 mb-3 space-y-1">{children}</ol>,
                                                strong: ({ children }) => <strong className="font-bold">{children}</strong>,
                                            }}
                                        >
                                            {message.id === streamingMessageId
                                                ? message.content + '▌'
                                                : message.content}
                                        </ReactMarkdown>
                                    </div>
                                    <div className="text-[10px] mt-3 font-medium text-gray-400">
                                        {message.timestamp.toLocaleTimeString([], {
                                            hour: '2-digit',
                                            minute: '2-digit',
                                        })}
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>
                ))}

                {/* Inline forms appear as EAGLE messages */}
                {activeForm && (
                    <div className="flex justify-start">
                        <div className="max-w-[85%]">
                            {activeForm === 'initial' && onInitialIntakeSubmit && (
                                <InitialIntakeForm onSubmit={onInitialIntakeSubmit} />
                            )}
                            {activeForm === 'equipment' && onEquipmentSubmit && onFormDismiss && (
                                <InlineEquipmentForm onSubmit={onEquipmentSubmit} onDismiss={onFormDismiss} />
                            )}
                            {activeForm === 'funding' && onFundingSubmit && onFormDismiss && (
                                <InlineFundingForm onSubmit={onFundingSubmit} onDismiss={onFormDismiss} />
                            )}
                        </div>
                    </div>
                )}

                {/* Typing indicator — only shown while waiting for the first token.
                    Once the streaming message starts appearing, the cursor (▌) inside
                    the message bubble takes over as the "still typing" signal. */}
                {isTyping && !streamingMessageId && (
                    <div className="flex justify-start msg-slide-in">
                        <div className="rounded-2xl rounded-bl-sm p-4 bg-white border border-gray-200 shadow-sm">
                            <div className="flex items-center gap-2 mb-2">
                                <div className="w-6 h-6 rounded-lg bg-nci-blue flex items-center justify-center text-white text-[10px] font-bold">
                                    E
                                </div>
                                <span className="text-xs font-semibold text-gray-700">EAGLE</span>
                            </div>
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
        </div>
    );
}
