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
        return text || `Request failed (${response.status})`;
    } catch {
        return `Request failed (${response.status})`;
    }
}

function normalizeDocxPreviewBlocks(blocks: unknown): DocxPreviewBlock[] {
    if (!Array.isArray(blocks)) return [];
    return blocks.flatMap((block) => {
        if (!block || typeof block !== 'object') return [];
        const raw = block as Record<string, unknown>;
        const kind = raw.kind;
        if (kind !== 'heading' && kind !== 'paragraph' && kind !== 'checkbox') return [];
        return [{
            block_id: typeof raw.block_id === 'string' ? raw.block_id : '',
            kind,
            text: typeof raw.text === 'string' ? raw.text : '',
            level: typeof raw.level === 'number' ? raw.level : null,
            checked: typeof raw.checked === 'boolean' ? raw.checked : null,
        }];
    });
}

function cloneDocxPreviewBlocks(blocks: DocxPreviewBlock[]): DocxPreviewBlock[] {
    return blocks.map((block) => ({ ...block }));
}

function docxPreviewBlocksEqual(left: DocxPreviewBlock[], right: DocxPreviewBlock[]): boolean {
    if (left.length !== right.length) return false;
    return left.every((block, index) => {
        const other = right[index];
        return (
            block.block_id === other.block_id
            && block.kind === other.kind
            && block.text === other.text
            && (block.level ?? null) === (other.level ?? null)
            && (block.checked ?? null) === (other.checked ?? null)
        );
    });
}

function normalizeXlsxPreviewSheets(sheets: unknown): XlsxPreviewSheet[] {
    if (!Array.isArray(sheets)) return [];
    return sheets.flatMap((sheet) => {
        if (!sheet || typeof sheet !== 'object') return [];
        const rawSheet = sheet as Record<string, unknown>;
        if (!Array.isArray(rawSheet.rows) || typeof rawSheet.sheet_id !== 'string' || typeof rawSheet.title !== 'string') {
            return [];
        }
        const rows = rawSheet.rows.flatMap((row) => {
            if (!row || typeof row !== 'object') return [];
            const rawRow = row as Record<string, unknown>;
            if (!Array.isArray(rawRow.cells) || typeof rawRow.row_index !== 'number') return [];
            const cells = rawRow.cells.flatMap((cell) => {
                if (!cell || typeof cell !== 'object') return [];
                const rawCell = cell as Record<string, unknown>;
                if (
                    typeof rawCell.cell_ref !== 'string'
                    || typeof rawCell.row !== 'number'
                    || typeof rawCell.col !== 'number'
                    || typeof rawCell.display_value !== 'string'
                    || typeof rawCell.value !== 'string'
                    || typeof rawCell.editable !== 'boolean'
                ) {
                    return [];
                }
                return [{
                    cell_ref: rawCell.cell_ref,
                    row: rawCell.row,
                    col: rawCell.col,
                    value: rawCell.value,
                    display_value: rawCell.display_value,
                    editable: rawCell.editable,
                    is_formula: typeof rawCell.is_formula === 'boolean' ? rawCell.is_formula : false,
                }];
            });
            return [{
                row_index: rawRow.row_index,
                cells,
            }];
        });
        return [{
            sheet_id: rawSheet.sheet_id,
            title: rawSheet.title,
            max_row: typeof rawSheet.max_row === 'number' ? rawSheet.max_row : rows.length,
            max_col: typeof rawSheet.max_col === 'number' ? rawSheet.max_col : 0,
            truncated: typeof rawSheet.truncated === 'boolean' ? rawSheet.truncated : false,
            rows,
        }];
    });
}

function cloneXlsxPreviewSheets(sheets: XlsxPreviewSheet[]): XlsxPreviewSheet[] {
    return sheets.map((sheet) => ({
        ...sheet,
        rows: sheet.rows.map((row) => ({
            ...row,
            cells: row.cells.map((cell) => ({ ...cell })),
        })),
    }));
}

function xlsxPreviewSheetsEqual(left: XlsxPreviewSheet[], right: XlsxPreviewSheet[]): boolean {
    if (left.length !== right.length) return false;
    return left.every((sheet, sheetIndex) => {
        const otherSheet = right[sheetIndex];
        if (!otherSheet || sheet.sheet_id !== otherSheet.sheet_id || sheet.rows.length !== otherSheet.rows.length) {
            return false;
        }
        return sheet.rows.every((row, rowIndex) => {
            const otherRow = otherSheet.rows[rowIndex];
            if (!otherRow || row.row_index !== otherRow.row_index || row.cells.length !== otherRow.cells.length) {
                return false;
            }
            return row.cells.every((cell, cellIndex) => {
                const otherCell = otherRow.cells[cellIndex];
                return Boolean(
                    otherCell
                    && cell.cell_ref === otherCell.cell_ref
                    && cell.value === otherCell.value
                    && cell.display_value === otherCell.display_value
                    && cell.editable === otherCell.editable
                );
            });
        });
    });
}

function collectXlsxCellEdits(originalSheets: XlsxPreviewSheet[], editedSheets: XlsxPreviewSheet[]) {
    const originalMap = new Map<string, XlsxPreviewCell>();
    for (const sheet of originalSheets) {
        for (const row of sheet.rows) {
            for (const cell of row.cells) {
                originalMap.set(`${sheet.sheet_id}:${cell.cell_ref}`, cell);
            }
        }
    }

    const edits: Array<{ sheet_id: string; cell_ref: string; value: string }> = [];
    for (const sheet of editedSheets) {
        for (const row of sheet.rows) {
            for (const cell of row.cells) {
                if (!cell.editable) continue;
                const original = originalMap.get(`${sheet.sheet_id}:${cell.cell_ref}`);
                if (!original) continue;
                if (original.value !== cell.value) {
                    edits.push({
                        sheet_id: sheet.sheet_id,
                        cell_ref: cell.cell_ref,
                        value: cell.value,
                    });
                }
            }
        }
    }
    return edits;
}

function autoResizeTextarea(element: HTMLTextAreaElement | null) {
    if (!element) return;
    element.style.height = '0px';
    element.style.height = `${element.scrollHeight}px`;
}

// ---------------------------------------------------------------------------
// Changelog Panel Component
// ---------------------------------------------------------------------------

interface ChangelogEntry {
    changelog_id: string;
    change_type: 'create' | 'update' | 'finalize';
    change_source: 'agent_tool' | 'user_edit';
    change_summary: string;
    doc_type: string;
    version: number;
    actor_user_id: string;
    created_at: string;
}

function formatRelativeTime(dateStr: string): string {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);

    if (diffMins < 1) return 'just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    const diffDays = Math.floor(diffHours / 24);
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
}

function DocumentChangelogPanel({
    packageId,
    documentType,
    documentKey,
}: {
    packageId?: string;
    documentType?: string;
    documentKey?: string;
}) {
    const [entries, setEntries] = useState<ChangelogEntry[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        // Need either (packageId + documentType) OR documentKey
        const canFetchPackage = packageId && documentType;
        const canFetchByKey = documentKey;

        if (!canFetchPackage && !canFetchByKey) return;

        const fetchChangelog = async () => {
            setLoading((prev) => (entries.length === 0 ? true : prev));
            setError(null);
            try {
                let url: string;
                if (canFetchPackage) {
                    url = `/api/packages/${packageId}/documents/${documentType}/changelog?limit=50`;
                } else {
                    url = `/api/document-changelog?key=${encodeURIComponent(documentKey!)}&limit=50`;
                }

                const res = await fetch(url);
                if (!res.ok) throw new Error('Failed to fetch changelog');
                const data = await res.json();
                setEntries(data.entries || []);
            } catch (err) {
                setError(err instanceof Error ? err.message : 'Failed to load changelog');
            } finally {
                setLoading(false);
            }
        };

        void fetchChangelog();
        const intervalId = window.setInterval(() => {
            void fetchChangelog();
        }, 10000);

        return () => window.clearInterval(intervalId);
    }, [documentKey, documentType, entries.length, packageId]);

    // No way to fetch changelog
    if (!packageId && !documentType && !documentKey) {
        return (
            <div className="flex-1 flex flex-col items-center justify-center text-center px-4">
                <div className="w-12 h-12 rounded-full bg-gray-100 flex items-center justify-center mb-3">
                    <History className="w-6 h-6 text-gray-400" />
                </div>
                <p className="text-sm text-gray-500">No document loaded</p>
                <p className="text-xs text-gray-400 mt-1">Document history will appear here.</p>
            </div>
        );
    }

    if (loading) {
        return (
            <div className="flex-1 flex items-center justify-center">
                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-[#003366]" />
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex-1 flex flex-col items-center justify-center text-center px-4">
                <p className="text-sm text-red-500">{error}</p>
            </div>
        );
    }

    if (entries.length === 0) {
        return (
            <div className="flex-1 flex flex-col items-center justify-center text-center px-4">
                <div className="w-12 h-12 rounded-full bg-gray-100 flex items-center justify-center mb-3">
                    <History className="w-6 h-6 text-gray-400" />
                </div>
                <p className="text-sm text-gray-500">No changelog entries yet.</p>
                <p className="text-xs text-gray-400 mt-1">Document changes will appear here.</p>
            </div>
        );
    }

    const changeTypeStyles: Record<string, { bg: string; text: string }> = {
        create: { bg: 'bg-green-100', text: 'text-green-700' },
        update: { bg: 'bg-blue-100', text: 'text-blue-700' },
        finalize: { bg: 'bg-purple-100', text: 'text-purple-700' },
    };

    return (
        <div className="flex-1 overflow-y-auto p-4 space-y-2">
            {entries.map((entry) => {
                const style = changeTypeStyles[entry.change_type] || { bg: 'bg-gray-100', text: 'text-gray-700' };
                const isAgent = entry.change_source === 'agent_tool';

                return (
                    <div
                        key={entry.changelog_id || `${entry.created_at}-${entry.doc_type}`}
                        className="flex items-start gap-2.5 rounded-lg border border-gray-200 bg-white px-3 py-2.5 hover:shadow-sm transition"
                    >
                        <span className="shrink-0 w-7 h-7 rounded-full flex items-center justify-center bg-gray-100">
                            {isAgent ? (
                                <Bot className="w-4 h-4 text-[#003366]" />
                            ) : (
                                <User className="w-4 h-4 text-gray-600" />
                            )}
                        </span>
                        <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2">
                                <span className={`px-1.5 py-0.5 rounded text-[9px] font-medium uppercase ${style.bg} ${style.text}`}>
                                    {entry.change_type}
                                </span>
                                <span className="text-[10px] text-gray-400">
                                    v{entry.version}
                                </span>
                            </div>
                            <p className="text-xs text-gray-700 mt-1">{entry.change_summary}</p>
                            <div className="flex items-center gap-2 mt-1">
                                <p className="text-[10px] text-gray-400">
                                    {formatRelativeTime(entry.created_at)} by {entry.actor_user_id}
                                </p>
                            </div>
                        </div>
                    </div>
                );
            })}
        </div>
    );
}

// Helper to extract package_id and doc_type from S3 key.
// Supports both:
// - eagle/{tenant}/{user}/packages/{package_id}/{doc_type}_v{N}.{ext}
// - eagle/{tenant}/packages/{package_id}/{doc_type}/v{N}/source.{ext}
function extractPackageInfo(key: string): { packageId?: string; docType?: string } {
    if (!key.includes('/packages/')) return {};
    const parts = key.split('/');
    try {
        const pkgIdx = parts.indexOf('packages');
        const packageId = parts[pkgIdx + 1];
        const canonicalDocType = parts[pkgIdx + 2];
        const versionSegment = parts[pkgIdx + 3];
        if (canonicalDocType && versionSegment?.startsWith('v')) {
            return { packageId, docType: canonicalDocType };
        }
        const filename = parts[parts.length - 1];
        const docType = filename.includes('_v')
            ? filename.split('_v')[0]
            : filename.split('.')[0];
        return { packageId, docType };
    } catch {
        return {};
    }
}

export default function DocumentViewerPage({ params }: PageProps) {
    const { id } = use(params);
    const router = useRouter();
    const searchParams = useSearchParams();
    const sessionId = searchParams.get('session') || '';

    // Extract package info from URL param as fallback
    const urlPackageInfo = useMemo(() => extractPackageInfo(decodeURIComponent(id)), [id]);

    // Document state
    const [documentContent, setDocumentContent] = useState('');
    const [documentTitle, setDocumentTitle] = useState('');
    const [documentType, setDocumentType] = useState('');
    const [fileType, setFileType] = useState('');
    const [contentType, setContentType] = useState('');
    const [isBinaryDocument, setIsBinaryDocument] = useState(false);
    const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
    const [packageId, setPackageId] = useState<string | undefined>(undefined);
    const [currentDocumentId, setCurrentDocumentId] = useState<string | null>(null);
    const [currentVersion, setCurrentVersion] = useState<number | null>(null);
    const [editContent, setEditContent] = useState('');
    const [docxPreviewMode, setDocxPreviewMode] = useState<DocumentInfo['preview_mode']>(null);
    const [docxPreviewBlocks, setDocxPreviewBlocks] = useState<DocxPreviewBlock[]>([]);
    const [editDocxPreviewBlocks, setEditDocxPreviewBlocks] = useState<DocxPreviewBlock[]>([]);
    const [xlsxPreviewSheets, setXlsxPreviewSheets] = useState<XlsxPreviewSheet[]>([]);
    const [editXlsxPreviewSheets, setEditXlsxPreviewSheets] = useState<XlsxPreviewSheet[]>([]);
    const [activeXlsxSheetId, setActiveXlsxSheetId] = useState<string | null>(null);
    const [isEditing, setIsEditing] = useState(false);
    const [isLoading, setIsLoading] = useState(true);
    const [docUpdated, setDocUpdated] = useState(false);
    const [unfilledCount, setUnfilledCount] = useState(0);
    const [showHydrationBanner, setShowHydrationBanner] = useState(false);
    const autoPromptSentRef = useRef(false);

    // Assistant panel tab state
    const [assistantTab, setAssistantTab] = useState<'chat' | 'changelog'>('chat');

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
    const docxBlockRefs = useRef<Record<string, HTMLDivElement | null>>({});

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
    const isDocxDocument = (fileType || '').toLowerCase() === 'docx';
    const isXlsxDocument = (fileType || '').toLowerCase() === 'xlsx';
    const canUseAiDocAssistant = !isBinaryDocument || isDocxDocument;
    const canEditDocxPreview = isBinaryDocument && isDocxDocument && docxPreviewBlocks.length > 0;
    const canEditXlsxPreview = isBinaryDocument && isXlsxDocument && xlsxPreviewSheets.length > 0;
    const hasDocxPreviewChanges = docxPreviewBlocksEqual(editDocxPreviewBlocks, docxPreviewBlocks) === false;
    const hasXlsxPreviewChanges = xlsxPreviewSheetsEqual(editXlsxPreviewSheets, xlsxPreviewSheets) === false;
    const currentBinaryDownloadTarget = useMemo(() => {
        if (!isBinaryDocument) return null;
        return s3Key || decodeURIComponent(id);
    }, [id, isBinaryDocument, s3Key]);

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
        if (doc.file_type !== undefined) {
            setFileType(doc.file_type || '');
        }
        if (doc.content_type !== undefined) {
            setContentType(doc.content_type || '');
        }
        if (typeof doc.is_binary === 'boolean') {
            setIsBinaryDocument(doc.is_binary);
        }
        if ('download_url' in doc) {
            setDownloadUrl(doc.download_url || null);
        }
        // Track the S3 key for save operations
        const docS3Key = doc.s3_key || doc.document_id;
        if (docS3Key) {
            setS3Key(docS3Key);
        }
        if (doc.document_id !== undefined) {
            setCurrentDocumentId(doc.document_id || null);
        }
        if (doc.version !== undefined) {
            setCurrentVersion(typeof doc.version === 'number' ? doc.version : null);
        }

        const nextPreviewBlocks = normalizeDocxPreviewBlocks(doc.preview_blocks);
        const nextPreviewSheets = normalizeXlsxPreviewSheets(doc.preview_sheets);
        setDocxPreviewMode(doc.preview_mode ?? null);
        setDocxPreviewBlocks(nextPreviewBlocks);
        setEditDocxPreviewBlocks(cloneDocxPreviewBlocks(nextPreviewBlocks));
        setXlsxPreviewSheets(nextPreviewSheets);
        setEditXlsxPreviewSheets(cloneXlsxPreviewSheets(nextPreviewSheets));
        setActiveXlsxSheetId(nextPreviewSheets[0]?.sheet_id || null);

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
            file_type: doc.file_type,
            content_type: doc.content_type,
            is_binary: doc.is_binary,
            download_url: doc.download_url,
            s3_key: doc.s3_key,
            status: doc.status,
            version: doc.version,
            generated_at: doc.generated_at,
            preview_mode: doc.preview_mode,
            preview_blocks: nextPreviewBlocks,
            preview_sheets: nextPreviewSheets,
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

            if (data.is_binary) {
                setDocumentTitle(data.title || doc.title || 'Untitled Document');
                setDocumentType(data.document_type || doc.document_type || '');
                setPackageId(data.package_id || doc.package_id);
                setFileType(data.file_type || '');
                setContentType(data.content_type || '');
                setIsBinaryDocument(true);
                setDownloadUrl(data.download_url || null);
                setS3Key(data.s3_key || doc.s3_key || rawId);
                setCurrentDocumentId(data.document_id || doc.document_id || rawId);
                setCurrentVersion(typeof data.version === 'number' ? data.version : null);
                const nextPreviewBlocks = normalizeDocxPreviewBlocks(data.preview_blocks);
                const nextPreviewSheets = normalizeXlsxPreviewSheets(data.preview_sheets);
                setDocxPreviewMode(data.preview_mode ?? null);
                setDocxPreviewBlocks(nextPreviewBlocks);
                setEditDocxPreviewBlocks(cloneDocxPreviewBlocks(nextPreviewBlocks));
                setXlsxPreviewSheets(nextPreviewSheets);
                setEditXlsxPreviewSheets(cloneXlsxPreviewSheets(nextPreviewSheets));
                setActiveXlsxSheetId(nextPreviewSheets[0]?.sheet_id || null);
                setDocumentContent(data.content || '');
                setEditContent(data.content || '');
                return;
            }

            if (typeof data.content === 'string' && data.content.length > 0) {
                applyDocumentUpdate({
                    ...doc,
                    title: data.title || doc.title,
                    document_type: data.document_type || doc.document_type,
                    package_id: data.package_id || doc.package_id,
                    document_id: data.document_id || doc.document_id || rawId,
                    s3_key: data.s3_key || doc.s3_key || rawId,
                    file_type: data.file_type || doc.file_type,
                    content_type: data.content_type || doc.content_type,
                    is_binary: data.is_binary,
                    download_url: data.download_url,
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
        let loadedFromCache = false;

        // Try sessionStorage first (instant load from chat navigation)
        // Double-lookup: new keys use plain encodeURIComponent, old keys had dots as %2E
        try {
            const stored = sessionStorage.getItem(`doc-content-${id}`)
                || sessionStorage.getItem(`doc-content-${encodeURIComponent(decodedId).replace(/\./g, '%2E')}`);
            if (stored) {
                const doc: DocumentInfo = JSON.parse(stored);
                setDocumentTitle(doc.title);
                setDocumentType(doc.document_type);
                setPackageId(doc.package_id);
                setFileType(doc.file_type || '');
                setContentType(doc.content_type || '');
                setIsBinaryDocument(Boolean(doc.is_binary));
                setDownloadUrl(doc.download_url || null);
                setS3Key(doc.s3_key || doc.document_id || null);
                setCurrentDocumentId(doc.document_id || null);
                setCurrentVersion(typeof doc.version === 'number' ? doc.version : null);
                const nextPreviewBlocks = normalizeDocxPreviewBlocks(doc.preview_blocks);
                const nextPreviewSheets = normalizeXlsxPreviewSheets(doc.preview_sheets);
                setDocxPreviewMode(doc.preview_mode ?? null);
                setDocxPreviewBlocks(nextPreviewBlocks);
                setEditDocxPreviewBlocks(cloneDocxPreviewBlocks(nextPreviewBlocks));
                setXlsxPreviewSheets(nextPreviewSheets);
                setEditXlsxPreviewSheets(cloneXlsxPreviewSheets(nextPreviewSheets));
                setActiveXlsxSheetId(nextPreviewSheets[0]?.sheet_id || null);
                if (doc.content) {
                    setDocumentContent(doc.content);
                    setEditContent(doc.content);
                    setIsLoading(false);
                    loadedFromCache = true;
                    // Don't return — still fetch fresh content from S3 in background
                }
            }
        } catch {
            // sessionStorage unavailable or parse error
        }

        // Try localStorage (handles navigation from Documents page)
        if (!loadedFromCache) {
            const stored2 = getGeneratedDocument(id);
            if (stored2?.content) {
                setDocumentTitle(stored2.title);
                setDocumentType(stored2.document_type);
                setPackageId(stored2.package_id);
                setFileType(stored2.file_type || '');
                setContentType(stored2.content_type || '');
                setIsBinaryDocument(Boolean(stored2.is_binary));
                setDownloadUrl(stored2.download_url || null);
                setS3Key(stored2.s3_key || stored2.id || null);
                setCurrentDocumentId(stored2.document_id || stored2.id || null);
                setCurrentVersion(typeof stored2.version === 'number' ? stored2.version : null);
                const nextPreviewBlocks = normalizeDocxPreviewBlocks(stored2.preview_blocks);
                const nextPreviewSheets = normalizeXlsxPreviewSheets(stored2.preview_sheets);
                setDocxPreviewMode(stored2.preview_mode ?? null);
                setDocxPreviewBlocks(nextPreviewBlocks);
                setEditDocxPreviewBlocks(cloneDocxPreviewBlocks(nextPreviewBlocks));
                setXlsxPreviewSheets(nextPreviewSheets);
                setEditXlsxPreviewSheets(cloneXlsxPreviewSheets(nextPreviewSheets));
                setActiveXlsxSheetId(nextPreviewSheets[0]?.sheet_id || null);
                setDocumentContent(stored2.content);
                setEditContent(stored2.content);
                setIsLoading(false);
                loadedFromCache = true;
                // Don't return — still fetch fresh content from S3 in background
            }
        }

        // Always fetch from API to get fresh content (even if we loaded from cache)
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
                    setFileType(data.file_type || '');
                    setContentType(data.content_type || '');
                    setIsBinaryDocument(Boolean(data.is_binary));
                    setDownloadUrl(data.download_url || null);
                    setS3Key(data.s3_key || data.key || data.document_id || null);
                    setCurrentDocumentId(data.document_id || data.key || null);
                    setCurrentVersion(typeof data.version === 'number' ? data.version : null);
                    const nextPreviewBlocks = normalizeDocxPreviewBlocks(data.preview_blocks);
                    const nextPreviewSheets = normalizeXlsxPreviewSheets(data.preview_sheets);
                    setDocxPreviewMode(data.preview_mode ?? null);
                    setDocxPreviewBlocks(nextPreviewBlocks);
                    setEditDocxPreviewBlocks(cloneDocxPreviewBlocks(nextPreviewBlocks));
                    setXlsxPreviewSheets(nextPreviewSheets);
                    setEditXlsxPreviewSheets(cloneXlsxPreviewSheets(nextPreviewSheets));
                    setActiveXlsxSheetId(nextPreviewSheets[0]?.sheet_id || null);
                    setDocumentContent(data.content || '');
                    setEditContent(data.content || '');
                    setIsLoading(false);
                    return;
                }
            } catch {
                // Backend unavailable — try template fallback only if no cache
            }

            // If we already loaded from cache, don't fall back to templates
            if (loadedFromCache) {
                return;
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
                        setDocxPreviewMode(null);
                        setDocxPreviewBlocks([]);
                        setEditDocxPreviewBlocks([]);
                        setXlsxPreviewSheets([]);
                        setEditXlsxPreviewSheets([]);
                        setActiveXlsxSheetId(null);
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
            setDocxPreviewMode(null);
            setDocxPreviewBlocks([]);
            setEditDocxPreviewBlocks([]);
            setXlsxPreviewSheets([]);
            setEditXlsxPreviewSheets([]);
            setActiveXlsxSheetId(null);
            setDocumentContent('*Unable to load document content. The document may have been created in this session — try going back and clicking "Open Document" again.*');
            setIsLoading(false);
        }

        fetchDocument();
    }, [id, getToken]);

    useEffect(() => {
        if (!isBinaryDocument || !packageId || !documentType) {
            return;
        }

        let cancelled = false;

        const syncLatestVersion = async () => {
            try {
                const token = await getToken();
                const response = await fetch(`/api/packages/${packageId}/documents/${documentType}`, {
                    headers: token ? { Authorization: `Bearer ${token}` } : {},
                });
                if (!response.ok || cancelled) {
                    return;
                }

                const data = await response.json() as {
                    document_id?: string;
                    version?: number;
                    title?: string;
                    doc_type?: string;
                    package_id?: string;
                    s3_key?: string;
                    file_type?: string;
                };

                const nextDocumentId = data.document_id || null;
                const nextVersion = typeof data.version === 'number' ? data.version : null;
                const versionChanged = nextVersion !== null && nextVersion !== currentVersion;
                const documentChanged = Boolean(nextDocumentId && nextDocumentId !== currentDocumentId);

                if (!versionChanged && !documentChanged) {
                    return;
                }

                setDocumentTitle(data.title || documentTitle);
                setDocumentType(data.doc_type || documentType);
                setPackageId(data.package_id || packageId);
                setFileType(data.file_type || fileType);
                setDownloadUrl(null);
                setS3Key(data.s3_key || s3Key);
                setCurrentDocumentId(nextDocumentId);
                setCurrentVersion(nextVersion);
                setDocUpdated(true);
                window.setTimeout(() => setDocUpdated(false), 2000);
            } catch {
                // Best-effort poll; keep the current editor state on transient failures.
            }
        };

        void syncLatestVersion();
        const intervalId = window.setInterval(() => {
            void syncLatestVersion();
        }, 10000);

        return () => {
            cancelled = true;
            window.clearInterval(intervalId);
        };
    }, [
        currentDocumentId,
        currentVersion,
        documentTitle,
        documentType,
        fileType,
        getToken,
        packageId,
        s3Key,
        isBinaryDocument,
    ]);

    useEffect(() => {
        if (!currentBinaryDownloadTarget) return;

        let cancelled = false;

        const refreshBinaryDownloadUrl = async () => {
            try {
                const token = await getToken();
                const response = await fetch(`/api/documents/${encodeURIComponent(currentBinaryDownloadTarget)}?content=false`, {
                    headers: token ? { Authorization: `Bearer ${token}` } : {},
                });
                if (!response.ok || cancelled) {
                    return;
                }

                const data = await response.json() as { download_url?: string | null };
                if (!cancelled) {
                    setDownloadUrl(data.download_url || null);
                }
            } catch {
                // Keep the last usable URL on transient failures.
            }
        };

        void refreshBinaryDownloadUrl();

        return () => {
            cancelled = true;
        };
    }, [currentBinaryDownloadTarget, getToken]);

    // Layer 1: Immediate hydration from session context
    useEffect(() => {
        if (isBinaryDocument || isLoading || !documentContent || !sessionId || !documentType) return;
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
    }, [isBinaryDocument, isLoading]);

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
            !sessionId ||
            isBinaryDocument
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
    }, [unfilledCount, isBinaryDocument, isLoading, isStreaming, showHydrationBanner, packageId]);

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
            ? (
                isDocxDocument && isBinaryDocument
                    ? `[DOCUMENT KEY]\n${s3Key}\nThis is a DOCX source file. For targeted edits, use edit_docx_document with exact existing text from the preview in edits[].search_text and the revised text in edits[].replacement_text. For checklist toggles shown in the preview, use checkbox_edits[] with label_text and checked. If the preview shows markdown heading markers like # or ##, do not include those markers in search_text.`
                    : `[DOCUMENT KEY]\n${s3Key}\nTo update this document in place, use create_document with update_existing_key="${s3Key}" and provide the full updated content in data.content.`
            )
            : '[DOCUMENT KEY]\nNot available - document must be saved to S3 first before updates can be applied.';

        return [
            'You are assisting with edits to an acquisition document in EAGLE.',
            '[DOCUMENT CONTEXT]',
            `Title: ${documentTitle || 'Untitled Document'}`,
            `Type: ${documentType || 'unknown'}`,
            `File Type: ${fileType || 'unknown'}`,
            boundedDoc ? `Current Content Excerpt:\n${boundedDoc}` : 'Current Content Excerpt: [empty]',
            s3KeyInfo,
            '[ORIGIN SESSION CONTEXT]',
            boundedSession || 'No origin session context was found for this document.',
            '[USER REQUEST]',
            userRequest,
            isDocxDocument && isBinaryDocument
                ? 'Instruction: If the user requests changes to this DOCX, use edit_docx_document for targeted replacements so the Word formatting is preserved. Use checkbox_edits for checkbox toggles instead of text replacement.'
                : 'Instruction: If the user requests substantive edits or section completion, use create_document with update_existing_key to update the document in place.',
        ].join('\n\n');
    }, [documentContent, documentTitle, documentType, fileType, isBinaryDocument, isDocxDocument, loadSession, sessionId, s3Key]);

    const handleSendMessage = async () => {
        if (!chatInput.trim() || isStreaming || !canUseAiDocAssistant) return;

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
    const displayedXlsxSheets = isEditing ? editXlsxPreviewSheets : xlsxPreviewSheets;
    const activeXlsxSheet = displayedXlsxSheets.find((sheet) => sheet.sheet_id === activeXlsxSheetId) || displayedXlsxSheets[0] || null;
    const docxEditOutline = useMemo(
        () => editDocxPreviewBlocks
            .filter((block) => block.kind === 'heading')
            .map((block) => ({
                block_id: block.block_id,
                level: block.level || 1,
                text: block.text.trim() || 'Untitled section',
            })),
        [editDocxPreviewBlocks],
    );

    const updateDocxPreviewBlock = useCallback((blockId: string, patch: Partial<DocxPreviewBlock>) => {
        setEditDocxPreviewBlocks((prev) => prev.map((block) => (
            block.block_id === blockId ? { ...block, ...patch } : block
        )));
    }, []);

    const scrollToDocxBlock = useCallback((blockId: string) => {
        docxBlockRefs.current[blockId]?.scrollIntoView({
            behavior: 'smooth',
            block: 'center',
        });
    }, []);

    const updateXlsxPreviewCell = useCallback((sheetId: string, cellRef: string, value: string) => {
        setEditXlsxPreviewSheets((prev) => prev.map((sheet) => {
            if (sheet.sheet_id !== sheetId) return sheet;
            return {
                ...sheet,
                rows: sheet.rows.map((row) => ({
                    ...row,
                    cells: row.cells.map((cell) => (
                        cell.cell_ref === cellRef
                            ? { ...cell, value, display_value: value }
                            : cell
                    )),
                })),
            };
        }));
    }, []);

    useEffect(() => {
        if (!xlsxPreviewSheets.length) {
            setActiveXlsxSheetId(null);
            return;
        }
        const exists = xlsxPreviewSheets.some((sheet) => sheet.sheet_id === activeXlsxSheetId);
        if (!exists) {
            setActiveXlsxSheetId(xlsxPreviewSheets[0].sheet_id);
        }
    }, [activeXlsxSheetId, xlsxPreviewSheets]);

    const handleToggleEdit = () => {
        if (isBinaryDocument) {
            if (isDocxDocument) {
                if (!canEditDocxPreview) return;
                setEditDocxPreviewBlocks(cloneDocxPreviewBlocks(docxPreviewBlocks));
                setIsEditing(!isEditing);
                return;
            }
            if (isXlsxDocument) {
                if (!canEditXlsxPreview) return;
                setEditXlsxPreviewSheets(cloneXlsxPreviewSheets(xlsxPreviewSheets));
                setIsEditing(!isEditing);
                return;
            }
            return;
        }
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
            const requestUrl = isBinaryDocument && isDocxDocument
                ? `/api/documents/${encodeURIComponent(s3Key)}/docx-edit`
                : isBinaryDocument && isXlsxDocument
                    ? `/api/documents/${encodeURIComponent(s3Key)}/xlsx-edit`
                    : `/api/documents/${encodeURIComponent(s3Key)}`;
            const requestBody = isBinaryDocument && isDocxDocument
                ? {
                    preview_blocks: editDocxPreviewBlocks,
                    preview_mode: docxPreviewMode || 'docx_blocks',
                    change_source: 'user_edit',
                }
                : isBinaryDocument && isXlsxDocument
                    ? {
                        cell_edits: collectXlsxCellEdits(xlsxPreviewSheets, editXlsxPreviewSheets),
                        change_source: 'user_edit',
                    }
                : {
                    content: editContent,
                    change_source: 'user_edit',
                };
            const res = await fetch(requestUrl, {
                method: isBinaryDocument ? 'POST' : 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    ...(token ? { Authorization: `Bearer ${token}` } : {}),
                },
                body: JSON.stringify(requestBody),
            });
            if (!res.ok) {
                throw new Error(await extractResponseError(res));
            }
            const result = await res.json() as DocumentInfo & { content?: string; message?: string; key?: string };

            // Update local state with saved content
            if (isBinaryDocument && isDocxDocument) {
                const savedPreviewBlocks = normalizeDocxPreviewBlocks(result.preview_blocks);
                setDocumentContent(result.content ?? documentContent);
                setDocxPreviewMode(result.preview_mode ?? docxPreviewMode ?? null);
                setDocxPreviewBlocks(savedPreviewBlocks);
                setEditDocxPreviewBlocks(cloneDocxPreviewBlocks(savedPreviewBlocks));
                setCurrentDocumentId(result.document_id || currentDocumentId);
                setCurrentVersion(typeof result.version === 'number' ? result.version : currentVersion);
                setDownloadUrl(null);
                setS3Key(result.s3_key || result.key || s3Key);
                setIsEditing(false);
            } else if (isBinaryDocument && isXlsxDocument) {
                const savedPreviewSheets = normalizeXlsxPreviewSheets(result.preview_sheets);
                setDocumentContent(result.content ?? documentContent);
                setXlsxPreviewSheets(savedPreviewSheets);
                setEditXlsxPreviewSheets(cloneXlsxPreviewSheets(savedPreviewSheets));
                setActiveXlsxSheetId(savedPreviewSheets[0]?.sheet_id || null);
                setCurrentDocumentId(result.document_id || currentDocumentId);
                setCurrentVersion(typeof result.version === 'number' ? result.version : currentVersion);
                setDownloadUrl(null);
                setS3Key(result.s3_key || result.key || s3Key);
                setIsEditing(false);
            } else {
                setDocumentContent(editContent);
            }
            setDocUpdated(true);
            setTimeout(() => setDocUpdated(false), 2000);

            // Clear sessionStorage cache so reload fetches fresh content
            try {
                sessionStorage.removeItem(`doc-content-${id}`);
            } catch {
                // Ignore sessionStorage errors
            }

            // Clear localStorage cache (eagle_generated_docs) so reload fetches fresh from S3
            // Must match the fuzzy lookup logic in getGeneratedDocument()
            try {
                const docsKey = 'eagle_generated_docs';
                const stored = localStorage.getItem(docsKey);
                if (stored) {
                    const docs = JSON.parse(stored) as Record<string, { id?: string; s3_key?: string; title?: string }>;
                    const decodedId = decodeURIComponent(id);
                    const normalizedId = encodeURIComponent(decodedId);
                    const s3KeyDecoded = s3Key ? decodeURIComponent(s3Key) : null;
                    let changed = false;

                    // Delete by direct key lookup
                    if (docs[id]) { delete docs[id]; changed = true; }
                    if (docs[normalizedId]) { delete docs[normalizedId]; changed = true; }
                    if (s3Key && docs[encodeURIComponent(s3Key)]) {
                        delete docs[encodeURIComponent(s3Key)];
                        changed = true;
                    }

                    // Also delete any fuzzy matches (same logic as getGeneratedDocument)
                    for (const key of Object.keys(docs)) {
                        const doc = docs[key];
                        if (
                            doc.id === id ||
                            doc.id === normalizedId ||
                            doc.s3_key === decodedId ||
                            doc.s3_key === s3KeyDecoded ||
                            doc.title === decodedId
                        ) {
                            delete docs[key];
                            changed = true;
                        }
                    }

                    if (changed) {
                        localStorage.setItem(docsKey, JSON.stringify(docs));
                    }
                }
            } catch {
                // Ignore localStorage errors
            }
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

            // Base64-encode content to prevent NCI WAF/proxy from
            // blocking POST bodies that contain legal text patterns.
            const res = await fetch('/api/documents', {
                method: 'POST',
                headers,
                body: JSON.stringify({
                    content_b64: btoa(unescape(encodeURIComponent(documentContent))),
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

                            {/* Download controls */}
                            <div className="relative">
                                {isBinaryDocument ? (
                                    downloadUrl ? (
                                        <a
                                            href={downloadUrl}
                                            target="_blank"
                                            rel="noreferrer"
                                            className="flex items-center gap-2 px-4 py-2 border border-gray-200 bg-white text-gray-700 rounded-xl text-sm font-medium hover:bg-gray-50 transition-colors"
                                        >
                                            <Download className="w-4 h-4" />
                                            Download Current
                                        </a>
                                    ) : (
                                        <button
                                            disabled
                                            className="flex items-center gap-2 px-4 py-2 border border-gray-200 bg-white text-gray-500 rounded-xl text-sm font-medium"
                                        >
                                            <RefreshCw className="w-4 h-4 animate-spin" />
                                            Preparing Download
                                        </button>
                                    )
                                ) : (
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
                                )}
                                {showDownloadMenu && !isBinaryDocument && (
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
                                disabled={isBinaryDocument && !canEditDocxPreview && !canEditXlsxPreview}
                                title={
                                    isBinaryDocument && !canEditDocxPreview && !canEditXlsxPreview
                                        ? 'Direct editing is unavailable for this binary document type.'
                                        : isBinaryDocument
                                            ? (
                                                isDocxDocument
                                                    ? 'Edit this structured DOCX preview. Changes will be applied back to the source document with python-docx.'
                                                    : 'Edit this structured spreadsheet preview. Changes will be applied back to the workbook with openpyxl.'
                                            )
                                            : undefined
                                }
                                className="flex items-center gap-2 px-4 py-2 bg-[#003366] text-white rounded-xl text-sm font-medium hover:bg-[#004488] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
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
                                    disabled={
                                        isSaving
                                        || !s3Key
                                        || (isBinaryDocument && isDocxDocument
                                            ? !hasDocxPreviewChanges
                                            : isBinaryDocument && isXlsxDocument
                                                ? !hasXlsxPreviewChanges
                                            : editContent === documentContent)
                                    }
                                    className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-xl text-sm font-medium hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                                    title={
                                        !s3Key
                                            ? 'Document must be saved to S3 first'
                                            : isBinaryDocument && isDocxDocument
                                                ? (hasDocxPreviewChanges ? 'Save DOCX preview edits to S3' : 'No changes to save')
                                                : isBinaryDocument && isXlsxDocument
                                                    ? (hasXlsxPreviewChanges ? 'Save spreadsheet edits to S3' : 'No changes to save')
                                                : (editContent === documentContent ? 'No changes to save' : 'Save to S3')
                                    }
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
                            <div className={`${isBinaryDocument && isDocxDocument && isEditing ? 'max-w-6xl' : 'max-w-3xl'} mx-auto`}>
                                {isBinaryDocument && isDocxDocument ? (
                                    <div className="space-y-6">
                                        <div className="rounded-2xl border border-blue-200 bg-blue-50 p-6 text-sm text-blue-950">
                                            <div className="flex items-center gap-2 text-base font-semibold">
                                                <FileText className="h-5 w-5" />
                                                DOCX preview
                                            </div>
                                            <p className="mt-3 leading-6">
                                                This Word document remains stored as a native `.docx` file. Browser edits work on a structured preview and save back through `python-docx` so the source file stays native.
                                            </p>
                                            <p className="mt-3 leading-6">
                                                Use `Edit` for direct paragraph and checkbox updates here, or use the assistant on the right for targeted DOCX revisions. Complex layout and styling still remain in the native Word file.
                                            </p>
                                            {downloadUrl && (
                                                <a
                                                    href={downloadUrl}
                                                    target="_blank"
                                                    rel="noreferrer"
                                                    className="mt-4 inline-flex items-center gap-2 rounded-xl bg-[#003366] px-4 py-2 text-sm font-medium text-white hover:bg-[#004488]"
                                                >
                                                    <Download className="h-4 w-4" />
                                                    Open current file
                                                </a>
                                            )}
                                        </div>
                                        {isEditing ? (
                                            <div className="lg:grid lg:grid-cols-[220px_minmax(0,1fr)] lg:gap-6">
                                                <aside className="hidden lg:block">
                                                    <div className="rounded-2xl border border-[#d8e1ef] bg-[#f7f9fc] p-4 shadow-sm">
                                                        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#5d6b82]">
                                                            Outline
                                                        </p>
                                                        <p className="mt-2 text-sm text-[#44546a]">
                                                            {editDocxPreviewBlocks.length} editable blocks
                                                        </p>
                                                        {hasDocxPreviewChanges && (
                                                            <div className="mt-3 rounded-full bg-amber-100 px-3 py-1 text-xs font-medium text-amber-800">
                                                                Unsaved changes
                                                            </div>
                                                        )}
                                                        <div className="mt-4 space-y-1.5">
                                                            {docxEditOutline.map((heading) => (
                                                                <button
                                                                    key={heading.block_id}
                                                                    onClick={() => scrollToDocxBlock(heading.block_id)}
                                                                    className="block w-full rounded-xl px-3 py-2 text-left text-sm text-[#334155] hover:bg-white"
                                                                    style={{ paddingLeft: `${12 + (heading.level - 1) * 12}px` }}
                                                                >
                                                                    {heading.text}
                                                                </button>
                                                            ))}
                                                        </div>
                                                    </div>
                                                </aside>
                                                <div className="rounded-[28px] border border-[#d9e2ec] bg-[#fcfbf8] shadow-[0_18px_40px_rgba(15,23,42,0.06)]">
                                                    <div className="rounded-t-[28px] border-b border-[#e4e7ec] bg-white px-6 py-4">
                                                        <div className="flex items-center justify-between gap-4">
                                                            <div>
                                                                <p className="text-sm font-semibold text-[#102a43]">
                                                                    Structured DOCX editor
                                                                </p>
                                                                <p className="mt-1 text-sm text-[#5d6b82]">
                                                                    Edit paragraphs and headings directly. Changes are saved back to the source document with formatting-preserving backend ops.
                                                                </p>
                                                            </div>
                                                            <div className="rounded-full border border-[#d8e1ef] bg-[#f8fafc] px-3 py-1 text-xs font-medium text-[#486581]">
                                                                {docxEditOutline.length} sections
                                                            </div>
                                                        </div>
                                                    </div>
                                                    <div className="space-y-5 p-5 md:p-8">
                                                        {editDocxPreviewBlocks.map((block) => (
                                                            <div
                                                                key={block.block_id}
                                                                ref={(element) => { docxBlockRefs.current[block.block_id] = element; }}
                                                                className={`rounded-2xl border px-5 py-4 transition-colors ${
                                                                    block.kind === 'heading'
                                                                        ? 'border-[#cdd7e1] bg-white shadow-sm'
                                                                        : block.kind === 'checkbox'
                                                                            ? 'border-[#d9e2ec] bg-[#fffefb]'
                                                                            : 'border-[#e5e7eb] bg-white'
                                                                }`}
                                                            >
                                                                {block.kind === 'checkbox' ? (
                                                                    <div className="flex items-start gap-3">
                                                                        <input
                                                                            type="checkbox"
                                                                            checked={Boolean(block.checked)}
                                                                            onChange={(e) => updateDocxPreviewBlock(block.block_id, { checked: e.target.checked })}
                                                                            className="mt-1 h-4 w-4 rounded border-gray-300 text-[#003366] focus:ring-[#003366]"
                                                                        />
                                                                        <div className="min-w-0 flex-1">
                                                                            <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-[#7b8794]">
                                                                                Checklist Item
                                                                            </div>
                                                                            <input
                                                                                type="text"
                                                                                value={block.text}
                                                                                onChange={(e) => updateDocxPreviewBlock(block.block_id, { text: e.target.value })}
                                                                                className="w-full border-0 bg-transparent px-0 text-base text-[#102a43] placeholder:text-[#9aa5b1] focus:outline-none"
                                                                                placeholder="Checkbox label"
                                                                            />
                                                                        </div>
                                                                    </div>
                                                                ) : (
                                                                    <>
                                                                        <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-[#7b8794]">
                                                                            {block.kind === 'heading' ? `Heading ${block.level || 1}` : 'Paragraph'}
                                                                        </div>
                                                                        <textarea
                                                                            value={block.text}
                                                                            onChange={(e) => {
                                                                                updateDocxPreviewBlock(block.block_id, { text: e.target.value });
                                                                                autoResizeTextarea(e.currentTarget);
                                                                            }}
                                                                            onInput={(e) => autoResizeTextarea(e.currentTarget)}
                                                                            ref={(element) => autoResizeTextarea(element)}
                                                                            rows={1}
                                                                            className={`w-full overflow-hidden border-0 bg-transparent px-0 text-[#102a43] placeholder:text-[#9aa5b1] focus:outline-none resize-none ${
                                                                                block.kind === 'heading'
                                                                                    ? 'text-[1.35rem] font-semibold leading-tight'
                                                                                    : 'text-[1.02rem] leading-8'
                                                                            }`}
                                                                            placeholder={block.kind === 'heading' ? 'Heading text' : 'Paragraph text'}
                                                                        />
                                                                    </>
                                                                )}
                                                            </div>
                                                        ))}
                                                        {editDocxPreviewBlocks.length === 0 && (
                                                            <div className="rounded-2xl border border-dashed border-gray-300 bg-gray-50 p-5 text-sm text-gray-600">
                                                                No editable preview blocks were extracted for this document.
                                                            </div>
                                                        )}
                                                    </div>
                                                </div>
                                            </div>
                                        ) : documentContent ? (
                                            <div className="prose prose-sm max-w-none">
                                                <MarkdownRenderer content={documentContent} />
                                            </div>
                                        ) : (
                                            <div className="rounded-2xl border border-gray-200 bg-gray-50 p-6 text-sm text-gray-700">
                                                Preview unavailable for this DOCX. You can still download the current file.
                                            </div>
                                        )}
                                    </div>
                                ) : isBinaryDocument && isXlsxDocument ? (
                                    <div className="space-y-6">
                                        <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-6 text-sm text-emerald-950">
                                            <div className="flex items-center gap-2 text-base font-semibold">
                                                <FileText className="h-5 w-5" />
                                                XLSX preview
                                            </div>
                                            <p className="mt-3 leading-6">
                                                This spreadsheet remains stored as a native `.xlsx` file. The pane below shows worksheet data extracted with `openpyxl` so you can review and edit input cells without leaving the browser.
                                            </p>
                                            <p className="mt-3 leading-6">
                                                Formula cells stay read-only. Changes are written back to the workbook with `openpyxl`, which preserves formulas, formatting, and sheet structure.
                                            </p>
                                            {downloadUrl && (
                                                <a
                                                    href={downloadUrl}
                                                    target="_blank"
                                                    rel="noreferrer"
                                                    className="mt-4 inline-flex items-center gap-2 rounded-xl bg-[#003366] px-4 py-2 text-sm font-medium text-white hover:bg-[#004488]"
                                                >
                                                    <Download className="h-4 w-4" />
                                                    Open current file
                                                </a>
                                            )}
                                        </div>
                                        {activeXlsxSheet ? (
                                            <div className="space-y-4 rounded-2xl border border-gray-200 bg-white p-5">
                                                <div className="flex flex-wrap gap-2">
                                                    {displayedXlsxSheets.map((sheet) => (
                                                        <button
                                                            key={sheet.sheet_id}
                                                            onClick={() => setActiveXlsxSheetId(sheet.sheet_id)}
                                                            className={`rounded-full px-3 py-1.5 text-sm font-medium transition ${
                                                                activeXlsxSheet.sheet_id === sheet.sheet_id
                                                                    ? 'bg-[#003366] text-white'
                                                                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                                                            }`}
                                                        >
                                                            {sheet.title}
                                                        </button>
                                                    ))}
                                                </div>
                                                {activeXlsxSheet.truncated && (
                                                    <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                                                        Preview truncated for large worksheet dimensions. Download the current workbook for the full view.
                                                    </div>
                                                )}
                                                <div className="overflow-x-auto rounded-xl border border-gray-200">
                                                    <table className="min-w-full border-collapse text-sm">
                                                        <thead className="bg-gray-50">
                                                            <tr>
                                                                <th className="border-b border-r border-gray-200 px-3 py-2 text-left font-semibold text-gray-600">Row</th>
                                                                {activeXlsxSheet.rows[0]?.cells.map((cell) => (
                                                                    <th
                                                                        key={cell.cell_ref}
                                                                        className="border-b border-r border-gray-200 px-3 py-2 text-left font-semibold text-gray-600"
                                                                    >
                                                                        {cell.cell_ref.replace(/\d+/g, '')}
                                                                    </th>
                                                                ))}
                                                            </tr>
                                                        </thead>
                                                        <tbody>
                                                            {activeXlsxSheet.rows.map((row) => (
                                                                <tr key={row.row_index} className="align-top">
                                                                    <td className="border-b border-r border-gray-200 bg-gray-50 px-3 py-2 font-medium text-gray-500">
                                                                        {row.row_index}
                                                                    </td>
                                                                    {row.cells.map((cell) => (
                                                                        <td
                                                                            key={cell.cell_ref}
                                                                            className={`border-b border-r border-gray-200 px-2 py-2 ${
                                                                                cell.editable ? 'bg-white' : 'bg-gray-50'
                                                                            }`}
                                                                        >
                                                                            {isEditing && cell.editable ? (
                                                                                <input
                                                                                    type="text"
                                                                                    value={cell.value}
                                                                                    onChange={(e) => updateXlsxPreviewCell(activeXlsxSheet.sheet_id, cell.cell_ref, e.target.value)}
                                                                                    className="w-full min-w-[110px] rounded-md border border-gray-200 px-2 py-1.5 text-sm text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                                                                                />
                                                                            ) : (
                                                                                <div className={`min-w-[110px] whitespace-pre-wrap break-words text-sm ${
                                                                                    cell.editable ? 'text-gray-900' : 'text-gray-500'
                                                                                }`}>
                                                                                    {cell.display_value || ''}
                                                                                </div>
                                                                            )}
                                                                        </td>
                                                                    ))}
                                                                </tr>
                                                            ))}
                                                        </tbody>
                                                    </table>
                                                </div>
                                            </div>
                                        ) : documentContent ? (
                                            <div className="prose prose-sm max-w-none">
                                                <MarkdownRenderer content={documentContent} />
                                            </div>
                                        ) : (
                                            <div className="rounded-2xl border border-gray-200 bg-gray-50 p-6 text-sm text-gray-700">
                                                Preview unavailable for this XLSX. You can still download the current file.
                                            </div>
                                        )}
                                    </div>
                                ) : isBinaryDocument ? (
                                    <div className="rounded-2xl border border-blue-200 bg-blue-50 p-6 text-sm text-blue-950">
                                        <div className="flex items-center gap-2 text-base font-semibold">
                                            <FileText className="h-5 w-5" />
                                            Native document detected
                                        </div>
                                        <p className="mt-3 leading-6">
                                            This file is stored as a native `{fileType || documentType || 'binary'}` document.
                                            Inline editing is intentionally disabled so EAGLE does not strip the document formatting.
                                        </p>
                                        <p className="mt-3 leading-6">
                                            Use the current file download and changelog on the right.
                                        </p>
                                        {downloadUrl && (
                                            <a
                                                href={downloadUrl}
                                                target="_blank"
                                                rel="noreferrer"
                                                className="mt-4 inline-flex items-center gap-2 rounded-xl bg-[#003366] px-4 py-2 text-sm font-medium text-white hover:bg-[#004488]"
                                            >
                                                <Download className="h-4 w-4" />
                                                Open current file
                                            </a>
                                        )}
                                        {contentType && (
                                            <p className="mt-4 text-xs text-blue-800">
                                                Content type: {contentType}
                                            </p>
                                        )}
                                    </div>
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

                    {/* Right Panel — Chat/Changelog */}
                    <div className="flex flex-col bg-gray-50" style={{ width: '35%' }}>
                        {/* Tab Header */}
                        <div className="px-4 py-2 bg-white border-b border-gray-200">
                            <div className="flex items-center gap-1">
                                <button
                                    onClick={() => setAssistantTab('chat')}
                                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition ${
                                        assistantTab === 'chat'
                                            ? 'bg-[#003366] text-white'
                                            : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'
                                    }`}
                                >
                                    <MessageSquare className="w-4 h-4" />
                                    Chat
                                </button>
                                <button
                                    onClick={() => setAssistantTab('changelog')}
                                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition ${
                                        assistantTab === 'changelog'
                                            ? 'bg-[#003366] text-white'
                                            : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'
                                    }`}
                                >
                                    <History className="w-4 h-4" />
                                    Changelog
                                </button>
                            </div>
                        </div>

                        {/* Chat Tab Content */}
                        {assistantTab === 'chat' && (
                            <>
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
                                                if (e.key === 'Enter' && !e.shiftKey && !isStreaming && canUseAiDocAssistant) {
                                                    e.preventDefault();
                                                    handleSendMessage();
                                                }
                                            }}
                                            placeholder={
                                                !canUseAiDocAssistant
                                                    ? 'AI editing is currently available for text documents and DOCX previews only.'
                                                    : isBinaryDocument
                                                        ? 'Ask for a targeted DOCX revision...'
                                                    : isStreaming
                                                        ? 'Waiting for response...'
                                                        : 'Ask about this document...'
                                            }
                                            disabled={isStreaming || !canUseAiDocAssistant}
                                            rows={1}
                                            className={`flex-1 resize-none px-3.5 py-2.5 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 ${
                                                (isStreaming || !canUseAiDocAssistant) ? 'opacity-50' : ''
                                            }`}
                                            style={{ maxHeight: 120 }}
                                        />
                                        <button
                                            onClick={handleSendMessage}
                                            disabled={!chatInput.trim() || isStreaming || !canUseAiDocAssistant}
                                            className="px-3.5 py-2.5 bg-[#003366] text-white rounded-xl hover:bg-[#004488] disabled:opacity-30 transition-colors"
                                        >
                                            <Send className="w-4 h-4" />
                                        </button>
                                    </div>
                                </div>
                            </>
                        )}

                        {/* Changelog Tab Content */}
                        {assistantTab === 'changelog' && (
                            <DocumentChangelogPanel
                                packageId={packageId || urlPackageInfo.packageId}
                                documentType={documentType || urlPackageInfo.docType}
                                documentKey={s3Key || decodeURIComponent(id)}
                            />
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
