'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import SimpleMessageList from './simple-message-list';
import SimpleWelcome from './simple-welcome';
import CommandPalette from './command-palette';
import ChatInput from './chat-input';
import ChatDragDrop from './chat-drag-drop';
import ActivityPanel from './activity-panel';
import { ChecklistPanel } from './checklist-panel';
import PackageSelectorModal from './package-selector-modal';
import { useAgentStream } from '@/hooks/use-agent-stream';
import { useSlashCommands } from '@/hooks/use-slash-commands';
import { useChatCallbacks } from '@/hooks/use-chat-callbacks';
import { useSession } from '@/contexts/session-context';
import { useAuth } from '@/contexts/auth-context';
import { useFeedback } from '@/contexts/feedback-context';
import { SlashCommand } from '@/lib/slash-commands';
import { ChatMessage, DocumentInfo } from '@/types/chat';
import { ToolStatus } from './tool-use-display';
import { UploadResult, assignToPackage } from '@/lib/document-api';
import { usePackageState } from '@/hooks/use-package-state';
import { useAnalytics } from '@/hooks/use-analytics';
import { ClientToolResult } from '@/lib/client-tools';

// -----------------------------------------------------------------------
// Types for per-message tool call tracking
// -----------------------------------------------------------------------

export interface TrackedToolCall {
    toolUseId: string;
    toolName: string;
    input: Record<string, unknown>;
    status: ToolStatus;
    isClientSide: boolean;
    result?: ClientToolResult | null;
}

export type ToolCallsByMessageId = Record<string, TrackedToolCall[]>;

export default function SimpleChatInterface() {
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [streamingMsg, setStreamingMsg] = useState<ChatMessage | null>(null);
    const streamingMsgRef = useRef<ChatMessage | null>(null);
    const [input, setInput] = useState('');
    const [isLoadingSession, setIsLoadingSession] = useState(true);
    const [documents, setDocuments] = useState<Record<string, DocumentInfo[]>>({});
    const [toolCallsByMsg, setToolCallsByMsg] = useState<ToolCallsByMessageId>({});
    const [agentStatus, setAgentStatus] = useState<string | null>(null);
    const [feedbackStatus, setFeedbackStatus] = useState<'idle' | 'sending' | 'done' | 'error'>('idle');
    const streamingMsgIdRef = useRef<string>(`stream-${Date.now()}`);
    const [isPanelOpen, setIsPanelOpen] = useState(true);
    const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false);
    const [uploadResult, setUploadResult] = useState<UploadResult | null>(null);
    const [isPackageSelectorOpen, setIsPackageSelectorOpen] = useState(false);

    const { currentSessionId, saveSession, loadSession, writeMessageOptimistic, renameSession } = useSession();
    const { getToken } = useAuth();
    const { setSnapshot } = useFeedback();
    const { track } = useAnalytics();

    const lastAssistantIdRef = useRef<string | null>(null);
    const titleGeneratedRef = useRef<Set<string>>(new Set());
    const firstUserMsgRef = useRef<string | null>(null);

    const { state: packageState, handleMetadata: handlePackageMetadata, reset: resetPackageState } = usePackageState();

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
            if (sessionData.messages.length > 0) {
                titleGeneratedRef.current.add(currentSessionId);
            }
        } else {
            setMessages([]);
            setDocuments({});
        }
        resetPackageState();
        firstUserMsgRef.current = null;
        setIsLoadingSession(false);
    }, [currentSessionId, loadSession, resetPackageState]);

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

    // Keep feedback context in sync
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

    // Chat callbacks hook
    const chatCallbacks = useChatCallbacks({
        currentSessionId,
        messages,
        streamingMsgIdRef,
        lastAssistantIdRef,
        streamingMsgRef,
        titleGeneratedRef,
        firstUserMsgRef,
        setMessages,
        setStreamingMsg,
        setDocuments,
        setToolCallsByMsg,
        setAgentStatus,
        handlePackageMetadata,
        renameSession,
    });

    // Agent stream
    const { sendQuery, isStreaming, error, logs, clearLogs, addUserInputLog } = useAgentStream({
        getToken,
        sessionId: currentSessionId ?? undefined,
        onMessage: chatCallbacks.onMessage,
        onComplete: chatCallbacks.onComplete,
        onError: chatCallbacks.onError,
        onDocumentGenerated: chatCallbacks.onDocumentGenerated,
        onToolUse: chatCallbacks.onToolUse,
        onToolResult: chatCallbacks.onToolResult,
        onAgentStatus: chatCallbacks.onAgentStatus,
        onStateUpdate: chatCallbacks.onStateUpdate,
    });

    const handleSend = async () => {
        if (!input.trim() || isStreaming) return;

        // Intercept /feedback command
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

        track('chat_send', { message_length: input.length });

        const userMessage: ChatMessage = {
            id: Date.now().toString(),
            role: 'user',
            content: input,
            timestamp: new Date(),
        };
        lastAssistantIdRef.current = null;
        setAgentStatus(null);
        if (messages.length === 0) {
            firstUserMsgRef.current = input;
        }
        streamingMsgIdRef.current = `stream-${Date.now()}`;
        setMessages((prev) => [...prev, userMessage]);
        addUserInputLog(input);
        writeMessageOptimistic(currentSessionId, userMessage);
        const query = input;
        setInput('');

        await sendQuery(query, currentSessionId, undefined, streamingMsgIdRef.current);
    };

    const insertText = (text: string) => {
        setInput(text);
    };

    // Upload handlers
    const handleUploadComplete = (result: UploadResult) => {
        setUploadResult(result);
        setIsPackageSelectorOpen(true);
    };

    const handleUploadError = (errorMsg: ChatMessage) => {
        setMessages((prev) => [...prev, errorMsg]);
    };

    const handlePackageAssignment = async (packageId: string | null, docType: string, title: string) => {
        if (!uploadResult) return;

        const msgId = `upload-${Date.now()}`;
        const token = await getToken();

        try {
            let docInfo: DocumentInfo;

            if (packageId) {
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

                const systemMsg: ChatMessage = {
                    id: msgId,
                    role: 'assistant',
                    content: `Document uploaded and assigned to package **${packageId}**.`,
                    timestamp: new Date(),
                };
                setMessages((prev) => [...prev, systemMsg]);
            } else {
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

                const systemMsg: ChatMessage = {
                    id: msgId,
                    role: 'assistant',
                    content: `Document uploaded to your workspace.`,
                    timestamp: new Date(),
                };
                setMessages((prev) => [...prev, systemMsg]);
            }

            setDocuments((prev) => ({
                ...prev,
                [msgId]: [...(prev[msgId] || []), docInfo],
            }));

            if (currentSessionId) {
                const { saveGeneratedDocument } = await import('@/lib/document-store');
                saveGeneratedDocument(docInfo, currentSessionId, title);
            }

            setUploadResult(null);
        } catch (err) {
            throw err;
        }
    };

    const handlePaletteSelect = (cmd: SlashCommand) => {
        setInput(cmd.name + ' ');
    };

    const displayMessages = streamingMsg ? [...messages, streamingMsg] : messages;
    const hasMessages = displayMessages.length > 0;

    return (
        <div className="h-full flex bg-[#F5F7FA]">
            {/* Left: main chat area */}
            <ChatDragDrop
                sessionId={currentSessionId}
                getToken={getToken}
                onUploadComplete={handleUploadComplete}
                onError={handleUploadError}
            >
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
                <ChatInput
                    input={input}
                    setInput={setInput}
                    isStreaming={isStreaming}
                    error={error}
                    feedbackStatus={feedbackStatus}
                    onSend={handleSend}
                    onInsertText={insertText}
                    onUploadComplete={handleUploadComplete}
                    sessionId={currentSessionId ?? undefined}
                    getToken={getToken}
                    isCommandPickerOpen={isCommandPickerOpen}
                    filteredCommands={filteredCommands}
                    selectedIndex={selectedIndex}
                    onSlashInputChange={handleSlashInputChange}
                    onSlashKeyDown={handleSlashKeyDown}
                    selectCommand={selectCommand}
                    closeCommandPicker={closeCommandPicker}
                />
            </ChatDragDrop>

            {/* Right: package checklist panel */}
            <ChecklistPanel state={packageState} />

            {/* Right: activity panel */}
            <ActivityPanel
                logs={logs}
                clearLogs={clearLogs}
                documents={documents}
                sessionId={currentSessionId ?? ''}
                packageState={packageState}
                isStreaming={isStreaming}
                isOpen={isPanelOpen}
                onToggle={() => setIsPanelOpen(v => !v)}
            />

            {/* Package selector modal */}
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
