'use client';

import { useState, useEffect, useCallback } from 'react';
import { Search, BookOpen, FolderTree, FileType, Database } from 'lucide-react';
import AuthGuard from '@/components/auth/auth-guard';
import { useAuth } from '@/contexts/auth-context';
import TopNav from '@/components/layout/top-nav';
import PageHeader from '@/components/layout/page-header';
import { Tabs } from '@/components/ui/tabs';
import KBDocumentList, { KBDocument } from '@/components/knowledge-base/kb-document-list';
import KBFolderView from '@/components/knowledge-base/kb-folder-view';
import KBPreviewModal from '@/components/knowledge-base/kb-preview-modal';
import PluginDataSection from '@/components/knowledge-base/plugin-data-section';

interface KBStats {
  total: number;
  by_topic: Record<string, number>;
  by_type: Record<string, number>;
  by_agent: Record<string, number>;
}

const KB_TABS = [
  { id: 'all', label: 'All Documents', icon: <BookOpen className="w-4 h-4" /> },
  { id: 'by_topic', label: 'By Topic', icon: <FolderTree className="w-4 h-4" /> },
  { id: 'by_type', label: 'By Type', icon: <FileType className="w-4 h-4" /> },
  { id: 'reference', label: 'Reference Data', icon: <Database className="w-4 h-4" /> },
];

export default function KnowledgeBasePage() {
  const { getToken } = useAuth();
  const [activeTab, setActiveTab] = useState('all');
  const [documents, setDocuments] = useState<KBDocument[]>([]);
  const [stats, setStats] = useState<KBStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [selectedDocument, setSelectedDocument] = useState<KBDocument | null>(null);

  const fetchDocuments = useCallback(
    async (query?: string) => {
      setLoading(true);
      try {
        const token = await getToken();
        const headers: Record<string, string> = {};
        if (token) headers['Authorization'] = `Bearer ${token}`;

        const params = new URLSearchParams();
        if (query) params.set('query', query);

        const url = params.toString()
          ? `/api/knowledge-base?${params.toString()}`
          : '/api/knowledge-base';

        const res = await fetch(url, { headers });
        if (res.ok) {
          const data = await res.json();
          setDocuments(data.documents || []);
        }
      } catch {
        // silently fail
      } finally {
        setLoading(false);
      }
    },
    [getToken],
  );

  const fetchStats = useCallback(async () => {
    try {
      const token = await getToken();
      const headers: Record<string, string> = {};
      if (token) headers['Authorization'] = `Bearer ${token}`;

      const res = await fetch('/api/knowledge-base/stats', { headers });
      if (res.ok) {
        setStats(await res.json());
      }
    } catch {
      // silently fail
    }
  }, [getToken]);

  useEffect(() => {
    fetchDocuments();
    fetchStats();
  }, [fetchDocuments, fetchStats]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setSearchQuery(searchInput);
    fetchDocuments(searchInput || undefined);
  };

  // Update tab badges with stats
  const tabsWithBadges = KB_TABS.map((tab) => ({
    ...tab,
    badge:
      tab.id === 'all' && stats
        ? stats.total
        : tab.id === 'by_topic' && stats
          ? Object.keys(stats.by_topic).length
          : tab.id === 'by_type' && stats
            ? Object.keys(stats.by_type).length
            : undefined,
  }));

  return (
    <AuthGuard>
      <div className="flex flex-col h-screen bg-gray-50">
        <TopNav />
        <main className="flex-1 overflow-y-auto">
          <div className="max-w-6xl mx-auto p-8">
            <PageHeader
              title="Knowledge Base"
              description="Browse acquisition reference documents, regulatory guidance, and reference data"
            />

            {/* Search bar */}
            <form onSubmit={handleSearch} className="mb-6">
              <div className="relative">
                <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
                <input
                  type="text"
                  value={searchInput}
                  onChange={(e) => setSearchInput(e.target.value)}
                  placeholder="Search knowledge base (semantic search)..."
                  className="w-full pl-12 pr-4 py-3 text-sm border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white shadow-sm"
                />
                {searchInput && (
                  <button
                    type="button"
                    onClick={() => {
                      setSearchInput('');
                      setSearchQuery('');
                      fetchDocuments();
                    }}
                    className="absolute right-14 top-1/2 -translate-y-1/2 text-xs text-gray-400 hover:text-gray-600"
                  >
                    Clear
                  </button>
                )}
                <button
                  type="submit"
                  className="absolute right-2 top-1/2 -translate-y-1/2 px-4 py-1.5 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 transition-colors"
                >
                  Search
                </button>
              </div>
              {searchQuery && (
                <p className="text-sm text-gray-500 mt-2">
                  Results for &quot;{searchQuery}&quot; — {documents.length} documents
                </p>
              )}
            </form>

            {/* Tabs */}
            <div className="mb-6">
              <Tabs
                tabs={tabsWithBadges}
                activeTab={activeTab}
                onChange={setActiveTab}
                variant="pills"
              />
            </div>

            {/* Tab content */}
            {activeTab === 'all' && (
              <KBDocumentList
                documents={documents}
                onSelect={setSelectedDocument}
                loading={loading}
              />
            )}

            {activeTab === 'by_topic' && (
              <div className="bg-white rounded-xl border border-gray-200 p-4">
                <KBFolderView
                  documents={documents}
                  groupBy="primary_topic"
                  stats={stats?.by_topic}
                  onSelect={setSelectedDocument}
                />
              </div>
            )}

            {activeTab === 'by_type' && (
              <div className="bg-white rounded-xl border border-gray-200 p-4">
                <KBFolderView
                  documents={documents}
                  groupBy="document_type"
                  stats={stats?.by_type}
                  onSelect={setSelectedDocument}
                />
              </div>
            )}

            {activeTab === 'reference' && <PluginDataSection />}
          </div>
        </main>

        {/* Preview modal */}
        <KBPreviewModal document={selectedDocument} onClose={() => setSelectedDocument(null)} />
      </div>
    </AuthGuard>
  );
}
