'use client';

import { useState, useRef, useCallback } from 'react';
import { Upload, FileText, X, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';

interface UploadedDocument {
    id: string;
    name: string;
    size: number;
    type: string;
    uploadedAt: Date;
    status: 'uploading' | 'success' | 'error';
    error?: string;
}

interface DocumentUploadProps {
    onUpload: (file: File) => Promise<{ success: boolean; error?: string }>;
    onRemove?: (documentId: string) => void;
    maxSizeMB?: number;
    acceptedTypes?: string[];
    className?: string;
}

const DEFAULT_ACCEPTED_TYPES = [
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'text/plain',
    'image/png',
    'image/jpeg',
    'image/gif',
];

const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

const getFileIcon = (type: string) => {
    if (type.includes('pdf')) return '📄';
    if (type.includes('word') || type.includes('document')) return '📝';
    if (type.includes('image')) return '🖼️';
    if (type.includes('text')) return '📃';
    return '📎';
};

export default function DocumentUpload({
    onUpload,
    onRemove,
    maxSizeMB = 10,
    acceptedTypes = DEFAULT_ACCEPTED_TYPES,
    className = '',
}: DocumentUploadProps) {
    const [documents, setDocuments] = useState<UploadedDocument[]>([]);
    const [isDragging, setIsDragging] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const generateId = () => `doc-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

    const validateFile = (file: File): { valid: boolean; error?: string } => {
        // Check file size
        if (file.size > maxSizeMB * 1024 * 1024) {
            return { valid: false, error: `File size exceeds ${maxSizeMB}MB limit` };
        }

        // Check file type
        if (!acceptedTypes.includes(file.type)) {
            return { valid: false, error: 'File type not supported' };
        }

        return { valid: true };
    };

    const handleFiles = useCallback(async (files: FileList | null) => {
        if (!files) return;

        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            const validation = validateFile(file);
            const docId = generateId();

            // Add to list with uploading status
            const newDoc: UploadedDocument = {
                id: docId,
                name: file.name,
                size: file.size,
                type: file.type,
                uploadedAt: new Date(),
                status: validation.valid ? 'uploading' : 'error',
                error: validation.error,
            };

            setDocuments((prev) => [...prev, newDoc]);

            // Upload if valid
            if (validation.valid) {
                try {
                    const result = await onUpload(file);
                    setDocuments((prev) =>
                        prev.map((d) =>
                            d.id === docId
                                ? {
                                    ...d,
                                    status: result.success ? 'success' : 'error',
                                    error: result.error,
                                }
                                : d
                        )
                    );
                } catch (error) {
                    setDocuments((prev) =>
                        prev.map((d) =>
                            d.id === docId
                                ? { ...d, status: 'error', error: 'Upload failed' }
                                : d
                        )
                    );
                }
            }
        }
    }, [onUpload, maxSizeMB, acceptedTypes]);

    const handleDragOver = (e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(true);
    };

    const handleDragLeave = (e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(false);
    };

    const handleDrop = (e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(false);
        handleFiles(e.dataTransfer.files);
    };

    const handleRemove = (docId: string) => {
        setDocuments((prev) => prev.filter((d) => d.id !== docId));
        onRemove?.(docId);
    };

    return (
        <div className={className}>
            {/* Dropzone */}
            <div
                onClick={() => fileInputRef.current?.click()}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                className={`relative border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-all ${
                    isDragging
                        ? 'border-blue-500 bg-blue-50'
                        : 'border-gray-200 hover:border-blue-300 hover:bg-gray-50'
                }`}
            >
                <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    accept={acceptedTypes.join(',')}
                    onChange={(e) => handleFiles(e.target.files)}
                    className="hidden"
                />

                <Upload className={`w-8 h-8 mx-auto mb-2 ${isDragging ? 'text-blue-500' : 'text-gray-400'}`} />
                <p className="text-sm text-gray-600 mb-1">
                    <span className="font-semibold text-blue-600">Click to upload</span> or drag and drop
                </p>
                <p className="text-xs text-gray-400">
                    PDF, DOC, DOCX, TXT, images (max {maxSizeMB}MB)
                </p>
            </div>

            {/* Uploaded Files List */}
            {documents.length > 0 && (
                <div className="mt-4 space-y-2">
                    <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
                        Uploaded Documents ({documents.length})
                    </p>

                    {documents.map((doc) => (
                        <div
                            key={doc.id}
                            className={`flex items-center gap-3 p-3 rounded-lg border ${
                                doc.status === 'error'
                                    ? 'bg-red-50 border-red-200'
                                    : doc.status === 'success'
                                    ? 'bg-green-50 border-green-200'
                                    : 'bg-gray-50 border-gray-200'
                            }`}
                        >
                            <span className="text-xl">{getFileIcon(doc.type)}</span>

                            <div className="flex-1 min-w-0">
                                <p className="text-sm font-medium text-gray-900 truncate">
                                    {doc.name}
                                </p>
                                <p className="text-xs text-gray-500">
                                    {formatFileSize(doc.size)}
                                    {doc.error && <span className="text-red-500 ml-2">{doc.error}</span>}
                                </p>
                            </div>

                            <div className="flex items-center gap-2">
                                {doc.status === 'uploading' && (
                                    <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />
                                )}
                                {doc.status === 'success' && (
                                    <CheckCircle className="w-4 h-4 text-green-500" />
                                )}
                                {doc.status === 'error' && (
                                    <AlertCircle className="w-4 h-4 text-red-500" />
                                )}

                                <button
                                    onClick={() => handleRemove(doc.id)}
                                    className="p-1 text-gray-400 hover:text-red-500 transition-colors"
                                >
                                    <X className="w-4 h-4" />
                                </button>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
