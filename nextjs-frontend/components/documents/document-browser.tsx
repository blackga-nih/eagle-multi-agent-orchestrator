'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  FileText,
  FolderOpen,
  Upload,
  Trash2,
  Download,
  Clock,
  Search,
  Plus,
  ChevronRight,
  File,
  RefreshCw,
  Filter,
  X,
} from 'lucide-react';

// Document metadata interface matching backend
export interface DocumentMetadata {
  document_id: string;
  user_id: string;
  document_type: string;
  title: string;
  description?: string;
  current_version: number;
  status: string;
  tags: string[];
  created_at: string;
  updated_at: string;
}

interface DocumentBrowserProps {
  userId: string;
  onSelectDocument?: (doc: DocumentMetadata) => void;
  onCreateDocument?: () => void;
  className?: string;
}

// Document type display configuration
const DOCUMENT_TYPE_CONFIG: Record<string, { icon: typeof FileText; label: string; color: string }> = {
  sow: { icon: FileText, label: 'Statement of Work', color: 'text-blue-600 bg-blue-50' },
  igce: { icon: FileText, label: 'IGCE', color: 'text-green-600 bg-green-50' },
  justification: { icon: FileText, label: 'Justification', color: 'text-purple-600 bg-purple-50' },
  market_research: { icon: FileText, label: 'Market Research', color: 'text-orange-600 bg-orange-50' },
  acquisition_plan: { icon: FileText, label: 'Acquisition Plan', color: 'text-indigo-600 bg-indigo-50' },
};

// Status badge colors
const STATUS_COLORS: Record<string, string> = {
  draft: 'bg-yellow-100 text-yellow-700',
  in_review: 'bg-blue-100 text-blue-700',
  final: 'bg-green-100 text-green-700',
  approved: 'bg-emerald-100 text-emerald-700',
  rejected: 'bg-red-100 text-red-700',
};

export default function DocumentBrowser({
  userId,
  onSelectDocument,
  onCreateDocument,
  className = '',
}: DocumentBrowserProps) {
  const [documents, setDocuments] = useState<DocumentMetadata[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterType, setFilterType] = useState<string | null>(null);
  const [filterStatus, setFilterStatus] = useState<string | null>(null);
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [showFilters, setShowFilters] = useState(false);

  // Fetch documents
  const fetchDocuments = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const params = new URLSearchParams({ user_id: userId });
      if (filterType) params.set('type', filterType);
      if (filterStatus) params.set('status', filterStatus);

      const response = await fetch(`/api/documents?${params}`);
      if (!response.ok) throw new Error('Failed to fetch documents');

      const data = await response.json();
      setDocuments(data.documents || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }, [userId, filterType, filterStatus]);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  // Handle document deletion
  const handleDelete = async (docId: string, e: React.MouseEvent) => {
    e.stopPropagation();

    if (!confirm('Are you sure you want to delete this document? This cannot be undone.')) {
      return;
    }

    try {
      const response = await fetch(`/api/documents/${docId}?user_id=${userId}`, {
        method: 'DELETE',
      });

      if (response.ok) {
        setDocuments(docs => docs.filter(d => d.document_id !== docId));
        if (selectedDocId === docId) {
          setSelectedDocId(null);
        }
      } else {
        throw new Error('Delete failed');
      }
    } catch (err) {
      console.error('Delete failed:', err);
      alert('Failed to delete document. Please try again.');
    }
  };

  // Handle document download
  const handleDownload = async (doc: DocumentMetadata, e: React.MouseEvent) => {
    e.stopPropagation();

    try {
      const response = await fetch(`/api/documents/${doc.document_id}?user_id=${userId}&content=true`);
      if (!response.ok) throw new Error('Download failed');

      const data = await response.json();
      const content = data.content || '';

      // Create blob and download
      const blob = new Blob([content], { type: 'text/markdown' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${doc.title.replace(/[^a-z0-9]/gi, '_')}_v${doc.current_version}.md`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Download failed:', err);
      alert('Failed to download document.');
    }
  };

  // Filter documents by search query
  const filteredDocuments = documents.filter(doc => {
    if (!searchQuery) return true;
    const query = searchQuery.toLowerCase();
    return (
      doc.title.toLowerCase().includes(query) ||
      doc.document_type.toLowerCase().includes(query) ||
      (doc.description?.toLowerCase().includes(query)) ||
      doc.tags.some(tag => tag.toLowerCase().includes(query))
    );
  });

  // Group documents by type
  const groupedByType = filteredDocuments.reduce((acc, doc) => {
    const type = doc.document_type;
    if (!acc[type]) acc[type] = [];
    acc[type].push(doc);
    return acc;
  }, {} as Record<string, DocumentMetadata[]>);

  // Get document type config
  const getTypeConfig = (type: string) => {
    return DOCUMENT_TYPE_CONFIG[type] || { icon: File, label: type, color: 'text-gray-600 bg-gray-50' };
  };

  // Clear filters
  const clearFilters = () => {
    setFilterType(null);
    setFilterStatus(null);
    setSearchQuery('');
  };

  const hasActiveFilters = filterType || filterStatus || searchQuery;

  return (
    <div className={`h-full flex flex-col bg-white rounded-2xl shadow-lg overflow-hidden ${className}`}>
      {/* Header */}
      <div className="p-4 border-b border-gray-100">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <FolderOpen className="w-5 h-5 text-blue-600" />
            <h2 className="font-semibold text-gray-900">My Documents</h2>
            <span className="px-2 py-0.5 rounded-full bg-gray-100 text-gray-600 text-xs">
              {documents.length}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={fetchDocuments}
              disabled={loading}
              className="p-2 hover:bg-gray-100 rounded-lg transition-colors disabled:opacity-50"
              title="Refresh"
            >
              <RefreshCw className={`w-4 h-4 text-gray-600 ${loading ? 'animate-spin' : ''}`} />
            </button>
            <button
              onClick={() => setShowFilters(!showFilters)}
              className={`p-2 rounded-lg transition-colors ${showFilters ? 'bg-blue-100 text-blue-600' : 'hover:bg-gray-100 text-gray-600'}`}
              title="Filters"
            >
              <Filter className="w-4 h-4" />
            </button>
            <button
              onClick={() => {/* TODO: Upload modal */}}
              className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
              title="Upload"
            >
              <Upload className="w-4 h-4 text-gray-600" />
            </button>
            <button
              onClick={onCreateDocument}
              className="flex items-center gap-1 px-3 py-1.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm"
            >
              <Plus className="w-4 h-4" />
              New
            </button>
          </div>
        </div>

        {/* Search */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search documents..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-4 py-2 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-3 top-1/2 -translate-y-1/2 p-0.5 hover:bg-gray-100 rounded"
            >
              <X className="w-3 h-3 text-gray-400" />
            </button>
          )}
        </div>

        {/* Filters Panel */}
        {showFilters && (
          <div className="mt-3 p-3 bg-gray-50 rounded-xl space-y-3">
            {/* Type filter */}
            <div>
              <label className="text-xs font-medium text-gray-500 mb-1.5 block">Document Type</label>
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => setFilterType(null)}
                  className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                    filterType === null
                      ? 'bg-blue-600 text-white'
                      : 'bg-white border border-gray-200 text-gray-600 hover:border-gray-300'
                  }`}
                >
                  All
                </button>
                {Object.entries(DOCUMENT_TYPE_CONFIG).map(([type, config]) => (
                  <button
                    key={type}
                    onClick={() => setFilterType(type)}
                    className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                      filterType === type
                        ? 'bg-blue-600 text-white'
                        : 'bg-white border border-gray-200 text-gray-600 hover:border-gray-300'
                    }`}
                  >
                    {config.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Status filter */}
            <div>
              <label className="text-xs font-medium text-gray-500 mb-1.5 block">Status</label>
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => setFilterStatus(null)}
                  className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                    filterStatus === null
                      ? 'bg-blue-600 text-white'
                      : 'bg-white border border-gray-200 text-gray-600 hover:border-gray-300'
                  }`}
                >
                  All
                </button>
                {Object.entries(STATUS_COLORS).map(([status]) => (
                  <button
                    key={status}
                    onClick={() => setFilterStatus(status)}
                    className={`px-3 py-1 rounded-full text-xs font-medium capitalize transition-colors ${
                      filterStatus === status
                        ? 'bg-blue-600 text-white'
                        : 'bg-white border border-gray-200 text-gray-600 hover:border-gray-300'
                    }`}
                  >
                    {status.replace('_', ' ')}
                  </button>
                ))}
              </div>
            </div>

            {hasActiveFilters && (
              <button
                onClick={clearFilters}
                className="text-xs text-blue-600 hover:text-blue-700 font-medium"
              >
                Clear all filters
              </button>
            )}
          </div>
        )}
      </div>

      {/* Document List */}
      <div className="flex-1 overflow-y-auto p-4">
        {loading && documents.length === 0 ? (
          <div className="flex items-center justify-center h-32">
            <div className="animate-spin w-6 h-6 border-2 border-blue-600 border-t-transparent rounded-full" />
          </div>
        ) : error ? (
          <div className="text-center py-8">
            <p className="text-red-500 text-sm mb-2">{error}</p>
            <button
              onClick={fetchDocuments}
              className="text-blue-600 hover:text-blue-700 text-sm font-medium"
            >
              Try again
            </button>
          </div>
        ) : filteredDocuments.length === 0 ? (
          <div className="text-center py-12">
            <FileText className="w-12 h-12 text-gray-300 mx-auto mb-3" />
            <p className="text-gray-500 text-sm mb-1">
              {hasActiveFilters ? 'No documents match your filters' : 'No documents yet'}
            </p>
            {hasActiveFilters ? (
              <button
                onClick={clearFilters}
                className="text-blue-600 hover:text-blue-700 text-sm font-medium"
              >
                Clear filters
              </button>
            ) : (
              <button
                onClick={onCreateDocument}
                className="mt-2 text-blue-600 hover:text-blue-700 text-sm font-medium"
              >
                Create your first document
              </button>
            )}
          </div>
        ) : (
          <div className="space-y-6">
            {Object.entries(groupedByType).map(([type, docs]) => {
              const config = getTypeConfig(type);

              return (
                <div key={type}>
                  <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2 flex items-center gap-2">
                    <config.icon className="w-3.5 h-3.5" />
                    {config.label}
                    <span className="text-gray-400">({docs.length})</span>
                  </h3>
                  <div className="space-y-2">
                    {docs.map((doc) => {
                      const typeConfig = getTypeConfig(doc.document_type);
                      const isSelected = selectedDocId === doc.document_id;

                      return (
                        <div
                          key={doc.document_id}
                          onClick={() => {
                            setSelectedDocId(doc.document_id);
                            onSelectDocument?.(doc);
                          }}
                          className={`p-3 rounded-xl border cursor-pointer transition-all group ${
                            isSelected
                              ? 'border-blue-500 bg-blue-50 shadow-sm'
                              : 'border-gray-100 hover:border-gray-200 hover:bg-gray-50'
                          }`}
                        >
                          <div className="flex items-start gap-3">
                            {/* Icon */}
                            <div className={`p-2 rounded-lg ${typeConfig.color}`}>
                              <typeConfig.icon className="w-4 h-4" />
                            </div>

                            {/* Content */}
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2">
                                <h4 className="font-medium text-gray-900 truncate">
                                  {doc.title}
                                </h4>
                                <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium capitalize ${
                                  STATUS_COLORS[doc.status] || 'bg-gray-100 text-gray-600'
                                }`}>
                                  {doc.status.replace('_', ' ')}
                                </span>
                              </div>
                              {doc.description && (
                                <p className="text-xs text-gray-500 truncate mt-0.5">
                                  {doc.description}
                                </p>
                              )}
                              <div className="flex items-center gap-3 mt-1.5 text-xs text-gray-400">
                                <span className="flex items-center gap-1">
                                  <Clock className="w-3 h-3" />
                                  {new Date(doc.updated_at).toLocaleDateString()}
                                </span>
                                <span>v{doc.current_version}</span>
                                {doc.tags.length > 0 && (
                                  <span className="flex items-center gap-1">
                                    {doc.tags.slice(0, 2).map(tag => (
                                      <span key={tag} className="px-1.5 py-0.5 bg-gray-100 rounded text-[10px]">
                                        {tag}
                                      </span>
                                    ))}
                                    {doc.tags.length > 2 && (
                                      <span className="text-gray-400">+{doc.tags.length - 2}</span>
                                    )}
                                  </span>
                                )}
                              </div>
                            </div>

                            {/* Actions */}
                            <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                              <button
                                onClick={(e) => handleDownload(doc, e)}
                                className="p-1.5 hover:bg-gray-100 rounded-lg transition-colors"
                                title="Download"
                              >
                                <Download className="w-4 h-4 text-gray-400" />
                              </button>
                              <button
                                onClick={(e) => handleDelete(doc.document_id, e)}
                                className="p-1.5 hover:bg-red-50 rounded-lg transition-colors"
                                title="Delete"
                              >
                                <Trash2 className="w-4 h-4 text-gray-400 hover:text-red-500" />
                              </button>
                              <ChevronRight className="w-4 h-4 text-gray-300 ml-1" />
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
