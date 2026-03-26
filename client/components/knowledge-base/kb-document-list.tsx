'use client';

import { useState, useEffect } from 'react';
import { FileText, BookOpen, Scale, Shield, Search } from 'lucide-react';
import Badge, { BadgeVariant } from '@/components/ui/badge';

const PAGE_SIZE = 20;

export interface KBDocument {
  document_id: string;
  title: string;
  summary: string;
  document_type: string;
  primary_topic: string;
  primary_agent: string;
  authority_level: string;
  keywords: string[];
  s3_key: string;
  confidence_score: number;
  word_count: number;
  page_count: number;
  file_type: string;
  last_updated: string;
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

const topicIcons: Record<string, React.ReactNode> = {
  compliance: <Shield className="w-4 h-4" />,
  legal: <Scale className="w-4 h-4" />,
  funding: <FileText className="w-4 h-4" />,
};

interface KBDocumentListProps {
  documents: KBDocument[];
  onSelect: (doc: KBDocument) => void;
  loading?: boolean;
}

export default function KBDocumentList({ documents, onSelect, loading }: KBDocumentListProps) {
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  // Reset visible count when documents change (new search, etc.)
  useEffect(() => {
    setVisibleCount(PAGE_SIZE);
  }, [documents]);

  if (loading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="bg-white rounded-xl border border-gray-200 p-5 animate-pulse">
            <div className="h-5 bg-gray-200 rounded w-2/3 mb-3" />
            <div className="h-3 bg-gray-100 rounded w-full mb-2" />
            <div className="h-3 bg-gray-100 rounded w-3/4" />
          </div>
        ))}
      </div>
    );
  }

  if (documents.length === 0) {
    return (
      <div className="text-center py-16">
        <Search className="w-12 h-12 text-gray-300 mx-auto mb-4" />
        <p className="text-gray-500 text-lg">No documents found</p>
        <p className="text-gray-400 text-sm mt-1">Try adjusting your search or filters</p>
      </div>
    );
  }

  const visible = documents.slice(0, visibleCount);
  const remaining = documents.length - visibleCount;

  return (
    <div className="space-y-3">
      {visible.map((doc) => (
        <button
          key={doc.document_id}
          onClick={() => onSelect(doc)}
          className="w-full text-left bg-white rounded-xl border border-gray-200 p-5 hover:border-blue-300 hover:shadow-md transition-all group"
        >
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-start gap-3 min-w-0 flex-1">
              <div className="mt-0.5 p-2 rounded-lg bg-blue-50 text-blue-600 shrink-0">
                {topicIcons[doc.primary_topic] || <BookOpen className="w-4 h-4" />}
              </div>
              <div className="min-w-0">
                <h3 className="font-semibold text-gray-900 group-hover:text-blue-600 transition-colors truncate">
                  {doc.title || doc.document_id}
                </h3>
                <p className="text-sm text-gray-500 mt-1 line-clamp-2">
                  {doc.summary || 'No summary available'}
                </p>
                <div className="flex flex-wrap items-center gap-2 mt-3">
                  <Badge variant={typeVariants[doc.document_type] || 'default'}>
                    {doc.document_type}
                  </Badge>
                  {doc.primary_topic && (
                    <Badge variant="info">{doc.primary_topic.replace(/_/g, ' ')}</Badge>
                  )}
                  {doc.authority_level && (
                    <Badge variant="purple">{doc.authority_level}</Badge>
                  )}
                </div>
              </div>
            </div>
            <div className="text-right shrink-0 text-xs text-gray-400 space-y-1">
              {doc.file_type && <div>{doc.file_type.toUpperCase()}</div>}
              {doc.word_count > 0 && <div>{doc.word_count.toLocaleString()} words</div>}
              {doc.page_count > 0 && <div>{doc.page_count} pages</div>}
              {doc.confidence_score > 0 && (
                <div className="text-green-600">{Math.round(doc.confidence_score * 100)}% conf</div>
              )}
            </div>
          </div>
        </button>
      ))}

      {remaining > 0 && (
        <button
          onClick={() => setVisibleCount((c) => c + PAGE_SIZE)}
          className="w-full py-3 text-sm text-blue-600 hover:text-blue-700 font-medium bg-white rounded-xl border border-gray-200 hover:border-blue-300 transition-colors"
        >
          Load more ({Math.min(remaining, PAGE_SIZE)} of {remaining} remaining)
        </button>
      )}
    </div>
  );
}
