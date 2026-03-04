'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  Plus, Search, FileStack, Trash2, Eye, Code, Loader2, AlertCircle,
  RefreshCw, Package, CheckCircle2, XCircle,
} from 'lucide-react';
import AuthGuard from '@/components/auth/auth-guard';
import TopNav from '@/components/layout/top-nav';
import PageHeader from '@/components/layout/page-header';
import Badge from '@/components/ui/badge';
import Modal from '@/components/ui/modal';
import { useAuth } from '@/contexts/auth-context';
import { pluginApi, templateApi } from '@/lib/admin-api';
import type { PluginEntity, TemplateEntity } from '@/types/admin';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const docTypeLabels: Record<string, string> = {
  sow: 'Statement of Work',
  igce: 'Cost Estimate (IGCE)',
  market_research: 'Market Research',
  acquisition_plan: 'Acquisition Plan',
  justification: 'Justification',
  funding_doc: 'Funding Document',
};

const docTypeColors: Record<string, string> = {
  sow: 'bg-blue-100 text-blue-700',
  igce: 'bg-green-100 text-green-700',
  market_research: 'bg-purple-100 text-purple-700',
  acquisition_plan: 'bg-amber-100 text-amber-700',
  justification: 'bg-red-100 text-red-700',
  funding_doc: 'bg-cyan-100 text-cyan-700',
};

function formatDate(d: string): string {
  return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

// Unified card type for rendering both bundled plugin templates and custom template overrides
interface TemplateCard {
  key: string;
  name: string;
  description: string;
  docType: string;
  source: 'bundled' | 'custom';
  content: string;
  version: number;
  updatedAt: string;
  raw: PluginEntity | TemplateEntity;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function TemplatesPage() {
  const { getToken } = useAuth();

  // Data
  const [pluginTemplates, setPluginTemplates] = useState<PluginEntity[]>([]);
  const [customTemplates, setCustomTemplates] = useState<TemplateEntity[]>([]);

  // UI
  const [searchQuery, setSearchQuery] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Modals
  const [selectedCard, setSelectedCard] = useState<TemplateCard | null>(null);
  const [showPreviewModal, setShowPreviewModal] = useState(false);
  const [previewCard, setPreviewCard] = useState<TemplateCard | null>(null);
  const [showNewModal, setShowNewModal] = useState(false);

  // Edit form state
  const [editBody, setEditBody] = useState('');
  const [editDisplayName, setEditDisplayName] = useState('');

  // New template form
  const [newTpl, setNewTpl] = useState({ doc_type: '', display_name: '', template_body: '' });

  // -----------------------------------------------------------------------
  // Data fetching
  // -----------------------------------------------------------------------

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [plugins, custom] = await Promise.all([
        pluginApi.list(getToken, 'templates'),
        templateApi.list(getToken).catch(() => [] as TemplateEntity[]),
      ]);
      setPluginTemplates(plugins);
      setCustomTemplates(Array.isArray(custom) ? custom : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load templates');
    } finally {
      setIsLoading(false);
    }
  }, [getToken]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // -----------------------------------------------------------------------
  // Build unified card list
  // -----------------------------------------------------------------------

  const cards: TemplateCard[] = [
    ...pluginTemplates.map((p): TemplateCard => ({
      key: `plugin-${p.name}`,
      name: (p.metadata?.display_name as string) || p.name,
      description: (p.metadata?.description as string) || '',
      docType: (p.metadata?.doc_type as string) || p.name,
      source: 'bundled',
      content: p.content,
      version: p.version,
      updatedAt: p.updated_at,
      raw: p,
    })),
    ...customTemplates.map((t): TemplateCard => ({
      key: `custom-${t.doc_type}`,
      name: t.display_name || t.doc_type,
      description: '',
      docType: t.doc_type,
      source: 'custom',
      content: t.template_body,
      version: t.version,
      updatedAt: t.updated_at,
      raw: t,
    })),
  ];

  const q = searchQuery.toLowerCase();
  const filteredCards = cards.filter(c =>
    c.name.toLowerCase().includes(q) ||
    c.docType.toLowerCase().includes(q) ||
    c.description.toLowerCase().includes(q),
  );

  // -----------------------------------------------------------------------
  // Actions
  // -----------------------------------------------------------------------

  function openEdit(card: TemplateCard) {
    setSelectedCard(card);
    setEditBody(card.content);
    setEditDisplayName(card.name);
  }

  function openPreview(card: TemplateCard, e: React.MouseEvent) {
    e.stopPropagation();
    setPreviewCard(card);
    setShowPreviewModal(true);
  }

  async function handleSaveTemplate() {
    if (!selectedCard) return;
    setSaving(true);
    try {
      await templateApi.create(getToken, selectedCard.docType, {
        display_name: editDisplayName,
        template_body: editBody,
      });
      setSelectedCard(null);
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save template');
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteTemplate() {
    if (!selectedCard) return;
    setSaving(true);
    try {
      await templateApi.delete(getToken, selectedCard.docType);
      setSelectedCard(null);
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete template');
    } finally {
      setSaving(false);
    }
  }

  async function handleCreateTemplate() {
    setSaving(true);
    try {
      await templateApi.create(getToken, newTpl.doc_type, {
        display_name: newTpl.display_name,
        template_body: newTpl.template_body,
      });
      setShowNewModal(false);
      setNewTpl({ doc_type: '', display_name: '', template_body: '' });
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create template');
    } finally {
      setSaving(false);
    }
  }

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------

  return (
    <AuthGuard>
    <div className="flex flex-col h-screen bg-gray-50">
      <TopNav />

      <main className="flex-1 overflow-y-auto">
        <div className="p-8">
          <PageHeader
            title="Document Templates"
            description="Manage reusable document templates and overrides"
            breadcrumbs={[
              { label: 'Admin', href: '/admin' },
              { label: 'Templates' },
            ]}
            actions={
              <div className="flex items-center gap-2">
                <button
                  onClick={() => fetchData()}
                  disabled={isLoading}
                  className="flex items-center gap-2 px-4 py-2.5 bg-white border border-gray-200 text-gray-700 rounded-xl font-medium hover:bg-gray-50 transition-colors disabled:opacity-50"
                >
                  <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
                  Refresh
                </button>
                <button
                  onClick={() => setShowNewModal(true)}
                  className="flex items-center gap-2 px-4 py-2.5 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700 transition-colors shadow-md shadow-blue-200"
                >
                  <Plus className="w-4 h-4" />
                  New Template
                </button>
              </div>
            }
          />

          {/* Search */}
          <div className="mb-6">
            <div className="relative max-w-md">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                placeholder="Search templates..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-10 pr-4 py-2.5 bg-white border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
              />
            </div>
          </div>

          {/* Error */}
          {error && (
            <div className="mb-6 flex items-center gap-3 p-4 bg-red-50 border border-red-200 rounded-xl text-red-700">
              <AlertCircle className="w-5 h-5 flex-shrink-0" />
              <div className="flex-1">
                <p className="font-medium">Error</p>
                <p className="text-sm text-red-600">{error}</p>
              </div>
              <button onClick={() => setError(null)} className="px-3 py-1.5 bg-red-100 text-red-700 rounded-lg text-sm font-medium hover:bg-red-200">
                Dismiss
              </button>
            </div>
          )}

          {/* Loading */}
          {isLoading && (
            <div className="flex flex-col items-center justify-center py-20">
              <Loader2 className="w-8 h-8 text-[#003149] animate-spin mb-4" />
              <p className="text-gray-500 text-sm">Loading templates...</p>
            </div>
          )}

          {/* Templates Grid */}
          {!isLoading && (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {filteredCards.map((card) => (
                <div
                  key={card.key}
                  className="bg-white rounded-2xl border border-gray-200 p-5 hover:border-blue-300 hover:shadow-lg transition-all cursor-pointer group"
                  onClick={() => openEdit(card)}
                >
                  <div className="flex items-start justify-between mb-3">
                    <div className={`p-3 rounded-xl ${card.source === 'bundled' ? 'bg-gray-100' : 'bg-blue-50'} group-hover:bg-blue-50 transition-colors`}>
                      {card.source === 'bundled' ? (
                        <Package className="w-6 h-6 text-gray-600 group-hover:text-blue-600" />
                      ) : (
                        <FileStack className="w-6 h-6 text-blue-600" />
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <span className={`text-[10px] font-bold uppercase px-2 py-1 rounded-full ${
                        card.source === 'bundled' ? 'bg-gray-100 text-gray-500' : 'bg-blue-100 text-blue-700'
                      }`}>
                        {card.source === 'bundled' ? 'Bundled' : 'Custom'}
                      </span>
                    </div>
                  </div>

                  <h3 className="font-semibold text-gray-900 mb-1 group-hover:text-blue-600 transition-colors">
                    {card.name}
                  </h3>
                  {card.description && (
                    <p className="text-sm text-gray-500 mb-3 line-clamp-2">{card.description}</p>
                  )}

                  <div className="flex items-center justify-between pt-3 border-t border-gray-100">
                    <span className={`text-[10px] font-bold uppercase px-2 py-1 rounded-full ${docTypeColors[card.docType] || 'bg-gray-100 text-gray-600'}`}>
                      {docTypeLabels[card.docType] || card.docType}
                    </span>
                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                        onClick={(e) => openPreview(card, e)}
                        className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                      >
                        <Eye className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {!isLoading && filteredCards.length === 0 && (
            <div className="text-center py-12">
              <FileStack className="w-12 h-12 text-gray-300 mx-auto mb-4" />
              <p className="text-gray-500">No templates found.</p>
            </div>
          )}
        </div>
      </main>

      {/* ─── Template Edit Modal ─── */}
      <Modal
        isOpen={!!selectedCard}
        onClose={() => setSelectedCard(null)}
        title={selectedCard ? `Edit: ${selectedCard.name}` : 'Template Details'}
        size="lg"
        footer={selectedCard && (
          <div className="flex justify-between">
            {selectedCard.source === 'custom' && (
              <button
                onClick={handleDeleteTemplate}
                disabled={saving}
                className="flex items-center gap-2 px-4 py-2 text-red-600 hover:text-red-700 disabled:opacity-50"
              >
                <Trash2 className="w-4 h-4" />
                Delete Override
              </button>
            )}
            <div className="flex gap-3 ml-auto">
              <button onClick={() => setSelectedCard(null)} className="px-4 py-2 text-gray-600 hover:text-gray-800">
                Cancel
              </button>
              <button
                onClick={handleSaveTemplate}
                disabled={saving || !editBody.trim()}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
              >
                {saving ? 'Saving...' : 'Save as Override'}
              </button>
            </div>
          </div>
        )}
      >
        {selectedCard && (
          <form className="space-y-4" onSubmit={(e) => e.preventDefault()}>
            <div className="flex items-center gap-2 mb-2">
              <span className={`text-xs font-bold uppercase px-2 py-1 rounded-full ${docTypeColors[selectedCard.docType] || 'bg-gray-100 text-gray-600'}`}>
                {docTypeLabels[selectedCard.docType] || selectedCard.docType}
              </span>
              <Badge variant={selectedCard.source === 'bundled' ? 'default' : 'primary'} size="sm">
                {selectedCard.source === 'bundled' ? 'Bundled' : 'Custom Override'}
              </Badge>
              <span className="text-xs text-gray-400">v{selectedCard.version}</span>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Display Name</label>
              <input
                type="text"
                value={editDisplayName}
                onChange={(e) => setEditDisplayName(e.target.value)}
                className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                <span className="flex items-center gap-2">
                  <Code className="w-4 h-4" />
                  Template Content
                </span>
              </label>
              <textarea
                value={editBody}
                onChange={(e) => setEditBody(e.target.value)}
                rows={12}
                className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 font-mono text-sm resize-none"
              />
              <p className="text-xs text-gray-500 mt-1">Use {'{{placeholder}}'} syntax for dynamic fields</p>
            </div>
          </form>
        )}
      </Modal>

      {/* ─── Template Preview Modal ─── */}
      <Modal
        isOpen={showPreviewModal}
        onClose={() => setShowPreviewModal(false)}
        title={previewCard ? `Preview: ${previewCard.name}` : 'Template Preview'}
        size="lg"
      >
        {previewCard && (
          <div className="space-y-4">
            <div className="flex items-center gap-2 mb-4">
              <span className={`text-xs font-bold uppercase px-2 py-1 rounded-full ${docTypeColors[previewCard.docType] || 'bg-gray-100 text-gray-600'}`}>
                {docTypeLabels[previewCard.docType] || previewCard.docType}
              </span>
              <Badge variant={previewCard.source === 'bundled' ? 'default' : 'primary'} size="sm">
                {previewCard.source === 'bundled' ? 'Bundled' : 'Custom'}
              </Badge>
            </div>

            <div>
              <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Template Content</h4>
              <div className="bg-gray-900 rounded-xl p-4 overflow-x-auto max-h-96 overflow-y-auto">
                <pre className="text-sm text-gray-100 whitespace-pre-wrap font-mono">
                  {previewCard.content}
                </pre>
              </div>
            </div>
          </div>
        )}
      </Modal>

      {/* ─── New Template Modal ─── */}
      <Modal
        isOpen={showNewModal}
        onClose={() => setShowNewModal(false)}
        title="Create New Template"
        size="lg"
        footer={
          <div className="flex justify-end gap-3">
            <button onClick={() => setShowNewModal(false)} className="px-4 py-2 text-gray-600 hover:text-gray-800">
              Cancel
            </button>
            <button
              onClick={handleCreateTemplate}
              disabled={saving || !newTpl.doc_type || !newTpl.template_body}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
            >
              {saving ? 'Creating...' : 'Create Template'}
            </button>
          </div>
        }
      >
        <form className="space-y-4" onSubmit={(e) => e.preventDefault()}>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Document Type *</label>
              <select
                value={newTpl.doc_type}
                onChange={(e) => setNewTpl(p => ({ ...p, doc_type: e.target.value }))}
                className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 bg-white"
              >
                <option value="">Select type...</option>
                {Object.entries(docTypeLabels).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Display Name</label>
              <input
                type="text"
                placeholder="e.g., Standard SOW Template"
                value={newTpl.display_name}
                onChange={(e) => setNewTpl(p => ({ ...p, display_name: e.target.value }))}
                className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Template Content *</label>
            <textarea
              rows={10}
              placeholder={'# Document Title\n\n## Section 1\n{{placeholder}}\n...'}
              value={newTpl.template_body}
              onChange={(e) => setNewTpl(p => ({ ...p, template_body: e.target.value }))}
              className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 font-mono text-sm resize-none"
            />
          </div>
        </form>
      </Modal>
    </div>
    </AuthGuard>
  );
}
