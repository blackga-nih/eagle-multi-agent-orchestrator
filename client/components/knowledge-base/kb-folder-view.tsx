'use client';

import { useState } from 'react';
import { ChevronRight, Folder, FolderOpen } from 'lucide-react';
import Badge from '@/components/ui/badge';
import type { KBDocument } from './kb-document-list';

interface KBFolderViewProps {
  documents: KBDocument[];
  groupBy: 'primary_topic' | 'document_type' | 'primary_agent';
  stats?: Record<string, number>;
  onSelect: (doc: KBDocument) => void;
}

export default function KBFolderView({ documents, groupBy, stats, onSelect }: KBFolderViewProps) {
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());

  // Group documents by the specified field
  const groups: Record<string, KBDocument[]> = {};
  for (const doc of documents) {
    const key = (doc[groupBy] as string) || 'unknown';
    if (!groups[key]) groups[key] = [];
    groups[key].push(doc);
  }

  // Sort groups by count descending
  const sortedGroups = Object.entries(groups).sort((a, b) => b[1].length - a[1].length);

  const toggleGroup = (key: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const formatLabel = (key: string) => key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

  if (sortedGroups.length === 0) {
    return (
      <div className="text-center py-16 text-gray-400">
        No documents to display
      </div>
    );
  }

  return (
    <div className="space-y-1">
      {sortedGroups.map(([key, docs]) => {
        const isExpanded = expandedGroups.has(key);
        const count = stats?.[key] ?? docs.length;

        return (
          <div key={key}>
            <button
              onClick={() => toggleGroup(key)}
              className="w-full flex items-center gap-3 px-4 py-3 rounded-lg hover:bg-gray-50 transition-colors group"
            >
              <ChevronRight
                className={`w-4 h-4 text-gray-400 transition-transform ${isExpanded ? 'rotate-90' : ''}`}
              />
              {isExpanded ? (
                <FolderOpen className="w-5 h-5 text-blue-500" />
              ) : (
                <Folder className="w-5 h-5 text-gray-400 group-hover:text-blue-500" />
              )}
              <span className="font-medium text-gray-900">{formatLabel(key)}</span>
              <Badge variant="default">{count}</Badge>
            </button>

            {isExpanded && (
              <div className="ml-12 border-l-2 border-gray-100 pl-4 pb-2 space-y-1">
                {docs.map((doc) => (
                  <button
                    key={doc.document_id}
                    onClick={() => onSelect(doc)}
                    className="w-full text-left px-3 py-2 rounded-lg hover:bg-blue-50 transition-colors group/item"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm text-gray-700 group-hover/item:text-blue-600 truncate">
                        {doc.title || doc.document_id}
                      </span>
                      <span className="text-xs text-gray-400 shrink-0">
                        {doc.file_type?.toUpperCase()}
                      </span>
                    </div>
                    {doc.summary && (
                      <p className="text-xs text-gray-400 truncate mt-0.5">{doc.summary}</p>
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
