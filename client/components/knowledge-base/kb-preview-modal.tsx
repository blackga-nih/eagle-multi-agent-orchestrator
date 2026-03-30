'use client';

import { useEffect, useState, useCallback } from 'react';
import { Loader2, ExternalLink } from 'lucide-react';
import Badge, { BadgeVariant } from '@/components/ui/badge';
import Modal from '@/components/ui/modal';
import CollapsibleMarkdown from '@/components/ui/collapsible-markdown';
import { useAuth } from '@/contexts/auth-context';
import type { KBDocument } from './kb-document-list';

interface KBPreviewModalProps {
  document: KBDocument | null;
  onClose: () => void;
}

const typeVariants: Record<string, BadgeVariant> = {
  regulation: 'danger',
  guidance: 'primary',
  policy: 'warning',
  template: 'success',
  memo: 'info',
  checklist: 'purple',
  reference: 'default',
};

export default function KBPreviewModal({ document: doc, onClose }: KBPreviewModalProps) {
  const { getToken } = useAuth();
  const [content, setContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [truncated, setTruncated] = useState(false);

  const fetchContent = useCallback(
    async (s3Key: string) => {
      setLoading(true);
      setContent(null);
      try {
        const token = await getToken();
        const headers: Record<string, string> = {};
        if (token) headers['Authorization'] = `Bearer ${token}`;

        const res = await fetch(`/api/knowledge-base/document/${encodeURI(s3Key)}`, { headers });
        if (!res.ok) throw new Error(`${res.status}`);
        const data = await res.json();
        setContent(data.content || '');
        setTruncated(data.truncated || false);
      } catch {
        setContent('Failed to load document content.');
      } finally {
        setLoading(false);
      }
    },
    [getToken],
  );

  useEffect(() => {
    if (doc?.s3_key) {
      fetchContent(doc.s3_key);
    } else {
      setContent(null);
    }
  }, [doc?.s3_key, fetchContent]);

  if (!doc) return null;

  return (
    <Modal isOpen={!!doc} onClose={onClose} title={doc.title || doc.document_id} size="lg">
      {/* Metadata grid */}
      <div className="grid grid-cols-2 gap-x-8 gap-y-3 mb-6 text-sm">
        <div>
          <span className="text-gray-500">Type</span>
          <div className="mt-1">
            <Badge variant={typeVariants[doc.document_type] || 'default'}>
              {doc.document_type}
            </Badge>
          </div>
        </div>
        <div>
          <span className="text-gray-500">Topic</span>
          <div className="mt-1">
            <Badge variant="info">{doc.primary_topic?.replace(/_/g, ' ') || 'N/A'}</Badge>
          </div>
        </div>
        <div>
          <span className="text-gray-500">Agent</span>
          <p className="text-gray-900">{doc.primary_agent?.replace(/-/g, ' ') || 'N/A'}</p>
        </div>
        <div>
          <span className="text-gray-500">Authority</span>
          <div className="mt-1">
            {doc.authority_level ? (
              <Badge variant="purple">{doc.authority_level}</Badge>
            ) : (
              <span className="text-gray-400">N/A</span>
            )}
          </div>
        </div>
        <div>
          <span className="text-gray-500">Words / Pages</span>
          <p className="text-gray-900">
            {doc.word_count > 0 ? doc.word_count.toLocaleString() : '?'} words
            {doc.page_count > 0 ? ` / ${doc.page_count} pages` : ''}
          </p>
        </div>
        <div>
          <span className="text-gray-500">Confidence</span>
          <p className="text-gray-900">
            {doc.confidence_score > 0 ? `${Math.round(doc.confidence_score * 100)}%` : 'N/A'}
          </p>
        </div>
      </div>

      {/* Keywords */}
      {doc.keywords && doc.keywords.length > 0 && (
        <div className="mb-6">
          <span className="text-sm text-gray-500">Keywords</span>
          <div className="flex flex-wrap gap-1.5 mt-1.5">
            {doc.keywords.map((kw) => (
              <Badge key={kw} variant="default">
                {kw}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {/* S3 key */}
      <div className="mb-6 text-xs text-gray-400 flex items-center gap-1">
        <ExternalLink className="w-3 h-3" />
        {doc.s3_key}
      </div>

      {/* Content */}
      <div className="border-t border-gray-100 pt-4">
        <h3 className="text-sm font-semibold text-gray-700 mb-3">Document Content</h3>
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
            <span className="ml-2 text-gray-500">Loading content...</span>
          </div>
        ) : content !== null ? (
          <>
            <div className="bg-white rounded-xl border border-gray-200 p-6 max-h-[400px] overflow-y-auto">
              <CollapsibleMarkdown content={content} />
            </div>
            {truncated && (
              <p className="text-xs text-amber-600 mt-2">Content truncated (50KB limit)</p>
            )}
          </>
        ) : (
          <p className="text-gray-400 text-sm">No content available</p>
        )}
      </div>
    </Modal>
  );
}
