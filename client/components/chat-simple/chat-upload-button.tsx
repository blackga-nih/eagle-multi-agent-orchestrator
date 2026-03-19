'use client';

import { useRef, useState, useCallback } from 'react';
import { Paperclip, Loader2, CheckCircle, AlertCircle } from 'lucide-react';
import { uploadDocument, UploadResult } from '@/lib/document-api';

interface ChatUploadButtonProps {
    onUploadComplete: (result: UploadResult) => void;
    sessionId?: string;
    packageId?: string;
    disabled?: boolean;
    getToken?: () => Promise<string | null>;
}

type UploadStatus = 'idle' | 'uploading' | 'success' | 'error';

export default function ChatUploadButton({
    onUploadComplete,
    sessionId,
    packageId,
    disabled = false,
    getToken,
}: ChatUploadButtonProps) {
    const fileInputRef = useRef<HTMLInputElement>(null);
    const [status, setStatus] = useState<UploadStatus>('idle');
    const [error, setError] = useState<string | null>(null);
    const [progress, setProgress] = useState<string | null>(null);

    const handleFileSelect = useCallback(async (files: FileList | null) => {
        if (!files || files.length === 0) return;

        const file = files[0];
        setStatus('uploading');
        setError(null);
        setProgress(`Uploading ${file.name}...`);

        try {
            const token = getToken ? await getToken() : null;
            const result = await uploadDocument(file, sessionId, packageId, token);
            setStatus('success');
            setProgress(null);
            onUploadComplete(result);

            // Reset status after brief delay
            setTimeout(() => setStatus('idle'), 2000);
        } catch (err) {
            setStatus('error');
            setError(err instanceof Error ? err.message : 'Upload failed');
            setProgress(null);

            // Reset status after delay
            setTimeout(() => {
                setStatus('idle');
                setError(null);
            }, 4000);
        }

        // Clear file input
        if (fileInputRef.current) {
            fileInputRef.current.value = '';
        }
    }, [onUploadComplete, sessionId, packageId, getToken]);

    const handleClick = () => {
        if (status === 'uploading' || disabled) return;
        fileInputRef.current?.click();
    };

    const getButtonContent = () => {
        switch (status) {
            case 'uploading':
                return <Loader2 className="w-5 h-5 animate-spin text-blue-500" />;
            case 'success':
                return <CheckCircle className="w-5 h-5 text-green-500" />;
            case 'error':
                return <AlertCircle className="w-5 h-5 text-red-500" />;
            default:
                return <Paperclip className="w-5 h-5 text-gray-500 group-hover:text-[#003366]" />;
        }
    };

    const getTooltip = () => {
        if (status === 'uploading') return progress;
        if (status === 'error') return error;
        if (status === 'success') return 'Upload complete';
        return 'Upload document (max 25 MB)';
    };

    return (
        <div className="relative group">
            <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.doc,.docx,.txt,.md,.xlsx,.xls"
                onChange={(e) => handleFileSelect(e.target.files)}
                className="hidden"
            />
            <button
                type="button"
                onClick={handleClick}
                disabled={disabled || status === 'uploading'}
                className={`
                    p-3 rounded-xl transition-all
                    ${disabled || status === 'uploading'
                        ? 'opacity-50 cursor-not-allowed'
                        : 'hover:bg-gray-100 cursor-pointer'
                    }
                `}
                title={getTooltip() || undefined}
            >
                {getButtonContent()}
            </button>

            {/* Progress/error tooltip */}
            {(status === 'uploading' || status === 'error') && (
                <div className={`
                    absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-1.5
                    text-xs rounded-lg whitespace-nowrap shadow-lg
                    ${status === 'error' ? 'bg-red-500 text-white' : 'bg-gray-800 text-white'}
                `}>
                    {status === 'uploading' ? progress : error}
                    <div className={`
                        absolute top-full left-1/2 -translate-x-1/2 -mt-1
                        border-4 border-transparent
                        ${status === 'error' ? 'border-t-red-500' : 'border-t-gray-800'}
                    `} />
                </div>
            )}
        </div>
    );
}
