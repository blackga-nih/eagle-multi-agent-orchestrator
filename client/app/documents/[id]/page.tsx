'use client';

import { useState, useEffect, useRef, use, useCallback } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
    ArrowLeft,
    Save,
    FileText,
    Send,
    Bot,
    User,
    Sparkles,
    Download,
    ChevronDown,
    Eye,
    Edit3,
    RefreshCw,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import TopNav from '@/components/layout/top-nav';
import MarkdownRenderer from '@/components/ui/markdown-renderer';
import { useAgentStream } from '@/hooks/use-agent-stream';
import { useAuth } from '@/contexts/auth-context';
import { useSession } from '@/contexts/session-context';
import { ChatMessage, DocumentInfo } from '@/types/chat';
import {
    hasPlaceholders,
    hydrateTemplate,
    buildHydrationContext,
    extractBackgroundFromMessages,
} from '@/lib/template-hydration';
import { getGeneratedDocument } from '@/lib/document-store';
import { DOCUMENT_TYPE_LABELS } from '@/types/schema';

interface PageProps {
    params: Promise<{ id: string }>;
}

// Maps filename prefix → local template file. Sorted longest-first at lookup
// so "acquisition_plan_*.md" matches before a hypothetical shorter prefix.
const TEMPLATE_MAP: Record<string, string> = {
    acquisition_plan: 'acquisition-plan-template.md',
    market_research: 'market-research-template.md',
    justification: 'justification-template.md',
    igce: 'igce-template.md',
    sow: 'sow-template.md',
};

const TEMPLATE_PREFIXES = Object.keys(TEMPLATE_MAP).sort((a, b) => b.length - a.length);

// Alias for local usage (backward compat with existing references in this file)
const DOC_TYPE_LABELS = DOCUMENT_TYPE_LABELS as Record<string, string>;
const MAX_DOC_CONTEXT_CHARS = 2000;
const MAX_SESSION_CONTEXT_CHARS = 1500;
const EDIT_INTENT_RE = /\b(edit|update|revise|modify|change|clear|fill|rewrite|amend|replace|adjust|section)\b/i;

function truncateWithEllipsis(text: string, maxChars: number): string {
    if (text.length <= maxChars) return text;
    return `${text.slice(0, maxChars - 3)}...`;
}

function sanitizeContextText(text: string): string {
    return text
        .replace(/Authorization:\s*[^\n]*/gi, '[REDACTED]')
        .replace(/Bearer\s+[A-Za-z0-9._-]+/gi, '[REDACTED]')
        .replace(/AWS_(ACCESS_KEY_ID|SECRET_ACCESS_KEY|SESSION_TOKEN)\s*[:=]?\s*[^\s\n]+/gi, '[REDACTED]');
}

async function extractResponseError(response: Response): Promise<string> {
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
        try {
            const payload = await response.json() as { detail?: string; error?: string; message?: string };
            return payload.detail || payload.error || payload.message || `Request failed (${response.status})`;
        } catch {
            return `Request failed (${response.status})`;
        }
    }
    try {
        const text = await response.text();
        return text || `Request failed (${response.status})`;
    } catch {
        return `Request failed (${response.status})`;
    }
}

export default function DocumentViewerPage({ params }: PageProps) {
    const { id } = use(params);
    const router = useRouter();
    const searchParams = useSearchParams();
    const sessionId = searchParams.get('session') || '';

    // Document state
    const [documentContent, setDocumentContent] = useState('');
    const [documentTitle, setDocumentTitle] = useState('');
    const [documentType, setDocumentType] = useState('');
    const [packageId, setPackageId] = useState<string | undefined>(undefined);
    const [editContent, setEditContent] = useState('');
    const [isEditing, setIsEditing] = useState(false);
    const [isLoading, setIsLoading] = useState(true);
    const [docUpdated, setDocUpdated] = useState(false);
    const [unfilledCount, setUnfilledCount] = useState(0);
    const [showHydrationBanner, setShowHydrationBanner] = useState(false);
    const autoPromptSentRef = useRef(false);

    // Chat state
    const [chatMessages, setChatMessages] = useState<ChatMessage[]>([
        {
            id: 'welcome',
            role: 'assistant',
            content: 'I can help you review and edit this document. Ask me to add sections, modify content, or explain any part of the document.',
            timestamp: new Date(),
        },
    ]);
    const [chatInput, setChatInput] = useState('');
    const [streamingAssistantMsg, setStreamingAssistantMsg] = useState<ChatMessage | null>(null);
    const streamingAssistantMsgRef = useRef<ChatMessage | null>(null);
    const generatedDocFetchSeqRef = useRef(0);
    const chatEndRef = useRef<HTMLDivElement>(null);
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    // Download state
    const [showDownloadMenu, setShowDownloadMenu] = useState(false);
    const [isExporting, setIsExporting] = useState(false);
    const [exportError, setExportError] = useState<string | null>(null);

    // Save state
    const [isSaving, setIsSaving] = useState(false);
    const [saveError, setSaveError] = useState<string | null>(null);
    const [s3Key, setS3Key] = useState<string | null>(null);

    const { getToken } = useAuth();
    const { loadSession } = useSession();

    const applyDocumentUpdate = useCallback((doc: Partial<DocumentInfo> & { content: string }) => {
        if (doc.package_id) {
            setPackageId(doc.package_id);
        }
        if (doc.title) {
            setDocumentTitle(doc.title);
        }
        if (doc.document_type) {
            setDocumentType(doc.document_type);
        }
        // Track the S3 key for save operations
        const docS3Key = doc.s3_key || doc.document_id;
        if (docS3Key) {
            setS3Key(docS3Key);
        }

        setDocumentContent(doc.content);
        setEditContent(doc.content);

        const targetRawId = doc.s3_key || doc.document_id || decodeURIComponent(id);
        const targetId = encodeURIComponent(targetRawId);
        const persistedDoc: DocumentInfo = {
            document_id: doc.document_id || targetRawId,
            package_id: doc.package_id,
            document_type: doc.document_type || documentType || 'document',
            title: doc.title || documentTitle || 'Document',
            content: doc.content,
            s3_key: doc.s3_key,
            status: doc.status,
            version: doc.version,
            generated_at: doc.generated_at,
        };

        try {
            // Update both current-route cache and resolved-target cache.
            sessionStorage.setItem(`doc-content-${id}`, JSON.stringify(persistedDoc));
            sessionStorage.setItem(`doc-content-${targetId}`, JSON.stringify(persistedDoc));
        } catch {
            // sessionStorage unavailable
        }

        setDocUpdated(true);
        setTimeout(() => setDocUpdated(false), 2000);
    }, [documentTitle, documentType, id]);

    const refreshGeneratedDocumentFromS3 = useCallback(async (doc: DocumentInfo) => {
        const rawId = doc.s3_key || doc.document_id;
        if (!rawId) return;

        const fetchSeq = ++generatedDocFetchSeqRef.current;
        try {
            const token = await getToken();
            const res = await fetch(`/api/documents/${encodeURIComponent(rawId)}?content=true`, {
                headers: token ? { Authorization: `Bearer ${token}` } : {},
            });
            if (!res.ok) return;

            const data = await res.json();
            if (fetchSeq !== generatedDocFetchSeqRef.current) return;

            if (typeof data.content === 'string' && data.content.length > 0) {
                applyDocumentUpdate({
                    ...doc,
                    title: data.title || doc.title,
                    document_type: data.document_type || doc.document_type,
                    package_id: data.package_id || doc.package_id,
                    document_id: data.document_id || doc.document_id || rawId,
                    s3_key: data.s3_key || doc.s3_key || rawId,
                    content: data.content,
                });
            }
        } catch {
            // Best-effort refresh: keep existing content if fetch fails.
        }
    }, [applyDocumentUpdate, getToken]);

    // Load document from sessionStorage or API
    useEffect(() => {
        const decodedId = decodeURIComponent(id);

        // Try sessionStorage first (instant load from chat navigation)
        // Double-lookup: new keys use plain encodeURIComponent, old keys had dots as %2E
        try {
            const stored = sessionStorage.getItem(`doc-content-${id}`)
                || sessionStorage.getItem(`doc-content-${encodeURIComponent(decodedId).replace(/\./g, '%2E')}`);
            if (stored) {
                const doc: DocumentInfo = JSON.parse(stored);
                if (doc.content) {
                    setDocumentTitle(doc.title);
                    setDocumentType(doc.document_type);
                    setPackageId(doc.package_id);
                    setS3Key(doc.s3_key || doc.document_id || null);
                    setDocumentContent(doc.content);
                    setEditContent(doc.content);
                    setIsLoading(false);
                    return;
                }
                // Has metadata but no content — keep metadata, fall through to fetch
                setDocumentTitle(doc.title);
                setDocumentType(doc.document_type);
                setPackageId(doc.package_id);
                setS3Key(doc.s3_key || doc.document_id || null);
            }
        } catch {
            // sessionStorage unavailable or parse error
        }

        // Try localStorage (handles navigation from Documents page)
        const stored2 = getGeneratedDocument(id);
        if (stored2?.content) {
            setDocumentTitle(stored2.title);
            setDocumentType(stored2.document_type);
            setPackageId(stored2.package_id);
            setS3Key(stored2.s3_key || stored2.id || null);
            setDocumentContent(stored2.content);
            setEditContent(stored2.content);
            setIsLoading(false);
            return;
        }

        // Fallback: try fetching from API, then from local templates
        async function fetchDocument() {
            // Try backend API first
            try {
                const token = await getToken();
                const res = await fetch(`/api/documents/${encodeURIComponent(decodedId)}?content=true`, {
                    headers: token ? { Authorization: `Bearer ${token}` } : {},
                });
                if (res.ok) {
                    const data = await res.json();
                    setDocumentTitle(data.title || 'Untitled Document');
                    setDocumentType(data.document_type || '');
                    setPackageId(data.package_id || undefined);
                    setS3Key(data.s3_key || data.key || data.document_id || null);
                    setDocumentContent(data.content || '');
                    setEditContent(data.content || '');
                    setIsLoading(false);
                    return;
                }
            } catch {
                // Backend unavailable — try template fallback
            }

            // Try loading from local template files (no S3 required)
            // Match by exact name first, then by longest prefix (e.g. sow_20260212.md → sow)
            let templateFile: string | null = null;
            let typeFromFile = '';

            if (decodedId.endsWith('-template.md')) {
                templateFile = decodedId;
                typeFromFile = decodedId.replace('-template.md', '').replace(/-/g, '_');
            } else {
                for (const prefix of TEMPLATE_PREFIXES) {
                    if (decodedId.startsWith(prefix + '_') || decodedId === prefix) {
                        templateFile = TEMPLATE_MAP[prefix];
                        typeFromFile = prefix;
                        break;
                    }
                }
            }

            if (templateFile) {
                try {
                    const res = await fetch(`/templates/${templateFile}`);
                    if (res.ok) {
                        const content = await res.text();
                        setDocumentTitle(DOC_TYPE_LABELS[typeFromFile] || 'Document');
                        setDocumentType(typeFromFile);
                        setDocumentContent(content);
                        setEditContent(content);
                        setIsLoading(false);
                        return;
                    }
                } catch {
                    // Template not found
                }
            }

            setDocumentTitle('Document');
            setDocumentContent('*Unable to load document content. The document may have been created in this session — try going back and clicking "Open Document" again.*');
            setIsLoading(false);
        }

        fetchDocument();
    }, [id, getToken]);

    // Layer 1: Immediate hydration from session context
    useEffect(() => {
        if (isLoading || !documentContent || !sessionId || !documentType) return;
        if (!hasPlaceholders(documentContent)) return;

        const sessionData = loadSession(sessionId);
        if (!sessionData) return;

        const context = buildHydrationContext(
            sessionData.acquisitionData || {},
            sessionData.messages || [],
        );
        const result = hydrateTemplate(documentContent, documentType, context);
        setDocumentContent(result.content);
        setEditContent(result.content);
        setUnfilledCount(result.unfilledCount);
        if (result.unfilledCount > 0) {
            setShowHydrationBanner(true);
        }
    // Run once after initial content loads
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isLoading]);

    // Agent stream for the document chat
    const { sendQuery, isStreaming } = useAgentStream({
        getToken,
        onMessage: (msg) => {
            const next: ChatMessage = {
                id: msg.id,
                role: 'assistant',
                content: msg.content,
                timestamp: msg.timestamp,
                reasoning: msg.reasoning,
                agent_id: msg.agent_id,
                agent_name: msg.agent_name,
            };
            streamingAssistantMsgRef.current = next;
            setStreamingAssistantMsg(next);
        },
        onComplete: () => {
            const completed = streamingAssistantMsgRef.current;
            if (completed) {
                setChatMessages((prev) => [...prev, completed]);
            }
            streamingAssistantMsgRef.current = null;
            setStreamingAssistantMsg(null);
        },
        onError: () => {
            streamingAssistantMsgRef.current = null;
            setStreamingAssistantMsg(null);
        },
        onDocumentGenerated: (doc) => {
            // LLM regenerated/updated the document.
            // Some streams include full content directly; others only include key metadata.
            if (doc.content && doc.content.length > 0) {
                applyDocumentUpdate(doc as DocumentInfo & { content: string });
                return;
            }
            void refreshGeneratedDocumentFromS3(doc);
        },
    });

    // Layer 2: LLM auto-fill for remaining unfilled sections
    useEffect(() => {
        if (
            unfilledCount <= 0 ||
            isLoading ||
            isStreaming ||
            autoPromptSentRef.current ||
            !showHydrationBanner ||
            !sessionId
        ) return;

        autoPromptSentRef.current = true;

        const sessionData = loadSession(sessionId);
        const contextSnippet = sessionData
            ? extractBackgroundFromMessages(
                  (sessionData.messages || [])
                      .filter((m) => m.role === 'user')
                      .slice(0, 5)
                      .map((m) => ({ role: m.role as 'user' | 'assistant', content: typeof m.content === 'string' ? m.content.slice(0, 400) : '' })),
              ).slice(0, 2000)
            : '';

        const docSnippet = documentContent.slice(0, 3000);

        const autoPrompt = `Please fill in all sections marked with "[... - To Be Filled]" in this document using the conversation context below. Generate the complete updated document using the create_document tool.

Conversation context:
${contextSnippet}

Current document (first 3000 chars):
${docSnippet}`;

        // Send as a chat message
        const userMsg: ChatMessage = {
            id: `auto-${Date.now()}`,
            role: 'user',
            content: 'Automatically filling in remaining document sections from conversation context...',
            timestamp: new Date(),
        };
        setChatMessages((prev) => [...prev, userMsg]);
        sendQuery(autoPrompt, sessionId, packageId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [unfilledCount, isLoading, isStreaming, showHydrationBanner, packageId]);

    // Scroll chat to bottom
    useEffect(() => {
        chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [chatMessages, streamingAssistantMsg, isStreaming]);

    // Auto-resize chat textarea
    const adjustTextareaHeight = useCallback(() => {
        const el = textareaRef.current;
        if (el) {
            el.style.height = 'auto';
            el.style.height = Math.min(el.scrollHeight, 120) + 'px';
        }
    }, []);

    useEffect(() => {
        adjustTextareaHeight();
    }, [chatInput, adjustTextareaHeight]);

    const buildDocumentAssistantPrompt = useCallback((userRequest: string): string => {
        const sanitizedDoc = sanitizeContextText(documentContent || '');
        // For edit operations, include full document content so backend edits
        // apply to the complete document, not a head/tail excerpt.
        const includeFullDocument = EDIT_INTENT_RE.test(userRequest);
        const docExcerpt = includeFullDocument
            ? sanitizedDoc
            : (sanitizedDoc.length > MAX_DOC_CONTEXT_CHARS
                ? `${sanitizedDoc.slice(0, 1000)}\n...\n${sanitizedDoc.slice(-1000)}`
                : sanitizedDoc);

        const sessionData = sessionId ? loadSession(sessionId) : null;
        const sessionMessages = (sessionData?.messages || [])
            .filter((m) => m.role === 'user')
            .slice(0, 5)
            .map((m) => ({
                role: 'user' as const,
                content: sanitizeContextText(typeof m.content === 'string' ? m.content : ''),
            }));

        const background = sessionMessages.length
            ? extractBackgroundFromMessages(sessionMessages)
            : '';

        const boundedDoc = includeFullDocument
            ? docExcerpt
            : truncateWithEllipsis(docExcerpt, MAX_DOC_CONTEXT_CHARS);
        const boundedSession = truncateWithEllipsis(background, MAX_SESSION_CONTEXT_CHARS);

        const s3KeyInfo = s3Key
            ? `[DOCUMENT KEY]\n${s3Key}\nTo update this document in place, use create_document with update_existing_key="${s3Key}" and provide the full updated content in data.content.`
            : '[DOCUMENT KEY]\nNot available - document must be saved to S3 first before updates can be applied.';

        return [
            'You are assisting with edits to an acquisition document in EAGLE.',
            '[DOCUMENT CONTEXT]',
            `Title: ${documentTitle || 'Untitled Document'}`,
            `Type: ${documentType || 'unknown'}`,
            boundedDoc ? `Current Content Excerpt:\n${boundedDoc}` : 'Current Content Excerpt: [empty]',
            s3KeyInfo,
            '[ORIGIN SESSION CONTEXT]',
            boundedSession || 'No origin session context was found for this document.',
            '[USER REQUEST]',
            userRequest,
            'Instruction: If the user requests substantive edits or section completion, use create_document with update_existing_key to update the document in place.',
        ].join('\n\n');
    }, [documentContent, documentTitle, documentType, loadSession, sessionId, s3Key]);

    const handleSendMessage = async () => {
        if (!chatInput.trim() || isStreaming) return;

        const userMsg: ChatMessage = {
            id: Date.now().toString(),
            role: 'user',
            content: chatInput,
            timestamp: new Date(),
        };
        setChatMessages((prev) => [...prev, userMsg]);
        const query = buildDocumentAssistantPrompt(chatInput);
        setChatInput('');

        await sendQuery(query, sessionId || undefined, packageId);
    };

    const displayChatMessages = streamingAssistantMsg
        ? [...chatMessages, streamingAssistantMsg]
        : chatMessages;

    const handleToggleEdit = () => {
        if (isEditing) {
            // Switching from edit to preview — save edits to local state
            setDocumentContent(editContent);
        } else {
            setEditContent(documentContent);
        }
        setIsEditing(!isEditing);
    };

    // Save handler - persists to S3
    const handleSave = async () => {
        if (!s3Key) {
            setSaveError('No document key available - cannot save');
            return;
        }
        setIsSaving(true);
        setSaveError(null);
        try {
            const token = await getToken();
            const res = await fetch(`/api/documents/${encodeURIComponent(s3Key)}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    ...(token ? { Authorization: `Bearer ${token}` } : {}),
                },
                body: JSON.stringify({ content: editContent, change_source: 'user_edit' }),
            });
            if (!res.ok) {
                throw new Error(await extractResponseError(res));
            }

            // Update local state with saved content
            setDocumentContent(editContent);
            setDocUpdated(true);
            setTimeout(() => setDocUpdated(false), 2000);
        } catch (err) {
            setSaveError(err instanceof Error ? err.message : 'Save failed');
        } finally {
            setIsSaving(false);
        }
    };

    // Download handler
    const handleDownload = async (format: 'docx' | 'pdf') => {
        setShowDownloadMenu(false);
        setIsExporting(true);
        setExportError(null);

        try {
            const token = await getToken();
            const headers: Record<string, string> = {
                'Content-Type': 'application/json',
            };
            if (token) headers['Authorization'] = `Bearer ${token}`;

            const res = await fetch('/api/documents', {
                method: 'POST',
                headers,
                body: JSON.stringify({
                    content: documentContent,
                    title: documentTitle,
                    format,
                }),
            });

            if (!res.ok) {
                const detail = await extractResponseError(res);
                throw new Error(`Export failed (${res.status}): ${detail}`);
            }

            const blob = await res.blob();
            if (blob.size === 0) {
                throw new Error('Export returned an empty file.');
            }

            const sig = new Uint8Array(await blob.slice(0, 4).arrayBuffer());
            const isDocx = sig.length >= 4 && sig[0] === 0x50 && sig[1] === 0x4b && sig[2] === 0x03 && sig[3] === 0x04;
            const isPdf = sig.length >= 4 && sig[0] === 0x25 && sig[1] === 0x50 && sig[2] === 0x44 && sig[3] === 0x46;
            if ((format === 'docx' && !isDocx) || (format === 'pdf' && !isPdf)) {
                throw new Error(`Export returned invalid ${format.toUpperCase()} file content.`);
            }

            const url = URL.createObjectURL(blob);
            const a = window.document.createElement('a');
            a.href = url;
            const ext = format === 'docx' ? 'docx' : 'pdf';
            a.download = `${documentTitle.replace(/[^a-z0-9]/gi, '_')}.${ext}`;
            window.document.body.appendChild(a);
            a.click();
            window.document.body.removeChild(a);
            URL.revokeObjectURL(url);
        } catch (err) {
            setExportError(err instanceof Error ? err.message : 'Export failed');
        } finally {
            setIsExporting(false);
        }
    };

    if (isLoading) {
        return (
            <div className="flex flex-col h-screen bg-gray-50">
                <TopNav />
                <div className="flex-1 flex items-center justify-center">
                    <div className="flex items-center gap-3 text-gray-500">
                        <RefreshCw className="w-5 h-5 animate-spin" />
                        <span>Loading document...</span>
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div className="flex flex-col h-screen bg-gray-50">
            <TopNav />

            <div className="flex-1 flex flex-col overflow-hidden">
                {/* Header */}
                <header className="bg-white border-b border-gray-200 px-6 py-3">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-4">
                            <button
                                onClick={() => router.back()}
                                className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
                                title="Back to chat"
                            >
                                <ArrowLeft className="w-5 h-5" />
                            </button>
                            <div>
                                <div className="flex items-center gap-2">
                                    <h1 className="text-lg font-semibold text-gray-900">{documentTitle}</h1>
                                    {docUpdated && (
                                        <span className="text-xs font-medium text-green-600 bg-green-50 px-2 py-0.5 rounded-full animate-pulse">
                                            Updated
                                        </span>
                                    )}
                                </div>
                                {documentType && (
                                    <span className="text-xs text-gray-500">
                                        {DOC_TYPE_LABELS[documentType] || documentType}
                                    </span>
                                )}
                            </div>
                        </div>
                        <div className="flex items-center gap-2">
                            {/* Export error */}
                            {exportError && (
                                <span className="text-xs text-red-600 mr-2">{exportError}</span>
                            )}

                            {/* Download dropdown */}
                            <div className="relative">
                                <button
                                    onClick={() => setShowDownloadMenu(!showDownloadMenu)}
                                    disabled={isExporting}
                                    className="flex items-center gap-2 px-4 py-2 border border-gray-200 bg-white text-gray-700 rounded-xl text-sm font-medium hover:bg-gray-50 transition-colors disabled:opacity-50"
                                >
                                    {isExporting ? (
                                        <RefreshCw className="w-4 h-4 animate-spin" />
                                    ) : (
                                        <Download className="w-4 h-4" />
                                    )}
                                    Download
                                    <ChevronDown className="w-3 h-3" />
                                </button>
                                {showDownloadMenu && (
                                    <div className="absolute right-0 top-full mt-1 w-52 bg-white border border-gray-200 rounded-xl shadow-lg z-10 overflow-hidden">
                                        <button
                                            onClick={() => handleDownload('docx')}
                                            className="w-full px-4 py-2.5 text-sm text-left hover:bg-gray-50 flex items-center gap-2"
                                        >
                                            <FileText className="w-4 h-4 text-blue-600" />
                                            Download as Word (.docx)
                                        </button>
                                        <button
                                            onClick={() => handleDownload('pdf')}
                                            className="w-full px-4 py-2.5 text-sm text-left hover:bg-gray-50 flex items-center gap-2 border-t border-gray-100"
                                        >
                                            <FileText className="w-4 h-4 text-red-600" />
                                            Download as PDF (.pdf)
                                        </button>
                                    </div>
                                )}
                            </div>

                            {/* Edit / Preview toggle */}
                            <button
                                onClick={handleToggleEdit}
                                className="flex items-center gap-2 px-4 py-2 bg-[#003366] text-white rounded-xl text-sm font-medium hover:bg-[#004488] transition-colors"
                            >
                                {isEditing ? (
                                    <>
                                        <Eye className="w-4 h-4" />
                                        Preview
                                    </>
                                ) : (
                                    <>
                                        <Edit3 className="w-4 h-4" />
                                        Edit
                                    </>
                                )}
                            </button>

                            {/* Save button (visible when editing) */}
                            {isEditing && (
                                <button
                                    onClick={handleSave}
                                    disabled={isSaving || editContent === documentContent || !s3Key}
                                    className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-xl text-sm font-medium hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                                    title={!s3Key ? 'Document must be saved to S3 first' : editContent === documentContent ? 'No changes to save' : 'Save to S3'}
                                >
                                    {isSaving ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                                    Save
                                </button>
                            )}

                            {/* Save error */}
                            {saveError && (
                                <span className="text-xs text-red-600 ml-2">{saveError}</span>
                            )}
                        </div>
                    </div>
                </header>

                {/* Hydration banner */}
                {showHydrationBanner && unfilledCount > 0 && (
                    <div className="bg-amber-50 border-b border-amber-200 px-6 py-2 flex items-center justify-between">
                        <p className="text-sm text-amber-800">
                            This document has <strong>{unfilledCount}</strong> section{unfilledCount !== 1 ? 's' : ''} to be filled.
                            The AI assistant will attempt to complete them.
                        </p>
                        <button
                            onClick={() => setShowHydrationBanner(false)}
                            className="text-xs text-amber-600 hover:text-amber-800 underline ml-4 whitespace-nowrap"
                        >
                            Dismiss
                        </button>
                    </div>
                )}

                {/* Main Content Area — 65/35 split */}
                <div className="flex-1 flex overflow-hidden">
                    {/* Left Panel — Document */}
                    <div
                        className={`flex-1 flex flex-col border-r bg-white overflow-y-auto transition-colors duration-500 ${
                            docUpdated ? 'border-r-green-300' : 'border-r-gray-200'
                        }`}
                        style={{ width: '65%' }}
                    >
                        <div className="flex-1 overflow-y-auto p-8">
                            <div className="max-w-3xl mx-auto">
                                {isEditing ? (
                                    <textarea
                                        value={editContent}
                                        onChange={(e) => setEditContent(e.target.value)}
                                        className="w-full min-h-[600px] p-4 border border-gray-200 rounded-xl font-mono text-sm leading-relaxed focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 resize-y"
                                    />
                                ) : (
                                    <div className="prose prose-sm max-w-none">
                                        <MarkdownRenderer content={documentContent} />
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>

                    {/* Right Panel — Chat */}
                    <div className="flex flex-col bg-gray-50" style={{ width: '35%' }}>
                        {/* Chat Header */}
                        <div className="px-4 py-3 bg-white border-b border-gray-200">
                            <div className="flex items-center gap-2">
                                <div className="w-8 h-8 bg-gradient-to-br from-[#003366] to-[#004488] rounded-lg flex items-center justify-center">
                                    <Bot className="w-4 h-4 text-white" />
                                </div>
                                <div>
                                    <h3 className="font-medium text-gray-900 text-sm">Document Assistant</h3>
                                    <p className="text-xs text-gray-500">
                                        {isStreaming ? 'Thinking...' : 'AI-powered editing help'}
                                    </p>
                                </div>
                            </div>
                        </div>

                        {/* Chat Messages */}
                        <div className="flex-1 overflow-y-auto p-4 space-y-4">
                            {displayChatMessages.map((msg) => (
                                <div key={msg.id} className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
                                    <div
                                        className={`w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 ${
                                            msg.role === 'assistant'
                                                ? 'bg-gradient-to-br from-[#003366] to-[#004488]'
                                                : 'bg-blue-500'
                                        }`}
                                    >
                                        {msg.role === 'assistant' ? (
                                            <Sparkles className="w-3.5 h-3.5 text-white" />
                                        ) : (
                                            <User className="w-3.5 h-3.5 text-white" />
                                        )}
                                    </div>
                                    <div
                                        className={`max-w-[85%] px-3.5 py-2.5 rounded-2xl text-sm leading-relaxed ${
                                            msg.role === 'assistant'
                                                ? 'bg-white border border-gray-200 text-gray-700'
                                                : 'bg-[#003366] text-white'
                                        }`}
                                    >
                                        <ReactMarkdown
                                            components={{
                                                p: ({ children }) => <p className="mb-1.5 last:mb-0">{children}</p>,
                                                ul: ({ children }) => <ul className="list-disc ml-4 mb-1.5 space-y-0.5 text-xs">{children}</ul>,
                                                ol: ({ children }) => <ol className="list-decimal ml-4 mb-1.5 space-y-0.5 text-xs">{children}</ol>,
                                                strong: ({ children }) => <strong className="font-bold">{children}</strong>,
                                                code: ({ children }) => (
                                                    <code className="bg-gray-100 px-1 py-0.5 rounded text-xs font-mono">{children}</code>
                                                ),
                                            }}
                                        >
                                            {msg.content}
                                        </ReactMarkdown>
                                    </div>
                                </div>
                            ))}

                            {/* Typing indicator */}
                            {isStreaming && !streamingAssistantMsg && (
                                <div className="flex gap-3">
                                    <div className="w-7 h-7 rounded-full flex items-center justify-center bg-gradient-to-br from-[#003366] to-[#004488]">
                                        <Sparkles className="w-3.5 h-3.5 text-white" />
                                    </div>
                                    <div className="bg-white border border-gray-200 rounded-2xl px-4 py-3">
                                        <div className="flex items-center gap-1.5">
                                            <div className="typing-dot" />
                                            <div className="typing-dot" />
                                            <div className="typing-dot" />
                                        </div>
                                    </div>
                                </div>
                            )}

                            <div ref={chatEndRef} />
                        </div>

                        {/* Chat Input */}
                        <div className="p-3 bg-white border-t border-gray-200">
                            <div className="flex gap-2">
                                <textarea
                                    ref={textareaRef}
                                    value={chatInput}
                                    onChange={(e) => setChatInput(e.target.value)}
                                    onKeyDown={(e) => {
                                        if (e.key === 'Enter' && !e.shiftKey && !isStreaming) {
                                            e.preventDefault();
                                            handleSendMessage();
                                        }
                                    }}
                                    placeholder={isStreaming ? 'Waiting for response...' : 'Ask about this document...'}
                                    disabled={isStreaming}
                                    rows={1}
                                    className={`flex-1 resize-none px-3.5 py-2.5 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 ${
                                        isStreaming ? 'opacity-50' : ''
                                    }`}
                                    style={{ maxHeight: 120 }}
                                />
                                <button
                                    onClick={handleSendMessage}
                                    disabled={!chatInput.trim() || isStreaming}
                                    className="px-3.5 py-2.5 bg-[#003366] text-white rounded-xl hover:bg-[#004488] disabled:opacity-30 transition-colors"
                                >
                                    <Send className="w-4 h-4" />
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Click-away for download menu */}
            {showDownloadMenu && (
                <div className="fixed inset-0 z-0" onClick={() => setShowDownloadMenu(false)} />
            )}
        </div>
    );
}
