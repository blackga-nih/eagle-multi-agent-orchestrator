'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Plus, Search, FileStack, Trash2, Eye, Code, Loader2, AlertCircle,
  RefreshCw, Package, FileText, FileSpreadsheet, File, Filter,
  Copy, CheckCircle2, X, ChevronDown,
} from 'lucide-react';
import AuthGuard from '@/components/auth/auth-guard';
import TopNav from '@/components/layout/top-nav';
import PageHeader from '@/components/layout/page-header';
import Badge from '@/components/ui/badge';
import Modal from '@/components/ui/modal';
import { useAuth } from '@/contexts/auth-context';
import { pluginApi, templateApi } from '@/lib/admin-api';
import { listPackages, type PackageInfo } from '@/lib/document-api';
import type { PluginEntity, TemplateEntity, S3Template } from '@/types/admin';

// ---------------------------------------------------------------------------
// Constants & Helpers
// ---------------------------------------------------------------------------

type TabType = 'all' | 's3' | 'custom';

const docTypeLabels: Record<string, string> = {
  sow: 'Statement of Work',
  igce: 'Cost Estimate (IGCE)',
  market_research: 'Market Research',
  acquisition_plan: 'Acquisition Plan',
  justification: 'Justification',
  funding_doc: 'Funding Document',
  cor_certification: 'COR Certification',
  son_products: 'SON - Products',
  son_services: 'SON - Services',
  buy_american: 'Buy American',
  subk_plan: 'Subcontracting Plan',
  conference_request: 'Conference Request',
  custom: 'Custom Document',
};

const docTypeColors: Record<string, string> = {
  sow: 'bg-blue-100 text-blue-700',
  igce: 'bg-green-100 text-green-700',
  market_research: 'bg-purple-100 text-purple-700',
  acquisition_plan: 'bg-amber-100 text-amber-700',
  justification: 'bg-red-100 text-red-700',
  funding_doc: 'bg-cyan-100 text-cyan-700',
  cor_certification: 'bg-teal-100 text-teal-700',
  son_products: 'bg-indigo-100 text-indigo-700',
  son_services: 'bg-indigo-100 text-indigo-700',
  buy_american: 'bg-orange-100 text-orange-700',
  subk_plan: 'bg-pink-100 text-pink-700',
  conference_request: 'bg-slate-100 text-slate-700',
  custom: 'bg-gray-100 text-gray-600',
};

const phaseColors: Record<string, string> = {
  intake: 'bg-sky-100 text-sky-700',
  planning: 'bg-violet-100 text-violet-700',
  solicitation: 'bg-amber-100 text-amber-700',
  evaluation: 'bg-emerald-100 text-emerald-700',
  award: 'bg-blue-100 text-blue-700',
  administration: 'bg-slate-100 text-slate-700',
};

const fileTypeIcons: Record<string, typeof FileText> = {
  docx: FileText,
  doc: FileText,
  xlsx: FileSpreadsheet,
  xls: FileSpreadsheet,
  pdf: File,
};

function formatDate(d: string): string {
  return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// Unified card type for rendering all template sources
interface TemplateCard {
  key: string;
  name: string;
  description: string;
  docType: string;
  source: 'bundled' | 'custom' | 's3';
  content: string;
  version: number;
  updatedAt: string;
  // S3-specific fields
  s3Key?: string;
  fileType?: string;
  sizeBytes?: number;
  phase?: string;
  useCase?: string;
  registered?: boolean;
  raw: PluginEntity | TemplateEntity | S3Template;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function TemplatesPage() {
  const { getToken } = useAuth();

  // Data
  const [pluginTemplates, setPluginTemplates] = useState<PluginEntity[]>([]);
  const [customTemplates, setCustomTemplates] = useState<TemplateEntity[]>([]);
  const [s3Templates, setS3Templates] = useState<S3Template[]>([]);
  const [packages, setPackages] = useState<PackageInfo[]>([]);
  const [phases, setPhases] = useState<Record<string, string>>({});
  const [phaseCounts, setPhaseCounts] = useState<Record<string, number>>({});

  // UI
  const [activeTab, setActiveTab] = useState<TabType>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [phaseFilter, setPhaseFilter] = useState<string | null>(null);
  const [fileTypeFilter, setFileTypeFilter] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Modals
  const [selectedCard, setSelectedCard] = useState<TemplateCard | null>(null);
  const [showPreviewModal, setShowPreviewModal] = useState(false);
  const [previewCard, setPreviewCard] = useState<TemplateCard | null>(null);
  const [showNewModal, setShowNewModal] = useState(false);
  const [showCopyModal, setShowCopyModal] = useState(false);
  const [copyTarget, setCopyTarget] = useState<TemplateCard | null>(null);
  const [selectedPackageId, setSelectedPackageId] = useState<string>('');
  const [newPackageTitle, setNewPackageTitle] = useState<string>('');

  // Edit form state
  const [editBody, setEditBody] = useState('');
  const [editDisplayName, setEditDisplayName] = useState('');

  // New template form
  const [newTpl, setNewTpl] = useState({ doc_type: '', display_name: '', template_body: '' });

  // -----------------------------------------------------------------------
  // Data fetching
  // -----------------------------------------------------------------------

  const fetchData = useCallback(async (refresh = false) => {
    setIsLoading(true);
    setError(null);
    try {
      const token = await getToken();
      const [plugins, custom, s3Response, pkgs] = await Promise.all([
        pluginApi.list(getToken, 'templates').catch(() => []),
        templateApi.list(getToken).catch(() => []),
        templateApi.listS3(getToken, undefined, refresh).catch(() => ({
          templates: [],
          total: 0,
          phases: {},
          phase_counts: {},
        })),
        listPackages(token).catch(() => []),
      ]);
      // Defensive: ensure arrays even if API returns unexpected shape
      setPluginTemplates(Array.isArray(plugins) ? plugins : []);
      setCustomTemplates(Array.isArray(custom) ? custom : []);
      setS3Templates(Array.isArray(s3Response?.templates) ? s3Response.templates : []);
      setPhases(s3Response?.phases && typeof s3Response.phases === 'object' ? s3Response.phases as Record<string, string> : {});
      setPhaseCounts(s3Response?.phase_counts && typeof s3Response.phase_counts === 'object' ? s3Response.phase_counts as Record<string, number> : {});
      setPackages(Array.isArray(pkgs) ? pkgs : []);
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

  const cards: TemplateCard[] = useMemo(() => [
    ...(pluginTemplates || []).map((p): TemplateCard => ({
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
    ...(customTemplates || []).map((t): TemplateCard => ({
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
    ...(s3Templates || []).map((s): TemplateCard => ({
      key: `s3-${s.s3_key}`,
      name: s.display_name,
      description: s.filename,
      docType: s.doc_type || 'custom',
      source: 's3',
      content: '', // S3 templates are binary, no content preview
      version: 1,
      updatedAt: s.last_modified || '',
      s3Key: s.s3_key,
      fileType: s.file_type,
      sizeBytes: s.size_bytes,
      phase: s.category?.phase,
      useCase: s.category?.use_case,
      registered: s.registered,
      raw: s,
    })),
  ], [pluginTemplates, customTemplates, s3Templates]);

  // Filter cards based on tab, search, phase, and file type
  const filteredCards = useMemo(() => {
    const q = searchQuery.toLowerCase();
    return cards.filter(c => {
      // Tab filter
      if (activeTab === 's3' && c.source !== 's3') return false;
      if (activeTab === 'custom' && c.source !== 'custom' && c.source !== 'bundled') return false;

      // Phase filter (S3 templates only)
      if (phaseFilter && c.source === 's3' && c.phase !== phaseFilter) return false;

      // File type filter (S3 templates only)
      if (fileTypeFilter && c.source === 's3' && c.fileType !== fileTypeFilter) return false;

      // Search filter
      return (
        c.name.toLowerCase().includes(q) ||
        c.docType.toLowerCase().includes(q) ||
        c.description.toLowerCase().includes(q)
      );
    });
  }, [cards, activeTab, searchQuery, phaseFilter, fileTypeFilter]);

  // Get unique file types for filter
  const uniqueFileTypes = useMemo(() => {
    const types = new Set<string>();
    (s3Templates || []).forEach(t => types.add(t.file_type));
    return Array.from(types).sort();
  }, [s3Templates]);

  // Tab counts
  const tabCounts = useMemo(() => ({
    all: cards.length,
    s3: cards.filter(c => c.source === 's3').length,
    custom: cards.filter(c => c.source === 'custom' || c.source === 'bundled').length,
  }), [cards]);

  // -----------------------------------------------------------------------
  // Actions
  // -----------------------------------------------------------------------

  function openEdit(card: TemplateCard) {
    if (card.source === 's3') {
      // For S3 templates, open copy modal
      openCopyModal(card);
    } else {
      setSelectedCard(card);
      setEditBody(card.content);
      setEditDisplayName(card.name);
    }
  }

  function openPreview(card: TemplateCard, e: React.MouseEvent) {
    e.stopPropagation();
    setPreviewCard(card);
    setShowPreviewModal(true);
  }

  function openCopyModal(card: TemplateCard) {
    setCopyTarget(card);
    setSelectedPackageId('');
    setShowCopyModal(true);
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

  async function handleCopyToPackage() {
    if (!copyTarget?.s3Key) return;
    // Require either an existing package OR a new package title
    if (selectedPackageId !== '__new__' && !selectedPackageId) return;
    if (selectedPackageId === '__new__' && !newPackageTitle.trim()) return;

    setSaving(true);
    try {
      let targetPackageId = selectedPackageId;

      // Create new package if needed
      if (selectedPackageId === '__new__') {
        const token = await getToken();
        const response = await fetch('/api/packages', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ title: newPackageTitle.trim() }),
        });
        if (!response.ok) {
          throw new Error('Failed to create package');
        }
        const newPkg = await response.json();
        targetPackageId = newPkg.package_id;
        // Update packages list so it appears in dropdown
        setPackages(prev => [newPkg, ...prev]);
      }

      const result = await templateApi.copyToPackage(getToken, {
        s3_key: copyTarget.s3Key,
        package_id: targetPackageId,
      });
      setShowCopyModal(false);
      setCopyTarget(null);
      setSelectedPackageId('');
      setNewPackageTitle('');
      setSuccessMessage(`Template copied to package. Document ID: ${result.document_id}`);
      setTimeout(() => setSuccessMessage(null), 5000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to copy template');
    } finally {
      setSaving(false);
    }
  }

  // -----------------------------------------------------------------------
  // Render helpers
  // -----------------------------------------------------------------------

  function renderFileTypeIcon(fileType: string | undefined) {
    const Icon = fileTypeIcons[fileType || ''] || File;
    return <Icon className="w-5 h-5" />;
  }

  function renderSourceBadge(source: 'bundled' | 'custom' | 's3') {
    const config = {
      bundled: { label: 'Bundled', class: 'bg-gray-100 text-gray-500' },
      custom: { label: 'Custom', class: 'bg-blue-100 text-blue-700' },
      s3: { label: 'S3 Library', class: 'bg-emerald-100 text-emerald-700' },
    };
    const { label, class: cls } = config[source];
    return (
      <span className={`text-[10px] font-bold uppercase px-2 py-1 rounded-full ${cls}`}>
        {label}
      </span>
    );
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
            description="Browse S3 template library and manage custom overrides"
            breadcrumbs={[
              { label: 'Admin', href: '/admin' },
              { label: 'Templates' },
            ]}
            actions={
              <div className="flex items-center gap-2">
                <button
                  onClick={() => fetchData(true)}
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

          {/* Tabs */}
          <div className="flex items-center gap-1 mb-6 bg-gray-100 rounded-xl p-1 w-fit">
            {(['all', 's3', 'custom'] as TabType[]).map(tab => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  activeTab === tab
                    ? 'bg-white text-gray-900 shadow-sm'
                    : 'text-gray-600 hover:text-gray-900'
                }`}
              >
                {tab === 'all' ? 'All' : tab === 's3' ? 'S3 Library' : 'Custom & Bundled'}
                <span className="ml-1.5 text-xs text-gray-400">({tabCounts[tab]})</span>
              </button>
            ))}
          </div>

          {/* Filters (shown for S3 tab or All tab) */}
          {(activeTab === 's3' || activeTab === 'all') && (
            <div className="flex flex-wrap items-center gap-3 mb-6">
              {/* Search */}
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <input
                  type="text"
                  placeholder="Search templates..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-64 pl-10 pr-4 py-2.5 bg-white border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
                />
              </div>

              {/* Phase Filter */}
              <div className="relative">
                <select
                  value={phaseFilter || ''}
                  onChange={(e) => setPhaseFilter(e.target.value || null)}
                  className="appearance-none pl-4 pr-10 py-2.5 bg-white border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 cursor-pointer"
                >
                  <option value="">All Phases</option>
                  {Object.entries(phases).map(([key, label]) => (
                    <option key={key} value={key}>
                      {label} ({phaseCounts[key] || 0})
                    </option>
                  ))}
                </select>
                <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
              </div>

              {/* File Type Filter */}
              <div className="relative">
                <select
                  value={fileTypeFilter || ''}
                  onChange={(e) => setFileTypeFilter(e.target.value || null)}
                  className="appearance-none pl-4 pr-10 py-2.5 bg-white border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 cursor-pointer"
                >
                  <option value="">All File Types</option>
                  {uniqueFileTypes.map(type => (
                    <option key={type} value={type}>{type.toUpperCase()}</option>
                  ))}
                </select>
                <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
              </div>

              {/* Clear filters */}
              {(phaseFilter || fileTypeFilter || searchQuery) && (
                <button
                  onClick={() => {
                    setPhaseFilter(null);
                    setFileTypeFilter(null);
                    setSearchQuery('');
                  }}
                  className="flex items-center gap-1.5 px-3 py-2 text-sm text-gray-500 hover:text-gray-700"
                >
                  <X className="w-4 h-4" />
                  Clear filters
                </button>
              )}
            </div>
          )}

          {/* Search only for custom tab */}
          {activeTab === 'custom' && (
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
          )}

          {/* Success Message */}
          {successMessage && (
            <div className="mb-6 flex items-center gap-3 p-4 bg-green-50 border border-green-200 rounded-xl text-green-700">
              <CheckCircle2 className="w-5 h-5 flex-shrink-0" />
              <div className="flex-1">
                <p className="font-medium">{successMessage}</p>
              </div>
              <button onClick={() => setSuccessMessage(null)} className="px-3 py-1.5 bg-green-100 text-green-700 rounded-lg text-sm font-medium hover:bg-green-200">
                Dismiss
              </button>
            </div>
          )}

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
                    <div className={`p-3 rounded-xl ${
                      card.source === 's3' ? 'bg-emerald-50' :
                      card.source === 'bundled' ? 'bg-gray-100' : 'bg-blue-50'
                    } group-hover:bg-blue-50 transition-colors`}>
                      {card.source === 's3' ? (
                        renderFileTypeIcon(card.fileType)
                      ) : card.source === 'bundled' ? (
                        <Package className="w-6 h-6 text-gray-600 group-hover:text-blue-600" />
                      ) : (
                        <FileStack className="w-6 h-6 text-blue-600" />
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      {renderSourceBadge(card.source)}
                    </div>
                  </div>

                  <h3 className="font-semibold text-gray-900 mb-1 group-hover:text-blue-600 transition-colors line-clamp-1">
                    {card.name}
                  </h3>
                  {card.description && (
                    <p className="text-sm text-gray-500 mb-3 line-clamp-1">{card.description}</p>
                  )}

                  {/* S3 template metadata */}
                  {card.source === 's3' && (
                    <div className="flex items-center gap-2 mb-3 text-xs text-gray-400">
                      <span className="uppercase">{card.fileType}</span>
                      {card.sizeBytes !== undefined && (
                        <>
                          <span>·</span>
                          <span>{formatBytes(card.sizeBytes)}</span>
                        </>
                      )}
                      {card.registered && (
                        <>
                          <span>·</span>
                          <span className="text-emerald-500 flex items-center gap-1">
                            <CheckCircle2 className="w-3 h-3" />
                            Registered
                          </span>
                        </>
                      )}
                    </div>
                  )}

                  <div className="flex items-center justify-between pt-3 border-t border-gray-100">
                    <div className="flex items-center gap-2">
                      {/* Phase badge for S3 templates */}
                      {card.phase && (
                        <span className={`text-[10px] font-bold uppercase px-2 py-1 rounded-full ${phaseColors[card.phase] || 'bg-gray-100 text-gray-600'}`}>
                          {phases[card.phase] || card.phase}
                        </span>
                      )}
                      {/* Doc type badge */}
                      <span className={`text-[10px] font-bold uppercase px-2 py-1 rounded-full ${docTypeColors[card.docType] || 'bg-gray-100 text-gray-600'}`}>
                        {docTypeLabels[card.docType] || card.docType}
                      </span>
                    </div>
                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      {card.source === 's3' ? (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            openCopyModal(card);
                          }}
                          className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                          title="Use Template"
                        >
                          <Copy className="w-4 h-4" />
                        </button>
                      ) : (
                        <button
                          onClick={(e) => openPreview(card, e)}
                          className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                        >
                          <Eye className="w-4 h-4" />
                        </button>
                      )}
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

      {/* Template Edit Modal */}
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

      {/* Template Preview Modal */}
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

      {/* New Template Modal */}
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

      {/* Copy to Package Modal */}
      <Modal
        isOpen={showCopyModal}
        onClose={() => {
          setShowCopyModal(false);
          setCopyTarget(null);
          setSelectedPackageId('');
        }}
        title="Use Template"
        size="md"
        footer={
          <div className="flex justify-end gap-3">
            <button
              onClick={() => {
                setShowCopyModal(false);
                setCopyTarget(null);
                setSelectedPackageId('');
                setNewPackageTitle('');
              }}
              className="px-4 py-2 text-gray-600 hover:text-gray-800"
            >
              Cancel
            </button>
            <button
              onClick={handleCopyToPackage}
              disabled={saving || (!selectedPackageId || (selectedPackageId === '__new__' && !newPackageTitle.trim()))}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
            >
              <Copy className="w-4 h-4" />
              {saving ? (selectedPackageId === '__new__' ? 'Creating...' : 'Copying...') : 'Copy to Package'}
            </button>
          </div>
        }
      >
        {copyTarget && (
          <div className="space-y-4">
            <div className="p-4 bg-gray-50 rounded-xl">
              <div className="flex items-center gap-3 mb-2">
                {renderFileTypeIcon(copyTarget.fileType)}
                <div>
                  <h4 className="font-medium text-gray-900">{copyTarget.name}</h4>
                  <p className="text-sm text-gray-500">{copyTarget.description}</p>
                </div>
              </div>
              <div className="flex items-center gap-2 mt-2">
                {copyTarget.phase && (
                  <span className={`text-[10px] font-bold uppercase px-2 py-1 rounded-full ${phaseColors[copyTarget.phase] || 'bg-gray-100 text-gray-600'}`}>
                    {phases[copyTarget.phase] || copyTarget.phase}
                  </span>
                )}
                <span className={`text-[10px] font-bold uppercase px-2 py-1 rounded-full ${docTypeColors[copyTarget.docType] || 'bg-gray-100 text-gray-600'}`}>
                  {docTypeLabels[copyTarget.docType] || copyTarget.docType}
                </span>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Select Target Package *
              </label>
              <select
                value={selectedPackageId}
                onChange={(e) => {
                  setSelectedPackageId(e.target.value);
                  if (e.target.value !== '__new__') setNewPackageTitle('');
                }}
                className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 bg-white"
              >
                <option value="">Select a package...</option>
                <option value="__new__">+ Create New Package</option>
                {packages.map(pkg => (
                  <option key={pkg.package_id} value={pkg.package_id}>
                    {pkg.title || pkg.package_id}
                    {pkg.status && ` (${pkg.status})`}
                  </option>
                ))}
              </select>
              {selectedPackageId === '__new__' && (
                <input
                  type="text"
                  placeholder="Enter package title..."
                  value={newPackageTitle}
                  onChange={(e) => setNewPackageTitle(e.target.value)}
                  className="mt-2 w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
                  autoFocus
                />
              )}
            </div>

            <p className="text-xs text-gray-500">
              This will create a copy of the template in your selected package. You can then customize the copy within the package.
            </p>
          </div>
        )}
      </Modal>
    </div>
    </AuthGuard>
  );
}
