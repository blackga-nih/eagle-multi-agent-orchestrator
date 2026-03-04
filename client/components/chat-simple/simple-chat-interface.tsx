'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import SimpleMessageList from './simple-message-list';
import SimpleWelcome from './simple-welcome';
import SimpleQuickActions from './simple-quick-actions';
import SlashCommandPicker from '@/components/chat/slash-command-picker';
import CommandPalette from './command-palette';
import { useAgentStream, ToolUseEvent } from '@/hooks/use-agent-stream';
import { useSlashCommands } from '@/hooks/use-slash-commands';
import { useSession } from '@/contexts/session-context';
import { useAuth } from '@/contexts/auth-context';
import { SlashCommand } from '@/lib/slash-commands';
import { ChatMessage, DocumentInfo } from '@/types/chat';
import { saveGeneratedDocument } from '@/lib/document-store';
import { ClientToolResult } from '@/lib/client-tools';
import { ToolStatus } from './tool-use-display';

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
}

/** Tool calls keyed by the parent message ID they belong to. */
export type ToolCallsByMessageId = Record<string, TrackedToolCall[]>;

export default function SimpleChatInterface() {
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    // In-flight streaming message kept separate — avoids React batching/duplicate-key issues.
    const [streamingMsg, setStreamingMsg] = useState<ChatMessage | null>(null);
    const streamingMsgRef = useRef<ChatMessage | null>(null);
    const [input, setInput] = useState('');
    const [isLoadingSession, setIsLoadingSession] = useState(true);
    const [documents, setDocuments] = useState<Record<string, DocumentInfo[]>>({});

    // Tool calls grouped by message ID — populated as SSE tool_use events arrive.
    const [toolCallsByMsg, setToolCallsByMsg] = useState<ToolCallsByMessageId>({});
    const [feedbackStatus, setFeedbackStatus] = useState<'idle' | 'sending' | 'done' | 'error'>('idle');
    // Stable ID for the current streaming message — reset on each sendQuery call.
    const streamingMsgIdRef = useRef<string>(`stream-${Date.now()}`);

    const { currentSessionId, saveSession, loadSession, writeMessageOptimistic, renameSession } = useSession();
    const { getToken } = useAuth();

    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const lastAssistantIdRef = useRef<string | null>(null);
    /** Track whether AI title has been generated for this session. */
    const titleGeneratedRef = useRef<Set<string>>(new Set());
    /** Store the first user message for title generation. */
    const firstUserMsgRef = useRef<string | null>(null);
    /** Ctrl+K command palette state. */
    const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false);

    // Global Ctrl+K keyboard shortcut
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
                e.preventDefault();
                setIsCommandPaletteOpen((v) => !v);
            }
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, []);

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
            // Mark existing sessions as already titled (don't re-generate)
            if (sessionData.messages.length > 0) {
                titleGeneratedRef.current.add(currentSessionId);
            }
        } else {
            setMessages([]);
            setDocuments({});
        }
        firstUserMsgRef.current = null;
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

    // -----------------------------------------------------------------------
    // Tool call tracking
    // -----------------------------------------------------------------------

    const upsertToolCall = useCallback((
        msgId: string,
        toolUseId: string,
        patch: Partial<TrackedToolCall>,
    ) => {
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
    }, []);

    // Agent stream
    const { sendQuery, isStreaming, error } = useAgentStream({
        getToken,
        sessionId: currentSessionId ?? undefined,

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
            streamingMsgRef.current = newMessage;
            setStreamingMsg(newMessage);
        },

        onComplete: () => {
            const completedMsg = streamingMsgRef.current;
            if (completedMsg) {
                lastAssistantIdRef.current = completedMsg.id;
                setMessages((prev) => [...prev, completedMsg]);

                // Migrate tool calls from the streaming ID to the committed message ID,
                // and mark any server-side tools still "pending" as "done" (subagent
                // delegations don't emit a result event — the text just streams in).
                const streamId = streamingMsgIdRef.current;
                setToolCallsByMsg((prev) => {
                    const calls = prev[streamId] ?? prev[completedMsg.id] ?? [];
                    if (calls.length === 0) return prev;
                    const finalized = calls.map((tc) =>
                        !tc.isClientSide && (tc.status === 'pending' || tc.status === 'running')
                            ? { ...tc, status: 'done' as const }
                            : tc
                    );
                    const next = { ...prev };
                    delete next[streamId];
                    next[completedMsg.id] = finalized;
                    return next;
                });

                // AI title generation — fire-and-forget on first assistant response
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
                        .catch(() => { /* title generation is best-effort */ });
                }
            }
            streamingMsgRef.current = null;
            setStreamingMsg(null);
        },

        onError: () => {
            streamingMsgRef.current = null;
            setStreamingMsg(null);
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

        onToolUse: (toolEvent: ToolUseEvent) => {
            // Associate tool calls with the current streaming message ID.
            const parentId = streamingMsgIdRef.current;

            if (toolEvent.result === undefined) {
                // Tool is starting — create entry with pending/running status.
                upsertToolCall(parentId, toolEvent.toolUseId, {
                    toolName: toolEvent.toolName,
                    input: toolEvent.input,
                    status: toolEvent.isClientSide ? 'running' : 'pending',
                    isClientSide: toolEvent.isClientSide,
                    result: undefined,
                });
            } else {
                // Client-side tool finished — update with result.
                const status: ToolStatus = toolEvent.result.success ? 'done' : 'error';
                upsertToolCall(parentId, toolEvent.toolUseId, {
                    status,
                    result: toolEvent.result,
                });
            }
        },
    });


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
                        conversation_snapshot: messages.map((m) => ({
                            role: m.role,
                            content: m.content,
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
        // Reset streaming message ID for the new turn
        streamingMsgIdRef.current = `stream-${Date.now()}`;
        setMessages((prev) => [...prev, userMessage]);
        // Optimistic write to IndexedDB — fire-and-forget, never blocks send
        writeMessageOptimistic(currentSessionId, userMessage);
        const query = input;
        setInput('');

        await sendQuery(query, currentSessionId);
    };

    const insertText = (text: string) => {
        setInput(text);
        textareaRef.current?.focus();
    };

    const displayMessages = streamingMsg ? [...messages, streamingMsg] : messages;
    const hasMessages = displayMessages.length > 0;

    const handlePaletteSelect = (cmd: SlashCommand) => {
        setInput(cmd.name + ' ');
        textareaRef.current?.focus();
    };

    return (
        <div className="h-full flex flex-col bg-[#F5F7FA]">
            {/* Ctrl+K command palette */}
            <CommandPalette
                isOpen={isCommandPaletteOpen}
                onClose={() => setIsCommandPaletteOpen(false)}
                onSelect={handlePaletteSelect}
            />

            {/* Main content area */}
            {!hasMessages && !isLoadingSession ? (
                <SimpleWelcome onAction={insertText} />
            ) : (
                <SimpleMessageList
                    messages={displayMessages}
                    isTyping={isStreaming}
                    documents={documents}
                    sessionId={currentSessionId}
                    toolCallsByMsg={toolCallsByMsg}
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
                            placeholder={isStreaming ? 'Waiting for response\u2026' : 'Ask EAGLE about acquisitions, type / or press Ctrl+K for commands\u2026'}
                            disabled={isStreaming}
                            rows={1}
                            className={`flex-1 resize-none overflow-hidden px-4 py-3 bg-white border border-[#D8DEE6] rounded-xl focus:outline-none focus:ring-2 focus:ring-[#2196F3]/30 focus:border-[#2196F3] transition-all text-sm leading-relaxed ${isStreaming ? 'opacity-50' : ''}`}
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
                        EAGLE &middot; National Cancer Institute
                    </p>
                </div>
            </footer>
        </div>
    );
}
