'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import SimpleMessageList from './simple-message-list';
import SimpleWelcome from './simple-welcome';
import SimpleQuickActions from './simple-quick-actions';
import SlashCommandPicker from '@/components/chat/slash-command-picker';
import { useAgentStream } from '@/hooks/use-agent-stream';
import { useSlashCommands } from '@/hooks/use-slash-commands';
import { useSession } from '@/contexts/session-context';
import { useAuth } from '@/contexts/auth-context';
import { SlashCommand } from '@/lib/slash-commands';
import { ChatMessage, DocumentInfo } from '@/types/chat';
import { saveGeneratedDocument } from '@/lib/document-store';

export default function SimpleChatInterface() {
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [input, setInput] = useState('');
    const [isLoadingSession, setIsLoadingSession] = useState(true);
    const [documents, setDocuments] = useState<Record<string, DocumentInfo[]>>({});

    const { currentSessionId, saveSession, loadSession } = useSession();
    const { getToken } = useAuth();

    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const lastAssistantIdRef = useRef<string | null>(null);

    // Load session data
    useEffect(() => {
        if (!currentSessionId) {
            setIsLoadingSession(false);
            return;
        }
        const sessionData = loadSession(currentSessionId);
        if (sessionData) {
            setMessages(sessionData.messages);
            setDocuments(sessionData.documents || {});
        } else {
            setMessages([]);
            setDocuments({});
        }
        setIsLoadingSession(false);
    }, [currentSessionId, loadSession]);

    // Auto-save session
    const saveSessionDebounced = useCallback(() => {
        if (messages.length > 0) {
            saveSession(messages, {}, documents);
        }
    }, [messages, documents, saveSession]);

    useEffect(() => {
        const timeoutId = setTimeout(saveSessionDebounced, 500);
        return () => clearTimeout(timeoutId);
    }, [saveSessionDebounced]);

    // Slash command handling
    const handleCommandSelect = (command: SlashCommand) => {
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
    } = useSlashCommands({ onCommandSelect: handleCommandSelect });

    // Agent stream
    const { sendQuery, isStreaming, error } = useAgentStream({
        getToken,
        onMessage: (msg) => {
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
            setMessages((prev) => [...prev, newMessage]);
        },
        onDocumentGenerated: (doc) => {
            // Attach document to latest assistant message
            const attachTo = lastAssistantIdRef.current;
            if (attachTo) {
                setDocuments((prev) => ({
                    ...prev,
                    [attachTo]: [...(prev[attachTo] || []), doc],
                }));
            }

            // Persist to localStorage for Packages & Documents pages
            if (currentSessionId) {
                const title =
                    messages.find((m) => m.role === 'user')?.content.slice(0, 80) ||
                    'Untitled Package';
                saveGeneratedDocument(doc, currentSessionId, title);
            }
        },
    });


    // Auto-resize textarea
    const adjustTextareaHeight = () => {
        const el = textareaRef.current;
        if (el) {
            el.style.height = 'auto';
            el.style.height = Math.min(el.scrollHeight, 160) + 'px';
        }
    };

    useEffect(() => {
        adjustTextareaHeight();
    }, [input]);

    const handleSend = async () => {
        if (!input.trim() || isStreaming) return;

        const userMessage: ChatMessage = {
            id: Date.now().toString(),
            role: 'user',
            content: input,
            timestamp: new Date(),
        };
        lastAssistantIdRef.current = null;
        setMessages((prev) => [...prev, userMessage]);
        const query = input;
        setInput('');

        await sendQuery(query, currentSessionId);
    };

    const insertText = (text: string) => {
        setInput(text);
        textareaRef.current?.focus();
    };

    const hasMessages = messages.length > 0;

    return (
        <div className="h-full flex flex-col bg-[#F5F7FA]">
            {/* Quick actions bar */}
            <SimpleQuickActions onAction={insertText} />

            {/* Main content area */}
            {!hasMessages && !isLoadingSession ? (
                <SimpleWelcome onAction={insertText} />
            ) : (
                <SimpleMessageList
                    messages={messages}
                    isTyping={isStreaming}
                    documents={documents}
                    sessionId={currentSessionId}
                />
            )}

            {/* Input footer */}
            <footer className="bg-white border-t border-[#D8DEE6] px-6 py-3 shrink-0">
                <div className="max-w-3xl mx-auto">
                    {error && (
                        <div className="mb-2 px-3 py-1.5 bg-red-50 border border-red-200 rounded-lg text-red-700 text-xs">
                            {error}
                        </div>
                    )}
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
                            placeholder={isStreaming ? 'Waiting for response\u2026' : 'Ask EAGLE about acquisitions, or type / for commands\u2026'}
                            disabled={isStreaming}
                            rows={1}
                            className={`flex-1 resize-none px-4 py-3 bg-white border border-[#D8DEE6] rounded-xl focus:outline-none focus:ring-2 focus:ring-[#2196F3]/30 focus:border-[#2196F3] transition-all text-sm leading-relaxed ${isStreaming ? 'opacity-50' : ''}`}
                            style={{ maxHeight: 160 }}
                        />
                        <button
                            onClick={handleSend}
                            disabled={!input.trim() || isStreaming}
                            className="p-3 bg-[#003366] text-white rounded-xl hover:bg-[#004488] disabled:opacity-30 transition-all shadow-md shrink-0"
                        >
                            <span className="text-base">&#10148;</span>
                        </button>
                    </div>
                    <p className="text-center text-[10px] text-[#8896A6] mt-2">
                        EAGLE &middot; National Cancer Institute &middot; Powered by Claude (Anthropic SDK)
                    </p>
                </div>
            </footer>
        </div>
    );
}
