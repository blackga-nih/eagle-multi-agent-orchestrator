'use client';

import { useState, useEffect, useRef, use, useCallback, useMemo } from 'react';
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
    History,
    MessageSquare,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import TopNav from '@/components/layout/top-nav';
import MarkdownRenderer from '@/components/ui/markdown-renderer';
import { useAgentStream } from '@/hooks/use-agent-stream';
import { useAuth } from '@/contexts/auth-context';
import { useSession } from '@/contexts/session-context';
import { ChatMessage, DocumentInfo, DocxPreviewBlock, XlsxPreviewCell, XlsxPreviewSheet } from '@/types/chat';
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
        return text.slice(0, 200) || `Request failed (${response.status})`;
    } catch {
        return `Request failed (${response.status})`;
    }
}

interface ChangelogEntry {
    change_type: string;
    change_source: string;
    change_summary: string;
    doc_type?: string;
    version?: number;
    actor_user_id?: string;
    created_at: string;
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
    const [editContent, setEditContent] = useState('');
    const [isEditing, setIsEditing] = useState(false);
    const [isLoading, setIsLoading] = useState(true);
    const [docUpdated, setDocUpdated] = useState(false);
    const [unfilledCount, setUnfilledCount] = useState(0);
    const [showHydrationBanner, setShowHydrationBanner] = useState(false);
    const autoPromptSentRef = useRef(false);

    // Binary document state
    const [docxPreviewBlocks, setDocxPreviewBlocks] = useState<DocxPreviewBlock[]>([]);
    const [editDocxPreviewBlocks, setEditDocxPreviewBlocks] = useState<DocxPreviewBlock[]>([]);
    const [docxPreviewMode, setDocxPreviewMode] = useState<string | null>(null);
    const [xlsxPreviewSheets, setXlsxPreviewSheets] = useState<XlsxPreviewSheet[]>([]);
    const [editXlsxPreviewSheets, setEditXlsxPreviewSheets] = useState<XlsxPreviewSheet[]>([]);
    const [activeXlsxSheetId, setActiveXlsxSheetId] = useState<string>('');
    const [isBinaryDocument, setIsBinaryDocument] = useState(false);
    const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
    const [isSaving, setIsSaving] = useState(false);
    const [saveError, setSaveError] = useState<string | null>(null);
    const [documentKey, setDocumentKey] = useState<string>('');
    const [packageId, setPackageId] = useState<string | null>(null);
    const [documentVersion, setDocumentVersion] = useState<number | null>(null);

    // Right panel tab state
    const [rightTab, setRightTab] = useState<'chat' | 'changelog'>('chat');
    const [changelog, setChangelog] = useState<ChangelogEntry[]>([]);
    const [changelogLoading, setChangelogLoading] = useState(false);

    const isDocxDocument = useMemo(() => docxPreviewMode === 'docx_blocks' || docxPreviewMode === 'text_fallback', [docxPreviewMode]);
    const isXlsxDocument = useMemo(() => xlsxPreviewSheets.length > 0, [xlsxPreviewSheets]);

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
    const chatEndRef = useRef<HTMLDivElement>(null);
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    // Download state
    const [showDownloadMenu, setShowDownloadMenu] = useState(false);
    const [isExporting, setIsExporting] = useState(false);
    const [exportError, setExportError] = useState<string | null>(null);

    const { getToken } = useAuth();
    const { loadSession } = useSession();

    // Load document from sessionStorage or API
    useEffect(() => {
        const decodedId = decodeURIComponent(id);

        // Try sessionStorage first (instant load from chat navigation)
        try {
            const stored = sessionStorage.getItem(`doc-content-${id}`)
                || sessionStorage.getItem(`doc-content-${encodeURIComponent(decodedId).replace(/\./g, '%2E')}`);
            if (stored) {
                const doc: DocumentInfo = JSON.parse(stored);
                if (doc.content) {
                    setDocumentTitle(doc.title);
                    setDocumentType(doc.document_type);
                    setDocumentContent(doc.content);
                    setEditContent(doc.content);
                    setDocumentKey(doc.s3_key || decodedId);
                    if (doc.package_id) setPackageId(doc.package_id);
                    if (doc.version) setDocumentVersion(doc.version);
                    setIsLoading(false);
                    return;
                }
                setDocumentTitle(doc.title);
                setDocumentType(doc.document_type);
            }
        } catch {
            // sessionStorage unavailable or parse error
        }

        // Try localStorage (handles navigation from Documents page)
        const stored2 = getGeneratedDocument(id);
        if (stored2?.content) {
            setDocumentTitle(stored2.title);
            setDocumentType(stored2.document_type);
            setDocumentContent(stored2.content);
            setEditContent(stored2.content);
            setDocumentKey(stored2.s3_key || decodedId);
            setIsLoading(false);
            return;
        }

        // Fallback: try fetching from API, then from local templates
        async function fetchDocument() {
            try {
                const token = await getToken();
                const res = await fetch(`/api/documents/${encodeURIComponent(decodedId)}?content=true`, {
                    headers: token ? { Authorization: `Bearer ${token}` } : {},
                });
                if (res.ok) {
                    const data = await res.json();
                    setDocumentTitle(data.title || 'Untitled Document');
                    setDocumentType(data.document_type || '');
                    setDocumentContent(data.content || '');
                    setEditContent(data.content || '');
                    setDocumentKey(data.s3_key || data.key || decodedId);
                    if (data.package_id) setPackageId(data.package_id);
                    if (data.version) setDocumentVersion(data.version);

                    // Handle binary document preview
                    if (data.is_binary || data.preview_mode) {
                        setIsBinaryDocument(true);
                        if (data.download_url) setDownloadUrl(data.download_url);

                        if (data.preview_blocks && data.preview_blocks.length > 0) {
                            setDocxPreviewBlocks(data.preview_blocks);
                            setEditDocxPreviewBlocks(JSON.parse(JSON.stringify(data.preview_blocks)));
                            setDocxPreviewMode(data.preview_mode || 'docx_blocks');
                        }
                        if (data.preview_sheets && data.preview_sheets.length > 0) {
                            setXlsxPreviewSheets(data.preview_sheets);
                            setEditXlsxPreviewSheets(JSON.parse(JSON.stringify(data.preview_sheets)));
                            if (data.preview_sheets[0]?.sheet_id) {
                                setActiveXlsxSheetId(data.preview_sheets[0].sheet_id);
                            }
                        }
                    }

                    setIsLoading(false);
                    return;
                }
            } catch {
                // Backend unavailable — try template fallback
            }

            // Try loading from local template files
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
        if (isBinaryDocument) return; // Skip hydration for binary docs
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isLoading]);

    // Agent stream for the document chat
    const { sendQuery, isStreaming } = useAgentStream({
        getToken,
        onMessage: (msg) => {
            setChatMessages((prev) => [
                ...prev,
                {
                    id: msg.id,
                    role: 'assistant',
                    content: msg.content,
                    timestamp: msg.timestamp,
                    reasoning: msg.reasoning,
                    agent_id: msg.agent_id,
                    agent_name: msg.agent_name,
                },
            ]);
        },
        onDocumentGenerated: (doc) => {
            if (doc.content) {
                setDocumentContent(doc.content);
                setEditContent(doc.content);
                if (doc.title) setDocumentTitle(doc.title);
                if (doc.document_type) setDocumentType(doc.document_type);

                setDocUpdated(true);
                setTimeout(() => setDocUpdated(false), 2000);
            }
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

        const userMsg: ChatMessage = {
            id: `auto-${Date.now()}`,
            role: 'user',
            content: 'Automatically filling in remaining document sections from conversation context...',
            timestamp: new Date(),
        };
        setChatMessages((prev) => [...prev, userMsg]);
        sendQuery(autoPrompt, sessionId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [unfilledCount, isLoading, isStreaming, showHydrationBanner]);

    // Scroll chat to bottom
    useEffect(() => {
        chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [chatMessages, isStreaming]);

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

    // Fetch changelog when tab switches
    useEffect(() => {
        if (rightTab !== 'changelog' || !documentKey) return;

        const fetchChangelog = async () => {
            setChangelogLoading(true);
            try {
                const token = await getToken();
                const headers: Record<string, string> = {};
                if (token) headers.Authorization = `Bearer ${token}`;

                const res = await fetch(`/api/document-changelog?key=${encodeURIComponent(documentKey)}&limit=50`, { headers });
                if (res.ok) {
                    const data = await res.json();
                    setChangelog(data.entries || []);
                }
            } catch {
                // Silently fail
            } finally {
                setChangelogLoading(false);
            }
        };

        fetchChangelog();
    }, [rightTab, documentKey, getToken]);

    const handleSendMessage = async () => {
        if (!chatInput.trim() || isStreaming) return;

        const userMsg: ChatMessage = {
            id: Date.now().toString(),
            role: 'user',
            content: chatInput,
            timestamp: new Date(),
        };
        setChatMessages((prev) => [...prev, userMsg]);
        const query = chatInput;
        setChatInput('');

        // Build context-aware prompt for edit requests on binary documents
        if (isBinaryDocument && EDIT_INTENT_RE.test(query) && documentKey) {
            const docContext = documentContent
                ? truncateWithEllipsis(sanitizeContextText(documentContent), MAX_DOC_CONTEXT_CHARS)
                : '';
            const enrichedQuery = `${query}\n\n[Document context: key=${documentKey}${docContext ? `, preview:\n${docContext}` : ''}]`;
            await sendQuery(enrichedQuery, sessionId);
        } else {
            await sendQuery(query, sessionId);
        }
    };

    const handleToggleEdit = () => {
        if (isEditing) {
            // Switching from edit to preview — save edits
            if (isDocxDocument) {
                setDocxPreviewBlocks(JSON.parse(JSON.stringify(editDocxPreviewBlocks)));
            } else if (isXlsxDocument) {
                setXlsxPreviewSheets(JSON.parse(JSON.stringify(editXlsxPreviewSheets)));
            } else {
                setDocumentContent(editContent);
            }
        } else {
            if (isDocxDocument) {
                setEditDocxPreviewBlocks(JSON.parse(JSON.stringify(docxPreviewBlocks)));
            } else if (isXlsxDocument) {
                setEditXlsxPreviewSheets(JSON.parse(JSON.stringify(xlsxPreviewSheets)));
            } else {
                setEditContent(documentContent);
            }
        }
        setIsEditing(!isEditing);
    };

    // Save structured edits (DOCX/XLSX)
    const handleSaveStructuredEdits = async () => {
        setIsSaving(true);
        setSaveError(null);
        try {
            const token = await getToken();
            const headers: Record<string, string> = { 'Content-Type': 'application/json' };
            if (token) headers.Authorization = `Bearer ${token}`;

            let res: Response;
            if (isDocxDocument) {
                res = await fetch(`/api/documents/${encodeURIComponent(documentKey)}/docx-edit`, {
                    method: 'POST',
                    headers,
                    body: JSON.stringify({
                        preview_blocks: editDocxPreviewBlocks,
                        preview_mode: docxPreviewMode,
                        change_source: 'user_edit',
                    }),
                });
            } else if (isXlsxDocument) {
                // Collect cell edits from modified sheets
                const cellEdits: Array<{ sheet_id: string; cell_ref: string; value: string }> = [];
                for (let si = 0; si < editXlsxPreviewSheets.length; si++) {
                    const editSheet = editXlsxPreviewSheets[si];
                    const origSheet = xlsxPreviewSheets[si];
                    if (!origSheet) continue;
                    for (let ri = 0; ri < editSheet.rows.length; ri++) {
                        const editRow = editSheet.rows[ri];
                        const origRow = origSheet.rows[ri];
                        if (!origRow) continue;
                        for (let ci = 0; ci < editRow.cells.length; ci++) {
                            const editCell = editRow.cells[ci];
                            const origCell = origRow.cells[ci];
                            if (!origCell || !editCell.editable) continue;
                            if (editCell.value !== origCell.value) {
                                cellEdits.push({
                                    sheet_id: editSheet.sheet_id,
                                    cell_ref: editCell.cell_ref,
                                    value: editCell.value,
                                });
                            }
                        }
                    }
                }
                if (cellEdits.length === 0) {
                    setSaveError('No changes detected');
                    setIsSaving(false);
                    return;
                }
                res = await fetch(`/api/documents/${encodeURIComponent(documentKey)}/xlsx-edit`, {
                    method: 'POST',
                    headers,
                    body: JSON.stringify({ cell_edits: cellEdits, change_source: 'user_edit' }),
                });
            } else {
                setIsSaving(false);
                return;
            }

            if (!res.ok) {
                const errMsg = await extractResponseError(res);
                setSaveError(errMsg);
                return;
            }

            const result = await res.json();

            // Update state with new preview data
            if (result.preview_blocks) {
                setDocxPreviewBlocks(result.preview_blocks);
                setEditDocxPreviewBlocks(JSON.parse(JSON.stringify(result.preview_blocks)));
            }
            if (result.preview_sheets) {
                setXlsxPreviewSheets(result.preview_sheets);
                setEditXlsxPreviewSheets(JSON.parse(JSON.stringify(result.preview_sheets)));
            }
            if (result.content) {
                setDocumentContent(result.content);
            }
            if (result.version) setDocumentVersion(result.version);

            setIsEditing(false);
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

        // For binary documents with a download URL, use presigned URL directly
        if (isBinaryDocument && downloadUrl && format === 'docx') {
            window.open(downloadUrl, '_blank');
            return;
        }

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
                throw new Error(`Export failed: ${res.status}`);
            }

            const blob = await res.blob();
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

    // DOCX block editor helpers
    const updateDocxBlock = useCallback((blockId: string, field: 'text' | 'checked', value: string | boolean) => {
        setEditDocxPreviewBlocks(prev => prev.map(block =>
            block.block_id === blockId
                ? { ...block, [field]: value }
                : block
        ));
    }, []);

    // XLSX cell editor helpers
    const updateXlsxCell = useCallback((sheetId: string, cellRef: string, value: string) => {
        setEditXlsxPreviewSheets(prev => prev.map(sheet =>
            sheet.sheet_id === sheetId
                ? {
                    ...sheet,
                    rows: sheet.rows.map(row => ({
                        ...row,
                        cells: row.cells.map(cell =>
                            cell.cell_ref === cellRef ? { ...cell, value } : cell
                        ),
                    })),
                }
                : sheet
        ));
    }, []);

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

    // --- Render: DOCX Block Editor ---
    const renderDocxBlockEditor = () => {
        const blocks = isEditing ? editDocxPreviewBlocks : docxPreviewBlocks;
        if (!blocks || blocks.length === 0) {
            return <p className="text-gray-400 italic">No preview blocks available.</p>;
        }

        return (
            <div className="space-y-2">
                {blocks.map((block) => {
                    if (block.kind === 'heading') {
                        const HeadingTag = `h${Math.min(block.level || 1, 6)}` as keyof JSX.IntrinsicElements;
                        const sizes: Record<number, string> = { 1: 'text-2xl', 2: 'text-xl', 3: 'text-lg' };
                        const sizeClass = sizes[block.level || 1] || 'text-base';

                        if (isEditing) {
                            return (
                                <input
                                    key={block.block_id}
                                    type="text"
                                    value={block.text}
                                    onChange={(e) => updateDocxBlock(block.block_id, 'text', e.target.value)}
                                    className={`w-full ${sizeClass} font-bold border-b border-gray-200 focus:border-blue-500 focus:outline-none py-1 bg-transparent`}
                                />
                            );
                        }
                        return (
                            <HeadingTag key={block.block_id} className={`${sizeClass} font-bold text-gray-900`}>
                                {block.text}
                            </HeadingTag>
                        );
                    }

                    if (block.kind === 'checkbox') {
                        return (
                            <label key={block.block_id} className="flex items-start gap-2 py-0.5 cursor-pointer">
                                <input
                                    type="checkbox"
                                    checked={block.checked ?? false}
                                    disabled={!isEditing}
                                    onChange={(e) => updateDocxBlock(block.block_id, 'checked', e.target.checked)}
                                    className="mt-1 rounded border-gray-300"
                                />
                                {isEditing ? (
                                    <input
                                        type="text"
                                        value={block.text}
                                        onChange={(e) => updateDocxBlock(block.block_id, 'text', e.target.value)}
                                        className="flex-1 border-b border-gray-200 focus:border-blue-500 focus:outline-none text-sm bg-transparent"
                                    />
                                ) : (
                                    <span className={`text-sm ${block.checked ? 'line-through text-gray-400' : 'text-gray-700'}`}>
                                        {block.text}
                                    </span>
                                )}
                            </label>
                        );
                    }

                    // Paragraph
                    if (isEditing) {
                        return (
                            <textarea
                                key={block.block_id}
                                value={block.text}
                                onChange={(e) => updateDocxBlock(block.block_id, 'text', e.target.value)}
                                rows={Math.max(2, Math.ceil(block.text.length / 80))}
                                className="w-full text-sm border border-gray-200 rounded-lg p-2 focus:border-blue-500 focus:outline-none resize-y bg-white"
                            />
                        );
                    }
                    return (
                        <p key={block.block_id} className="text-sm text-gray-700 leading-relaxed">
                            {block.text}
                        </p>
                    );
                })}
            </div>
        );
    };

    // --- Render: XLSX Grid Editor ---
    const renderXlsxGridEditor = () => {
        const sheets = isEditing ? editXlsxPreviewSheets : xlsxPreviewSheets;
        if (!sheets || sheets.length === 0) {
            return <p className="text-gray-400 italic">No spreadsheet data available.</p>;
        }

        const activeSheet = sheets.find(s => s.sheet_id === activeXlsxSheetId) || sheets[0];

        return (
            <div className="flex flex-col h-full">
                {/* Sheet tabs */}
                {sheets.length > 1 && (
                    <div className="flex gap-1 px-2 py-1 bg-gray-100 border-b border-gray-200 overflow-x-auto">
                        {sheets.map((sheet) => (
                            <button
                                key={sheet.sheet_id}
                                onClick={() => setActiveXlsxSheetId(sheet.sheet_id)}
                                className={`px-3 py-1 text-xs rounded-t-lg whitespace-nowrap ${
                                    sheet.sheet_id === activeXlsxSheetId
                                        ? 'bg-white border border-b-white border-gray-200 font-medium text-gray-900'
                                        : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50'
                                }`}
                            >
                                {sheet.title}
                            </button>
                        ))}
                    </div>
                )}

                {/* Grid */}
                <div className="flex-1 overflow-auto">
                    <table className="border-collapse text-xs w-full">
                        <tbody>
                            {activeSheet.rows.map((row) => (
                                <tr key={row.row_index} className="border-b border-gray-100">
                                    <td className="px-1 py-0.5 bg-gray-50 text-gray-400 text-right border-r border-gray-200 select-none w-8">
                                        {row.row_index}
                                    </td>
                                    {row.cells.map((cell) => (
                                        <td
                                            key={cell.cell_ref}
                                            className={`px-1.5 py-0.5 border-r border-gray-100 min-w-[80px] max-w-[200px] ${
                                                cell.is_formula ? 'bg-blue-50/30 text-blue-700' : ''
                                            } ${!cell.editable ? 'bg-gray-50/50' : ''}`}
                                        >
                                            {isEditing && cell.editable ? (
                                                <input
                                                    type="text"
                                                    value={cell.value}
                                                    onChange={(e) => updateXlsxCell(activeSheet.sheet_id, cell.cell_ref, e.target.value)}
                                                    className="w-full border-none bg-transparent focus:bg-blue-50 focus:outline-none text-xs px-0.5"
                                                />
                                            ) : (
                                                <span className="block truncate" title={cell.display_value}>
                                                    {cell.display_value || cell.value}
                                                </span>
                                            )}
                                        </td>
                                    ))}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>

                {activeSheet.truncated && (
                    <div className="px-3 py-1 text-xs text-amber-600 bg-amber-50 border-t border-amber-200">
                        Preview truncated. Download the file for the complete spreadsheet.
                    </div>
                )}
            </div>
        );
    };

    // --- Render: Changelog Tab ---
    const renderChangelogTab = () => {
        if (changelogLoading) {
            return (
                <div className="flex items-center justify-center py-8 text-gray-400">
                    <RefreshCw className="w-4 h-4 animate-spin mr-2" />
                    Loading changelog...
                </div>
            );
        }

        if (changelog.length === 0) {
            return (
                <div className="text-center py-8 text-gray-400 text-sm">
                    No changelog entries yet.
                </div>
            );
        }

        return (
            <div className="space-y-3 p-4">
                {changelog.map((entry, idx) => (
                    <div key={idx} className="bg-white rounded-lg border border-gray-200 p-3">
                        <div className="flex items-center gap-2 mb-1">
                            <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${
                                entry.change_source === 'agent_tool'
                                    ? 'bg-purple-100 text-purple-700'
                                    : 'bg-blue-100 text-blue-700'
                            }`}>
                                {entry.change_source === 'agent_tool' ? 'AI' : 'User'}
                            </span>
                            <span className="text-xs text-gray-500">
                                {entry.change_type}
                                {entry.version ? ` v${entry.version}` : ''}
                            </span>
                        </div>
                        <p className="text-sm text-gray-700">{entry.change_summary}</p>
                        <p className="text-xs text-gray-400 mt-1">
                            {new Date(entry.created_at).toLocaleString()}
                            {entry.actor_user_id ? ` by ${entry.actor_user_id}` : ''}
                        </p>
                    </div>
                ))}
            </div>
        );
    };

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
                                    {documentVersion && (
                                        <span className="text-xs text-gray-400">v{documentVersion}</span>
                                    )}
                                </div>
                                {documentType && (
                                    <span className="text-xs text-gray-500">
                                        {DOC_TYPE_LABELS[documentType] || documentType}
                                        {isBinaryDocument && isDocxDocument && ' (DOCX)'}
                                        {isBinaryDocument && isXlsxDocument && ' (XLSX)'}
                                    </span>
                                )}
                            </div>
                        </div>
                        <div className="flex items-center gap-2">
                            {/* Save/export errors */}
                            {(exportError || saveError) && (
                                <span className="text-xs text-red-600 mr-2">{exportError || saveError}</span>
                            )}

                            {/* Save button for structured edits */}
                            {isEditing && (isDocxDocument || isXlsxDocument) && (
                                <button
                                    onClick={handleSaveStructuredEdits}
                                    disabled={isSaving}
                                    className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-xl text-sm font-medium hover:bg-green-700 transition-colors disabled:opacity-50"
                                >
                                    {isSaving ? (
                                        <RefreshCw className="w-4 h-4 animate-spin" />
                                    ) : (
                                        <Save className="w-4 h-4" />
                                    )}
                                    Save
                                </button>
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
                                {isDocxDocument ? (
                                    renderDocxBlockEditor()
                                ) : isXlsxDocument ? (
                                    renderXlsxGridEditor()
                                ) : isEditing ? (
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

                    {/* Right Panel — Chat + Changelog */}
                    <div className="flex flex-col bg-gray-50" style={{ width: '35%' }}>
                        {/* Right panel tabs */}
                        <div className="flex bg-white border-b border-gray-200">
                            <button
                                onClick={() => setRightTab('chat')}
                                className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                                    rightTab === 'chat'
                                        ? 'border-[#003366] text-[#003366]'
                                        : 'border-transparent text-gray-500 hover:text-gray-700'
                                }`}
                            >
                                <MessageSquare className="w-4 h-4" />
                                Chat
                            </button>
                            <button
                                onClick={() => setRightTab('changelog')}
                                className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                                    rightTab === 'changelog'
                                        ? 'border-[#003366] text-[#003366]'
                                        : 'border-transparent text-gray-500 hover:text-gray-700'
                                }`}
                            >
                                <History className="w-4 h-4" />
                                Changelog
                            </button>
                        </div>

                        {rightTab === 'chat' ? (
                            <>
                                {/* Chat Messages */}
                                <div className="flex-1 overflow-y-auto p-4 space-y-4">
                                    {chatMessages.map((msg) => (
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
                                    {isStreaming && (
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
                            </>
                        ) : (
                            <div className="flex-1 overflow-y-auto">
                                {renderChangelogTab()}
                            </div>
                        )}
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
