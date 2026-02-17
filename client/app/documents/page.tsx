'use client';

import { useState, useEffect, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { Plus, Search, Filter, FileText, Eye, Download, Edit2, Clock, Copy } from 'lucide-react';
import AuthGuard from '@/components/auth/auth-guard';
import TopNav from '@/components/layout/top-nav';
import PageHeader from '@/components/layout/page-header';
import Badge from '@/components/ui/badge';
import Modal from '@/components/ui/modal';
import { Tabs } from '@/components/ui/tabs';
import MarkdownRenderer from '@/components/ui/markdown-renderer';
import {
  MOCK_DOCUMENTS,
  MOCK_DOCUMENT_TEMPLATES,
  getDocumentStatusColor,
  formatDate,
} from '@/lib/mock-data';
import { getGeneratedDocuments, StoredDocument } from '@/lib/document-store';
import { Document, DocumentTemplate, DocumentType, DocumentStatus } from '@/types/schema';

const documentTypeLabels: Record<DocumentType, string> = {
  sow: 'Statement of Work',
  igce: 'Cost Estimate (IGCE)',
  market_research: 'Market Research',
  acquisition_plan: 'Acquisition Plan',
  justification: 'Justification',
  funding_doc: 'Funding Document',
};

const documentTypeIcons: Record<DocumentType, string> = {
  sow: 'S',
  igce: 'I',
  market_research: 'M',
  acquisition_plan: 'A',
  justification: 'J',
  funding_doc: 'F',
};

/** Convert a StoredDocument from localStorage into the Document shape used by the UI. */
function storedToDocument(sd: StoredDocument): Document {
  return {
    id: sd.id,
    workflow_id: sd.session_id,
    document_type: sd.document_type,
    title: sd.title,
    status: sd.status,
    content: sd.content,
    version: sd.version,
    created_at: sd.created_at,
    updated_at: sd.updated_at,
  };
}

export default function DocumentsPage() {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedDocument, setSelectedDocument] = useState<Document | null>(null);
  const [showNewModal, setShowNewModal] = useState(false);
  const [showTemplatesModal, setShowTemplatesModal] = useState(false);
  const [localDocs, setLocalDocs] = useState<Document[]>([]);

  // Load localStorage docs on mount
  useEffect(() => {
    setLocalDocs(getGeneratedDocuments().map(storedToDocument));
  }, []);

  const allDocuments = useMemo(() => {
    return [...localDocs, ...MOCK_DOCUMENTS];
  }, [localDocs]);

  const statusTabs = useMemo(() => [
    { id: 'all', label: 'All Documents', badge: allDocuments.length },
    { id: 'not_started', label: 'Not Started', badge: allDocuments.filter(d => d.status === 'not_started').length },
    { id: 'in_progress', label: 'In Progress', badge: allDocuments.filter(d => d.status === 'in_progress').length },
    { id: 'draft', label: 'Draft', badge: allDocuments.filter(d => d.status === 'draft').length },
    { id: 'approved', label: 'Approved', badge: allDocuments.filter(d => d.status === 'approved').length },
  ], [allDocuments]);

  const filteredDocuments = allDocuments.filter(d => {
    const matchesSearch = d.title.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesStatus = activeTab === 'all' || d.status === activeTab;
    return matchesSearch && matchesStatus;
  });

  const handleDocumentClick = (doc: Document) => {
    // For localStorage docs, populate sessionStorage so the viewer can load them
    const isLocal = localDocs.some((ld) => ld.id === doc.id);
    if (isLocal && doc.content) {
      try {
        sessionStorage.setItem(`doc-content-${doc.id}`, JSON.stringify({
          title: doc.title,
          document_type: doc.document_type,
          content: doc.content,
        }));
      } catch {
        // sessionStorage unavailable
      }
    }
    setSelectedDocument(doc);
  };

  return (
    <AuthGuard>
    <div className="flex flex-col h-screen bg-gray-50">
      <TopNav />

      <main className="flex-1 overflow-y-auto">
        <div className="p-8">
          <PageHeader
            title="Documents"
            description="Create and manage acquisition documents"
            actions={
              <div className="flex gap-3">
                <button
                  onClick={() => setShowTemplatesModal(true)}
                  className="flex items-center gap-2 px-4 py-2.5 bg-white border border-gray-200 text-gray-700 rounded-xl font-medium hover:bg-gray-50 transition-colors"
                >
                  <FileText className="w-4 h-4" />
                  Templates
                </button>
                <button
                  onClick={() => setShowNewModal(true)}
                  className="flex items-center gap-2 px-4 py-2.5 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700 transition-colors shadow-md shadow-blue-200"
                >
                  <Plus className="w-4 h-4" />
                  New Document
                </button>
              </div>
            }
          />

          {/* Search */}
          <div className="mb-6 flex items-center gap-4">
            <div className="relative flex-1 max-w-md">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                placeholder="Search documents..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-10 pr-4 py-2.5 bg-white border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
              />
            </div>
            <button className="flex items-center gap-2 px-4 py-2.5 bg-white border border-gray-200 rounded-xl text-sm text-gray-600 hover:bg-gray-50">
              <Filter className="w-4 h-4" />
              Filter by Type
            </button>
          </div>

          {/* Status Tabs */}
          <div className="mb-6">
            <Tabs tabs={statusTabs} activeTab={activeTab} onChange={setActiveTab} variant="pills" />
          </div>

          {/* Documents List */}
          <div className="space-y-3">
            {filteredDocuments.map((doc) => (
              <div
                key={doc.id}
                className="bg-white rounded-xl border border-gray-200 p-4 hover:border-blue-300 hover:shadow-md transition-all cursor-pointer group"
                onClick={() => handleDocumentClick(doc)}
              >
                <div className="flex items-center gap-4">
                  {/* Icon */}
                  <div className={`w-12 h-12 rounded-xl flex items-center justify-center text-white font-bold ${
                    doc.document_type === 'sow' ? 'bg-blue-500' :
                    doc.document_type === 'igce' ? 'bg-green-500' :
                    doc.document_type === 'market_research' ? 'bg-purple-500' :
                    doc.document_type === 'justification' ? 'bg-amber-500' :
                    'bg-gray-500'
                  }`}>
                    {documentTypeIcons[doc.document_type] || 'D'}
                  </div>

                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="font-semibold text-gray-900 group-hover:text-blue-600 transition-colors truncate">
                        {doc.title}
                      </h3>
                      <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full ${getDocumentStatusColor(doc.status)}`}>
                        {doc.status.replace('_', ' ')}
                      </span>
                    </div>
                    <div className="flex items-center gap-4 text-xs text-gray-500">
                      <span>{documentTypeLabels[doc.document_type]}</span>
                      <span className="flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {formatDate(doc.updated_at)}
                      </span>
                      <span>v{doc.version}</span>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button className="p-2 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors">
                      <Eye className="w-4 h-4" />
                    </button>
                    <button className="p-2 text-gray-400 hover:text-green-600 hover:bg-green-50 rounded-lg transition-colors">
                      <Edit2 className="w-4 h-4" />
                    </button>
                    <button className="p-2 text-gray-400 hover:text-purple-600 hover:bg-purple-50 rounded-lg transition-colors">
                      <Download className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {filteredDocuments.length === 0 && (
            <div className="text-center py-12">
              <FileText className="w-12 h-12 text-gray-300 mx-auto mb-4" />
              <p className="text-gray-500">No documents found.</p>
            </div>
          )}
        </div>
      </main>

      {/* Document Preview Modal */}
      <Modal
        isOpen={!!selectedDocument}
        onClose={() => setSelectedDocument(null)}
        title={selectedDocument?.title}
        size="lg"
        footer={
          <div className="flex justify-between">
            <button
              onClick={() => setSelectedDocument(null)}
              className="px-4 py-2 text-gray-600 hover:text-gray-800"
            >
              Close
            </button>
            <div className="flex gap-2">
              <button className="flex items-center gap-2 px-4 py-2 border border-gray-200 rounded-lg text-sm hover:bg-gray-50">
                <Download className="w-4 h-4" />
                Export
              </button>
              <button
                onClick={() => {
                  if (selectedDocument) {
                    router.push(`/documents/${selectedDocument.id}`);
                  }
                }}
                className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700"
              >
                <Edit2 className="w-4 h-4" />
                Edit Document
              </button>
            </div>
          </div>
        }
      >
        {selectedDocument && (
          <div className="space-y-6">
            {/* Document Metadata */}
            <div className="grid grid-cols-2 gap-4 p-4 bg-gray-50 rounded-xl">
              <div>
                <label className="text-xs text-gray-500 uppercase tracking-wide">Type</label>
                <p className="mt-1 text-sm font-medium">{documentTypeLabels[selectedDocument.document_type]}</p>
              </div>
              <div>
                <label className="text-xs text-gray-500 uppercase tracking-wide">Status</label>
                <p className="mt-1">
                  <span className={`inline-block text-xs font-bold uppercase px-2 py-1 rounded-full ${getDocumentStatusColor(selectedDocument.status)}`}>
                    {selectedDocument.status.replace('_', ' ')}
                  </span>
                </p>
              </div>
              <div>
                <label className="text-xs text-gray-500 uppercase tracking-wide">Version</label>
                <p className="mt-1 text-sm font-medium">v{selectedDocument.version}</p>
              </div>
              <div>
                <label className="text-xs text-gray-500 uppercase tracking-wide">Last Updated</label>
                <p className="mt-1 text-sm font-medium">{formatDate(selectedDocument.updated_at)}</p>
              </div>
            </div>

            {/* Document Content */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-xs text-gray-500 uppercase tracking-wide">Document Content</label>
                {selectedDocument.content && (
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(selectedDocument.content || '');
                    }}
                    className="flex items-center gap-1 px-2 py-1 text-xs text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded transition-colors"
                  >
                    <Copy className="w-3 h-3" />
                    Copy
                  </button>
                )}
              </div>
              <div className="p-6 bg-white rounded-xl border border-gray-200 max-h-[400px] overflow-y-auto">
                {selectedDocument.content ? (
                  <MarkdownRenderer content={selectedDocument.content} />
                ) : (
                  <div className="text-center py-8">
                    <FileText className="w-10 h-10 text-gray-300 mx-auto mb-3" />
                    <p className="text-gray-500 text-sm">
                      No content yet. Click &quot;Edit Document&quot; to start writing.
                    </p>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </Modal>

      {/* Templates Modal */}
      <Modal
        isOpen={showTemplatesModal}
        onClose={() => setShowTemplatesModal(false)}
        title="Document Templates"
        size="lg"
      >
        <div className="space-y-4">
          {MOCK_DOCUMENT_TEMPLATES.map((template) => (
            <div
              key={template.id}
              className="p-4 border border-gray-200 rounded-xl hover:border-blue-300 hover:bg-blue-50/50 transition-all cursor-pointer"
            >
              <div className="flex items-start justify-between mb-2">
                <div>
                  <h4 className="font-semibold text-gray-900">{template.name}</h4>
                  <p className="text-xs text-gray-500 mt-0.5">{documentTypeLabels[template.document_type]}</p>
                </div>
                {template.is_active ? (
                  <Badge variant="success" size="sm">Active</Badge>
                ) : (
                  <Badge variant="default" size="sm">Inactive</Badge>
                )}
              </div>
              <p className="text-sm text-gray-600">{template.description}</p>
            </div>
          ))}
        </div>
      </Modal>

      {/* New Document Modal */}
      <Modal
        isOpen={showNewModal}
        onClose={() => setShowNewModal(false)}
        title="Create New Document"
        size="md"
        footer={
          <div className="flex justify-end gap-3">
            <button
              onClick={() => setShowNewModal(false)}
              className="px-4 py-2 text-gray-600 hover:text-gray-800"
            >
              Cancel
            </button>
            <button className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
              Create Document
            </button>
          </div>
        }
      >
        <form className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Document Type *</label>
            <select className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 bg-white">
              <option value="">Select type...</option>
              <option value="sow">Statement of Work</option>
              <option value="igce">Cost Estimate (IGCE)</option>
              <option value="market_research">Market Research</option>
              <option value="acquisition_plan">Acquisition Plan</option>
              <option value="justification">Justification</option>
              <option value="funding_doc">Funding Document</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Title *</label>
            <input
              type="text"
              placeholder="e.g., SOW - CT Scanner Acquisition"
              className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Template</label>
            <select className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 bg-white">
              <option value="">No template (blank document)</option>
              {MOCK_DOCUMENT_TEMPLATES.filter(t => t.is_active).map((t) => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Associated Workflow</label>
            <select className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 bg-white">
              <option value="">Select workflow...</option>
              <option value="wf-001">128-Slice CT Scanner Acquisition</option>
              <option value="wf-004">Laboratory Centrifuge</option>
            </select>
          </div>
        </form>
      </Modal>
    </div>
    </AuthGuard>
  );
}
