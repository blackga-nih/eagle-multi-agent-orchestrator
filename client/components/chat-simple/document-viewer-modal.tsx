'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import { Loader2, ExternalLink, Download } from 'lucide-react';
import Modal from '@/components/ui/modal';
import MarkdownRenderer from '@/components/ui/markdown-renderer';
import { docLabel } from './checklist-panel';

interface DocumentData {
  document_id?: string;
  doc_type?: string;
  title?: string;
  version?: number;
  status?: string;
  file_type?: string;
  content?: string;
  s3_key?: string;
  created_at?: string;
  word_count?: number;
  download_url?: string;
}

interface DocumentViewerModalProps {
  isOpen: boolean;
  onClose: () => void;
  packageId: string;
  docType: string;
  docLabel: string;
  getToken: () => Promise<string | null>;
  /** All completed doc types in this package — enables tabbed navigation. */
  completedDocTypes?: string[];
}

/** Badge color per document status. */
const STATUS_STYLES: Record<string, string> = {
  draft: 'bg-amber-100 text-amber-800',
  final: 'bg-green-100 text-green-800',
  pending: 'bg-gray-100 text-gray-600',
};

/** Color palette for document type tabs. */
const TAB_COLORS: Record<string, { bg: string; border: string; text: string }> = {
  sow:                 { bg: 'bg-blue-50',    border: 'border-blue-500',   text: 'text-blue-700' },
  igce:                { bg: 'bg-emerald-50', border: 'border-emerald-500', text: 'text-emerald-700' },
  'market-research':   { bg: 'bg-violet-50',  border: 'border-violet-500', text: 'text-violet-700' },
  'acquisition-plan':  { bg: 'bg-amber-50',   border: 'border-amber-500',  text: 'text-amber-700' },
  justification:       { bg: 'bg-rose-50',    border: 'border-rose-500',   text: 'text-rose-700' },
  'd-f':               { bg: 'bg-orange-50',  border: 'border-orange-500', text: 'text-orange-700' },
  qasp:                { bg: 'bg-teal-50',    border: 'border-teal-500',   text: 'text-teal-700' },
  'source-selection-plan': { bg: 'bg-indigo-50', border: 'border-indigo-500', text: 'text-indigo-700' },
  'subcontracting-plan':   { bg: 'bg-pink-50',   border: 'border-pink-500',  text: 'text-pink-700' },
  'security-checklist':    { bg: 'bg-red-50',    border: 'border-red-500',   text: 'text-red-700' },
  'section-508':       { bg: 'bg-cyan-50',    border: 'border-cyan-500',   text: 'text-cyan-700' },
  'human-subjects':    { bg: 'bg-lime-50',    border: 'border-lime-500',   text: 'text-lime-700' },
  'sb-review':         { bg: 'bg-fuchsia-50', border: 'border-fuchsia-500', text: 'text-fuchsia-700' },
  'purchase-request':  { bg: 'bg-sky-50',     border: 'border-sky-500',    text: 'text-sky-700' },
  eval_criteria:       { bg: 'bg-yellow-50',  border: 'border-yellow-500', text: 'text-yellow-700' },
  cor_certification:   { bg: 'bg-slate-50',   border: 'border-slate-500',  text: 'text-slate-700' },
  'transmittal-memo':  { bg: 'bg-stone-50',   border: 'border-stone-500',  text: 'text-stone-700' },
};

const DEFAULT_TAB_COLOR = { bg: 'bg-gray-50', border: 'border-gray-500', text: 'text-gray-700' };

function getTabColor(docType: string) {
  return TAB_COLORS[docType] || DEFAULT_TAB_COLOR;
}

/** Shorten label for tab display. */
function shortLabel(dt: string): string {
  const full = docLabel(dt);
  // Use abbreviation in parentheses if available, e.g. "Statement of Work (SOW)" → "SOW"
  const match = full.match(/\(([^)]+)\)/);
  return match ? match[1] : full;
}

export default function DocumentViewerModal({
  isOpen,
  onClose,
  packageId,
  docType: initialDocType,
  getToken,
  completedDocTypes,
}: DocumentViewerModalProps) {
  const [activeDocType, setActiveDocType] = useState(initialDocType);
  const [docCache, setDocCache] = useState<Record<string, DocumentData>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Sync active tab when modal opens with a different doc type
  useEffect(() => {
    if (isOpen && initialDocType) {
      setActiveDocType(initialDocType);
    }
  }, [isOpen, initialDocType]);

  // Clear cache when modal closes or package changes
  useEffect(() => {
    if (!isOpen) {
      setDocCache({});
      setError(null);
    }
  }, [isOpen, packageId]);

  // Fetch document content for active tab
  useEffect(() => {
    if (!isOpen || !packageId || !activeDocType) return;
    if (docCache[activeDocType]) return; // Already cached

    setLoading(true);
    setError(null);

    const apiDocType = activeDocType.replace(/-/g, '_');

    void (async () => {
      try {
        const token = await getToken();
        const res = await fetch(
          `/api/packages/${encodeURIComponent(packageId)}/documents/${encodeURIComponent(apiDocType)}`,
          { headers: token ? { Authorization: `Bearer ${token}` } : {} },
        );
        if (!res.ok) {
          setError(`Failed to load document (${res.status})`);
          setLoading(false);
          return;
        }
        const data = await res.json();
        setDocCache((prev) => ({ ...prev, [activeDocType]: data }));
      } catch {
        setError('Network error loading document');
      } finally {
        setLoading(false);
      }
    })();
  }, [isOpen, packageId, activeDocType, docCache, getToken]);

  const doc = docCache[activeDocType] ?? null;

  const tabs = useMemo(() => {
    if (!completedDocTypes || completedDocTypes.length <= 1) return null;
    return completedDocTypes;
  }, [completedDocTypes]);

  /** Open the full /documents/[id] viewer page in a new tab. */
  const handleOpenFull = useCallback(() => {
    if (!doc) return;
    const docId = encodeURIComponent(doc.s3_key || doc.document_id || activeDocType);
    try {
      sessionStorage.setItem(`doc-content-${docId}`, JSON.stringify(doc));
    } catch {
      /* sessionStorage may be full */
    }
    window.open(`/documents/${docId}`, '_blank');
  }, [doc, activeDocType]);

  /** Download the document content as a markdown file. */
  const handleDownload = useCallback(() => {
    if (!doc?.content) return;
    const blob = new Blob([doc.content], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${doc.title || activeDocType}_v${doc.version || 1}.md`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }, [doc, activeDocType]);

  const wordCount = doc?.word_count ?? (doc?.content ? doc.content.split(/\s+/).length : 0);

  const footer = doc ? (
    <div className="flex items-center justify-between">
      <div className="text-xs text-gray-500">
        v{doc.version || 1}
        {wordCount > 0 && <> &middot; {wordCount.toLocaleString()} words</>}
        {doc.status && (
          <>
            {' '}
            &middot;{' '}
            <span
              className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium ${STATUS_STYLES[doc.status] || 'bg-gray-100 text-gray-600'}`}
            >
              {doc.status}
            </span>
          </>
        )}
      </div>
      <div className="flex gap-2">
        {doc.content && (
          <button
            onClick={handleDownload}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md border border-gray-300 text-gray-700 hover:bg-gray-100 transition-colors"
          >
            <Download className="w-3.5 h-3.5" />
            Download
          </button>
        )}
        <button
          onClick={handleOpenFull}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md bg-[#003366] text-white hover:bg-[#004488] transition-colors"
        >
          <ExternalLink className="w-3.5 h-3.5" />
          Open Full Viewer
        </button>
      </div>
    </div>
  ) : undefined;

  const currentLabel = docLabel(activeDocType);

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={currentLabel} size="xxl" footer={footer}>
      {/* Document tabs — shown when multiple completed docs exist */}
      {tabs && (
        <div className="flex gap-1 overflow-x-auto pb-3 mb-3 border-b border-gray-200 -mt-1">
          {tabs.map((dt) => {
            const isActive = dt === activeDocType;
            const color = getTabColor(dt);
            return (
              <button
                key={dt}
                onClick={() => setActiveDocType(dt)}
                className={`shrink-0 px-3 py-1.5 rounded-md text-xs font-medium border-b-2 transition-all ${
                  isActive
                    ? `${color.bg} ${color.border} ${color.text} shadow-sm`
                    : 'bg-white border-transparent text-gray-500 hover:text-gray-700 hover:bg-gray-50'
                }`}
              >
                {shortLabel(dt)}
                {docCache[dt] && (
                  <span className="ml-1 w-1.5 h-1.5 inline-block rounded-full bg-green-400" />
                )}
              </button>
            );
          })}
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center h-48">
          <Loader2 className="w-6 h-6 animate-spin text-[#003366]" />
          <span className="ml-2 text-sm text-gray-500">Loading document...</span>
        </div>
      )}

      {error && (
        <div className="flex flex-col items-center justify-center h-48 text-center">
          <p className="text-sm text-red-600">{error}</p>
          <button
            onClick={onClose}
            className="mt-3 text-xs text-gray-500 hover:text-gray-700 underline"
          >
            Close
          </button>
        </div>
      )}

      {!loading && !error && doc && (
        <>
          {doc.content ? (
            <MarkdownRenderer content={doc.content} />
          ) : (
            <div className="flex flex-col items-center justify-center h-48 text-center">
              <p className="text-sm text-gray-500">No preview available for this document.</p>
              <button
                onClick={handleOpenFull}
                className="mt-3 flex items-center gap-1 text-xs text-[#003366] hover:underline"
              >
                <ExternalLink className="w-3 h-3" />
                Open in full viewer
              </button>
            </div>
          )}
        </>
      )}
    </Modal>
  );
}
