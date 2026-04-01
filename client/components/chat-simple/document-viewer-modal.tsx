'use client';

import { useState, useEffect, useCallback } from 'react';
import { Loader2, ExternalLink, Download } from 'lucide-react';
import Modal from '@/components/ui/modal';
import MarkdownRenderer from '@/components/ui/markdown-renderer';

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
}

/** Badge color per document status. */
const STATUS_STYLES: Record<string, string> = {
  draft: 'bg-amber-100 text-amber-800',
  final: 'bg-green-100 text-green-800',
  pending: 'bg-gray-100 text-gray-600',
};

export default function DocumentViewerModal({
  isOpen,
  onClose,
  packageId,
  docType,
  docLabel,
  getToken,
}: DocumentViewerModalProps) {
  const [doc, setDoc] = useState<DocumentData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen || !packageId || !docType) return;
    setLoading(true);
    setError(null);
    setDoc(null);

    // Normalize hyphens to underscores for the API
    const apiDocType = docType.replace(/-/g, '_');

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
        setDoc(await res.json());
      } catch {
        setError('Network error loading document');
      } finally {
        setLoading(false);
      }
    })();
  }, [isOpen, packageId, docType, getToken]);

  /** Open the full /documents/[id] viewer page in a new tab. */
  const handleOpenFull = useCallback(() => {
    if (!doc) return;
    const docId = encodeURIComponent(doc.s3_key || doc.document_id || docType);
    try {
      sessionStorage.setItem(`doc-content-${docId}`, JSON.stringify(doc));
    } catch {
      /* sessionStorage may be full */
    }
    window.open(`/documents/${docId}`, '_blank');
  }, [doc, docType]);

  /** Download the document content as a markdown file. */
  const handleDownload = useCallback(() => {
    if (!doc?.content) return;
    const blob = new Blob([doc.content], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${doc.title || docType}_v${doc.version || 1}.md`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }, [doc, docType]);

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

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={docLabel} size="xxl" footer={footer}>
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
