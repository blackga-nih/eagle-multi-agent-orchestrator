'use client';

import { useRef, useEffect, RefObject } from 'react';
import SlashCommandPicker from '@/components/chat/slash-command-picker';
import SimpleQuickActions from './simple-quick-actions';
import ChatUploadButton from './chat-upload-button';
import { SlashCommand } from '@/lib/slash-commands';
import { UploadResult } from '@/lib/document-api';

interface ChatInputProps {
    input: string;
    setInput: (value: string) => void;
    isStreaming: boolean;
    error: string | null;
    feedbackStatus: 'idle' | 'sending' | 'done' | 'error';
    onSend: () => void;
    onInsertText: (text: string) => void;
    onUploadComplete: (result: UploadResult) => void;
    sessionId: string | undefined;
    getToken: () => Promise<string | null>;
    // Slash command props
    isCommandPickerOpen: boolean;
    filteredCommands: SlashCommand[];
    selectedIndex: number;
    onSlashInputChange: (value: string, cursorPos: number) => void;
    onSlashKeyDown: (e: React.KeyboardEvent) => void;
    selectCommand: (cmd: SlashCommand) => void;
    closeCommandPicker: () => void;
}

export default function ChatInput({
    input,
    setInput,
    isStreaming,
    error,
    feedbackStatus,
    onSend,
    onInsertText,
    onUploadComplete,
    sessionId,
    getToken,
    isCommandPickerOpen,
    filteredCommands,
    selectedIndex,
    onSlashInputChange,
    onSlashKeyDown,
    selectCommand,
    closeCommandPicker,
}: ChatInputProps) {
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    // Auto-resize textarea
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

    const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (isCommandPickerOpen) {
            onSlashKeyDown(e);
            if (['ArrowUp', 'ArrowDown', 'Enter', 'Escape', 'Tab'].includes(e.key)) return;
        }
        if (e.key === 'Enter' && !e.shiftKey && !isStreaming && !isCommandPickerOpen) {
            e.preventDefault();
            onSend();
        }
    };

    return (
        <footer className="bg-white border-t border-[#D8DEE6] px-6 py-3 shrink-0">
            <div className="max-w-3xl mx-auto">
                {error && (
                    <div className="mb-2 px-3 py-1.5 bg-red-50 border border-red-200 rounded-lg text-red-700 text-xs">
                        {error}
                    </div>
                )}
                {feedbackStatus === 'sending' && (
                    <div className="mb-2 px-3 py-1.5 bg-blue-50 border border-blue-200 rounded-lg text-blue-700 text-xs">
                        Submitting feedback...
                    </div>
                )}
                {feedbackStatus === 'done' && (
                    <div className="mb-2 px-3 py-1.5 bg-green-50 border border-green-200 rounded-lg text-green-700 text-xs">
                        Feedback received. Thank you!
                    </div>
                )}
                {feedbackStatus === 'error' && (
                    <div className="mb-2 px-3 py-1.5 bg-red-50 border border-red-200 rounded-lg text-red-700 text-xs">
                        Failed to submit feedback. Please try again.
                    </div>
                )}

                {/* Quick action pills */}
                <SimpleQuickActions onAction={onInsertText} />

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
                            onSlashInputChange(e.target.value, e.target.selectionStart || 0);
                        }}
                        onKeyDown={handleKeyDown}
                        placeholder={isStreaming ? 'Waiting for response...' : 'Ask EAGLE about acquisitions, type / or press Ctrl+K for commands...'}
                        disabled={isStreaming}
                        rows={1}
                        className={`flex-1 resize-none overflow-hidden px-4 py-3 bg-white border border-[#D8DEE6] rounded-xl focus:outline-none focus:ring-2 focus:ring-[#2196F3]/30 focus:border-[#2196F3] transition-all text-sm leading-relaxed ${isStreaming ? 'opacity-50' : ''}`}
                        style={{ maxHeight: 160 }}
                    />
                    <ChatUploadButton
                        onUploadComplete={onUploadComplete}
                        sessionId={sessionId}
                        disabled={isStreaming}
                        getToken={getToken}
                    />
                    <button
                        onClick={onSend}
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
    );
}
