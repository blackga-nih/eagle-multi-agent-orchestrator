'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import SimpleMessageList from './simple-message-list';
import SimpleWelcome from './simple-welcome';
import SimpleQuickActions from './simple-quick-actions';
import SlashCommandPicker from '@/components/chat/slash-command-picker';
import CommandPalette from './command-palette';
import { useAgentStream, ToolUseEvent, ServerToolResult } from '@/hooks/use-agent-stream';
import { useSlashCommands } from '@/hooks/use-slash-commands';
import { useSession } from '@/contexts/session-context';
import { useAuth } from '@/contexts/auth-context';
import { useFeedback } from '@/contexts/feedback-context';
import { SlashCommand } from '@/lib/slash-commands';
import { ChatMessage, DocumentInfo } from '@/types/chat';
import { saveGeneratedDocument } from '@/lib/document-store';
import { ClientToolResult } from '@/lib/client-tools';
import { ToolStatus } from './tool-use-display';
import ActivityPanel from './activity-panel';
import ChatUploadButton from './chat-upload-button';
import PackageSelectorModal from './package-selector-modal';
import { UploadResult, assignToPackage } from '@/lib/document-api';

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
    // Agent status text shown during model thinking / tool execution
    const [agentStatus, setAgentStatus] = useState<string | null>(null);
    const [feedbackStatus, setFeedbackStatus] = useState<'idle' | 'sending' | 'done' | 'error'>('idle');
    // Stable ID for the current streaming message — reset on each sendQuery call.
    const streamingMsgIdRef = useRef<string>(`stream-${Date.now()}`);

    const { currentSessionId, saveSession, loadSession, writeMessageOptimistic, renameSession } = useSession();
    const { getToken } = useAuth();
    const { setSnapshot } = useFeedback();

    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const lastAssistantIdRef = useRef<string | null>(null);
    /** Track whether AI title has been generated for this session. */
    const titleGeneratedRef = useRef<Set<string>>(new Set());
    /** Store the first user message for title generation. */
    const firstUserMsgRef = useRef<string | null>(null);
    /** Ctrl+K command palette state. */
    const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false);
    /** Document upload state. */
    const [uploadResult, setUploadResult] = useState<UploadResult | null>(null);
    const [isPackageSelectorOpen, setIsPackageSelectorOpen] = useState(false);
    const [isDragging, setIsDragging] = useState(false);

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

    // Keep feedback context in sync so the modal can include conversation state
    useEffect(() => {
        setSnapshot({
            messages: messages.map((m) => ({
                role: m.role,
                content: m.content,
                id: m.id,
                timestamp: m.timestamp,
            })),
            lastMessageId: lastAssistantIdRef.current,
        });
    }, [messages, setSnapshot]);

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

    /** Right panel state. */
    const [isPanelOpen, setIsPanelOpen] = useState(true);

    // Agent stream
    const { sendQuery, isStreaming, error, logs, clearLogs, addUserInputLog } = useAgentStream({
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

        onComplete: (toolResults?: ServerToolResult[]) => {
            setAgentStatus(null);
            const completedMsg = streamingMsgRef.current;
            if (completedMsg) {
                lastAssistantIdRef.current = completedMsg.id;
                setMessages((prev) => [...prev, completedMsg]);

                // Migrate tool calls from the streaming ID to the committed message ID,
                // mark pending tools as "done", and merge any server-side tool results.
                const streamId = streamingMsgIdRef.current;
                setToolCallsByMsg((prev) => {
                    const calls = prev[streamId] ?? prev[completedMsg.id] ?? [];
                    if (calls.length === 0) return prev;

                    // Build a lookup: toolName → result (FIFO — first result matches first call)
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
                        // Try to match a server-side result by name
                        const pending = resultsByName.get(tc.toolName);
                        const matched = pending?.shift();
                        if (matched) {
                            return { ...tc, status: 'done' as const, result: matched.result as ClientToolResult };
                        }
                        // No result — just mark done
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

                // Migrate any document cards attached to the temporary stream id
                // onto the committed assistant message id.
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
            setAgentStatus(null);
            streamingMsgRef.current = null;
            setStreamingMsg(null);
        },

        onDocumentGenerated: (doc) => {
            // Attach to the active streaming message when tool_result arrives
            // before the first text chunk sets lastAssistantIdRef.
            const attachTo = lastAssistantIdRef.current ?? streamingMsgIdRef.current;
            setDocuments((prev) => {
                const existing = prev[attachTo] ?? [];
                const merged = dedupeDocuments([...existing, doc]);
                return {
                    ...prev,
                    [attachTo]: merged,
                };
            });

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
                // Client-side tool finished — update by exact toolUseId.
                // Server-side results are merged in onComplete via toolResults.
                const status: ToolStatus = toolEvent.result.success ? 'done' : 'error';
                upsertToolCall(parentId, toolEvent.toolUseId, {
                    status,
                    result: toolEvent.result,
                });
            }
        },

        onToolResult: (toolName, result) => {
            // Immediately update matching tool card to 'done' during streaming
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

        onAgentStatus: (status) => {
            setAgentStatus(status);
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
        // Log user input to agent logs panel
        addUserInputLog(input);
        // Optimistic write to IndexedDB — fire-and-forget, never blocks send
        writeMessageOptimistic(currentSessionId, userMessage);
        const query = input;
        setInput('');

        await sendQuery(query, currentSessionId, undefined, streamingMsgIdRef.current);
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

    // Upload handlers
    const handleUploadComplete = (result: UploadResult) => {
        setUploadResult(result);
        setIsPackageSelectorOpen(true);
    };

    const handlePackageAssignment = async (packageId: string | null, docType: string, title: string) => {
        if (!uploadResult) return;

        const msgId = `upload-${Date.now()}`;
        const token = await getToken();

        try {
            let docInfo: DocumentInfo;

            if (packageId) {
                // Assign to package - get back document details
                const result = await assignToPackage(uploadResult.upload_id, packageId, docType, title, token);
                docInfo = {
                    document_id: result.document_id,
                    package_id: result.package_id,
                    document_type: result.doc_type || docType,
                    doc_type: result.doc_type || docType,
                    title: result.title || title,
                    s3_key: result.s3_key || uploadResult.key,
                    mode: 'package',
                    status: result.status || 'draft',
                    version: result.version || 1,
                    content_type: uploadResult.content_type,
                    is_binary: uploadResult.content_type !== 'text/plain' && uploadResult.content_type !== 'text/markdown',
                    generated_at: new Date().toISOString(),
                };

                // Add system message
                const systemMsg: ChatMessage = {
                    id: msgId,
                    role: 'assistant',
                    content: `Document uploaded and assigned to package **${packageId}**.`,
                    timestamp: new Date(),
                };
                setMessages((prev) => [...prev, systemMsg]);
            } else {
                // Keep in workspace
                docInfo = {
                    document_type: docType,
                    doc_type: docType,
                    title: title,
                    s3_key: uploadResult.key,
                    mode: 'workspace',
                    status: 'draft',
                    version: 1,
                    content_type: uploadResult.content_type,
                    is_binary: uploadResult.content_type !== 'text/plain' && uploadResult.content_type !== 'text/markdown',
                    generated_at: new Date().toISOString(),
                };

                // Add system message
                const systemMsg: ChatMessage = {
                    id: msgId,
                    role: 'assistant',
                    content: `Document uploaded to your workspace.`,
                    timestamp: new Date(),
                };
                setMessages((prev) => [...prev, systemMsg]);
            }

            // Add document card to the message
            setDocuments((prev) => ({
                ...prev,
                [msgId]: [...(prev[msgId] || []), docInfo],
            }));

            // Persist to localStorage
            if (currentSessionId) {
                saveGeneratedDocument(docInfo, currentSessionId, title);
            }

            setUploadResult(null);
        } catch (err) {
            throw err;
        }
    };

    // Drag-drop handlers
    const handleDragOver = (e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(true);
    };

    const handleDragLeave = (e: React.DragEvent) => {
        e.preventDefault();
        // Only hide if leaving the main container
        if (e.currentTarget === e.target) {
            setIsDragging(false);
        }
    };

    const handleDrop = async (e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(false);

        const files = e.dataTransfer.files;
        if (files.length === 0) return;

        const file = files[0];
        // Validate file type
        const validTypes = [
            'application/pdf',
            'application/msword',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'application/vnd.ms-excel',
            'text/plain',
            'text/markdown',
        ];
        if (!validTypes.includes(file.type)) {
            // Show error in chat
            const errorMsg: ChatMessage = {
                id: `upload-error-${Date.now()}`,
                role: 'assistant',
                content: `Unsupported file type: ${file.type || 'unknown'}. Please upload PDF, Word, Excel, or text documents.`,
                timestamp: new Date(),
            };
            setMessages((prev) => [...prev, errorMsg]);
            return;
        }

        // Use the upload API
        try {
            const token = await getToken();
            const { uploadDocument } = await import('@/lib/document-api');
            const result = await uploadDocument(file, currentSessionId || undefined, undefined, token);
            handleUploadComplete(result);
        } catch (err) {
            const errorMsg: ChatMessage = {
                id: `upload-error-${Date.now()}`,
                role: 'assistant',
                content: `Upload failed: ${err instanceof Error ? err.message : 'Unknown error'}`,
                timestamp: new Date(),
            };
            setMessages((prev) => [...prev, errorMsg]);
        }
    };

    return (
        <div className="h-full flex bg-[#F5F7FA]">
            {/* Left: main chat area */}
            <div
                className="flex-1 flex flex-col min-w-0 relative"
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
            >
                {/* Drag overlay */}
                {isDragging && (
                    <div className="absolute inset-0 z-40 bg-blue-500/10 border-2 border-dashed border-blue-500 rounded-lg flex items-center justify-center pointer-events-none">
                        <div className="bg-white px-6 py-4 rounded-xl shadow-lg">
                            <p className="text-blue-600 font-medium">Drop document to upload</p>
                            <p className="text-sm text-gray-500">PDF, Word, or text files</p>
                        </div>
                    </div>
                )}

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
                        agentStatus={agentStatus}
                        pendingToolCalls={toolCallsByMsg[streamingMsgIdRef.current] ?? []}
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
                            <ChatUploadButton
                                onUploadComplete={handleUploadComplete}
                                sessionId={currentSessionId || undefined}
                                disabled={isStreaming}
                                getToken={getToken}
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

            {/* Right: activity panel */}
            <ActivityPanel
                logs={logs}
                clearLogs={clearLogs}
                documents={documents}
                sessionId={currentSessionId ?? ''}
                isStreaming={isStreaming}
                isOpen={isPanelOpen}
                onToggle={() => setIsPanelOpen(v => !v)}
            />

            {/* Package selector modal for uploaded documents */}
            <PackageSelectorModal
                isOpen={isPackageSelectorOpen}
                onClose={() => {
                    setIsPackageSelectorOpen(false);
                    setUploadResult(null);
                }}
                uploadResult={uploadResult}
                onAssign={handlePackageAssignment}
                getToken={getToken}
            />
        </div>
    );
}
