import { useEffect, useRef, useState } from 'react';
import { Message } from './chat-interface';
import ReactMarkdown from 'react-markdown';
import { Loader2, Brain, ChevronDown, ChevronUp } from 'lucide-react';
import InitialIntakeForm from '../forms/initial-intake-form';
import InlineEquipmentForm from './inline-equipment-form';
import InlineFundingForm from './inline-funding-form';
import WelcomeMessage from './welcome-message';
import SuggestedPrompts from './suggested-prompts';

interface MessageListProps {
    messages: Message[];
    isTyping: boolean;
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

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({
            behavior: 'smooth',
            block: 'end',
        });
    }, [messages, isTyping, activeForm]);

    const toggleReasoning = (id: string) => {
        setExpandedReasoning(prev => ({ ...prev, [id]: !prev[id] }));
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
                        className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'} animate-in fade-in slide-in-from-bottom-2 duration-300`}
                    >
                        <div
                            className={`max-w-[85%] rounded-2xl shadow-sm ${message.role === 'user'
                                ? 'bg-blue-600 text-white p-4 shadow-blue-100'
                                : 'bg-white border border-gray-100 p-5'
                                }`}
                        >
                            {message.role === 'assistant' && (
                                <div className="flex items-center justify-between mb-3">
                                    <div className="flex items-center gap-2">
                                        <div className="w-8 h-8 rounded-xl bg-blue-600 flex items-center justify-center text-white text-xs font-bold shadow-sm shadow-blue-200">
                                            E
                                        </div>
                                        <div>
                                            <div className="text-xs font-bold text-gray-900 tracking-tight">EAGLE</div>
                                            <div className="text-[9px] text-blue-500 font-bold uppercase tracking-wider">Assistant</div>
                                        </div>
                                    </div>
                                    {message.reasoning && (
                                        <button
                                            onClick={() => toggleReasoning(message.id)}
                                            className="flex items-center gap-1.5 px-2 py-1 rounded-md hover:bg-gray-50 text-[10px] font-bold text-gray-400 hover:text-blue-600 transition-colors"
                                        >
                                            <Brain className="w-3 h-3" />
                                            Reasoning {expandedReasoning[message.id] ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                                        </button>
                                    )}
                                </div>
                            )}

                            {message.role === 'assistant' && message.reasoning && expandedReasoning[message.id] && (
                                <div className="mb-4 p-3 bg-gray-50 border border-gray-100 rounded-xl text-[11px] text-gray-600 leading-relaxed italic animate-in slide-in-from-top-2 duration-200">
                                    <div className="font-bold text-[9px] uppercase tracking-widest text-gray-400 mb-1 flex items-center gap-1">
                                        <Brain className="w-2.5 h-2.5" /> Agent Intent Log
                                    </div>
                                    {message.reasoning}
                                </div>
                            )}

                            <div className={message.role === 'user' ? 'text-white leading-relaxed' : 'text-gray-700 leading-relaxed'}>
                                <ReactMarkdown
                                    components={{
                                        p: ({ children }) => <p className="mb-3 last:mb-0">{children}</p>,
                                        ul: ({ children }) => <ul className="list-disc ml-5 mb-3 space-y-1">{children}</ul>,
                                        ol: ({ children }) => <ol className="list-decimal ml-5 mb-3 space-y-1">{children}</ol>,
                                        strong: ({ children }) => <strong className="font-bold text-current">{children}</strong>,
                                    }}
                                >
                                    {message.content}
                                </ReactMarkdown>
                            </div>
                            <div
                                className={`text-[10px] mt-3 font-medium ${message.role === 'user' ? 'text-blue-100 opacity-70' : 'text-gray-400'
                                    }`}
                            >
                                {message.timestamp.toLocaleTimeString([], {
                                    hour: '2-digit',
                                    minute: '2-digit',
                                })}
                            </div>
                        </div>
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

                {isTyping && (
                    <div className="flex justify-start">
                        <div className="max-w-[80%] rounded-lg p-4 bg-white border border-gray-200 shadow-sm">
                            <div className="flex items-center gap-2 mb-2">
                                <div className="w-6 h-6 rounded-full bg-blue-600 flex items-center justify-center text-white text-xs font-bold">
                                    E
                                </div>
                                <span className="text-sm font-semibold text-gray-700">EAGLE</span>
                            </div>
                            <div className="flex items-center gap-2 text-gray-500">
                                <Loader2 className="w-4 h-4 animate-spin" />
                                <span className="text-sm">Typing...</span>
                            </div>
                        </div>
                    </div>
                )}

                <div ref={messagesEndRef} />
            </div>
        </div>
    );
}
