'use client';

import { useState, useCallback } from 'react';
import { ChatMessage } from '@/types/chat';
import { UploadResult } from '@/lib/document-api';

const VALID_UPLOAD_TYPES = [
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.ms-excel',
    'text/plain',
    'text/markdown',
];

interface ChatDragDropProps {
    children: React.ReactNode;
    sessionId: string | null;
    getToken: () => Promise<string | null>;
    onUploadComplete: (result: UploadResult) => void;
    onError: (message: ChatMessage) => void;
}

export default function ChatDragDrop({
    children,
    sessionId,
    getToken,
    onUploadComplete,
    onError,
}: ChatDragDropProps) {
    const [isDragging, setIsDragging] = useState(false);

    const handleDragOver = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(true);
    }, []);

    const handleDragLeave = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        if (e.currentTarget === e.target) {
            setIsDragging(false);
        }
    }, []);

    const handleDrop = useCallback(async (e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(false);

        const files = e.dataTransfer.files;
        if (files.length === 0) return;

        const file = files[0];

        if (!VALID_UPLOAD_TYPES.includes(file.type)) {
            onError({
                id: `upload-error-${Date.now()}`,
                role: 'assistant',
                content: `Unsupported file type: ${file.type || 'unknown'}. Please upload PDF, Word, Excel, or text documents.`,
                timestamp: new Date(),
            });
            return;
        }

        try {
            const token = await getToken();
            const { uploadDocument } = await import('@/lib/document-api');
            const result = await uploadDocument(file, sessionId || undefined, undefined, token);
            onUploadComplete(result);
        } catch (err) {
            onError({
                id: `upload-error-${Date.now()}`,
                role: 'assistant',
                content: `Upload failed: ${err instanceof Error ? err.message : 'Unknown error'}`,
                timestamp: new Date(),
            });
        }
    }, [sessionId, getToken, onUploadComplete, onError]);

    return (
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
            {children}
        </div>
    );
}
