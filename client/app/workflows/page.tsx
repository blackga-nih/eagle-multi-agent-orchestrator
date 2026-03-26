'use client';

import { useState, useEffect, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { Plus, Search, Filter, ArrowUpDown, Eye, Edit2, CheckCircle2, Circle, FileText, Loader2 } from 'lucide-react';
import AuthGuard from '@/components/auth/auth-guard';
import TopNav from '@/components/layout/top-nav';
import PageHeader from '@/components/layout/page-header';
import Badge from '@/components/ui/badge';
import Modal from '@/components/ui/modal';
import { Tabs } from '@/components/ui/tabs';
import {
  getWorkflowStatusColor,
  getAcquisitionTypeLabel,
  formatCurrency,
  formatDate,
} from '@/lib/format-helpers';
import { getPackages, PackageData } from '@/lib/document-store';
import { Workflow, WorkflowStatus } from '@/types/schema';
import { useAuth } from '@/contexts/auth-context';

/** Convert a localStorage PackageData into a Workflow shape for the grid. */
function packageToWorkflow(pkg: PackageData): Workflow {
  const completed = pkg.checklist.filter((c) => c.status === 'completed').length;
  const total = pkg.checklist.length;
  return {
    id: pkg.id,
    user_id: 'local',
    title: pkg.title,
    description: `${completed}/${total} documents generated`,
    status: pkg.status,
    created_at: pkg.created_at,
    updated_at: pkg.updated_at,
    metadata: { _source: 'localStorage' },
    archived: false,
  };
}

/** Convert a backend package response into a Workflow shape. */
function backendToWorkflow(pkg: Record<string, unknown>): Workflow {
  return {
    id: (pkg.package_id as string) || (pkg.id as string) || '',
    user_id: (pkg.user_id as string) || '',
    title: (pkg.title as string) || 'Untitled Package',
    description: (pkg.description as string) || '',
    status: ((pkg.status as string) || 'in_progress') as WorkflowStatus,
    acquisition_type: pkg.acquisition_type as Workflow['acquisition_type'],
    estimated_value: pkg.estimated_value as number | undefined,
    timeline_deadline: pkg.timeline_deadline as string | undefined,
    urgency_level: pkg.urgency_level as Workflow['urgency_level'],
    created_at: (pkg.created_at as string) || new Date().toISOString(),
    updated_at: (pkg.updated_at as string) || new Date().toISOString(),
    metadata: { _source: 'backend' },
    archived: false,
  };
}

export default function WorkflowsPage() {
  const router = useRouter();
  const { getToken } = useAuth();
  const [activeTab, setActiveTab] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedWorkflow, setSelectedWorkflow] = useState<Workflow | null>(null);
  const [selectedPackage, setSelectedPackage] = useState<PackageData | null>(null);
  const [editingTitle, setEditingTitle] = useState(false);
  const [editTitleValue, setEditTitleValue] = useState('');
  const [showNewModal, setShowNewModal] = useState(false);
  const [localPackages, setLocalPackages] = useState<PackageData[]>([]);
  const [backendWorkflows, setBackendWorkflows] = useState<Workflow[]>([]);
  const [loading, setLoading] = useState(true);

  // Load localStorage packages on mount
  useEffect(() => {
    setLocalPackages(getPackages());
  }, []);

  // Fetch packages from backend
  useEffect(() => {
    let cancelled = false;
    async function loadBackendPackages() {
      try {
        const token = await getToken();
        const res = await fetch('/api/packages', {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (res.ok && !cancelled) {
          const data = await res.json();
          const packages = Array.isArray(data) ? data : data.packages || [];
          setBackendWorkflows(packages.map(backendToWorkflow));
        }
      } catch {
        // Backend unavailable — show only localStorage packages
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    loadBackendPackages();
    return () => { cancelled = true; };
  }, [getToken]);

  const allWorkflows = useMemo(() => {
    const localAsWorkflows = localPackages.map(packageToWorkflow);
    return [...localAsWorkflows, ...backendWorkflows];
  }, [localPackages, backendWorkflows]);

  const statusTabs = useMemo(() => [
    { id: 'all', label: 'All', badge: allWorkflows.length },
    { id: 'in_progress', label: 'In Progress', badge: allWorkflows.filter(w => w.status === 'in_progress').length },
    { id: 'pending_review', label: 'Pending Review', badge: allWorkflows.filter(w => w.status === 'pending_review').length },
    { id: 'approved', label: 'Approved', badge: allWorkflows.filter(w => w.status === 'approved').length },
    { id: 'completed', label: 'Completed', badge: allWorkflows.filter(w => w.status === 'completed').length },
  ], [allWorkflows]);

  const filteredWorkflows = allWorkflows.filter(w => {
    const matchesSearch = w.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      w.description?.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesStatus = activeTab === 'all' || w.status === activeTab;
    return matchesSearch && matchesStatus;
  });

  const handleWorkflowClick = (workflow: Workflow) => {
    // If it's a localStorage package, show the document checklist modal
    if ((workflow.metadata as Record<string, unknown>)?._source === 'localStorage') {
      const pkg = localPackages.find((p) => p.id === workflow.id) ?? null;
      setSelectedPackage(pkg);
    } else {
      setSelectedWorkflow(workflow);
    }
  };

  const handleEditTitle = () => {
    if (selectedPackage) {
      setEditTitleValue(selectedPackage.title);
      setEditingTitle(true);
    }
  };

  const handleSaveTitle = async () => {
    if (!selectedPackage || !editTitleValue.trim()) return;

    try {
      // Update localStorage
      const packages = getPackages();
      const updated = packages.map((pkg) =>
        pkg.id === selectedPackage.id
          ? { ...pkg, title: editTitleValue.trim(), updated_at: new Date().toISOString() }
          : pkg
      );

      // Persist back to localStorage
      const packagesMap = Object.fromEntries(
        updated.map((pkg) => [pkg.id, pkg])
      );
      try {
        localStorage.setItem('eagle_packages', JSON.stringify(packagesMap));
      } catch {
        // localStorage full or unavailable
      }

      // Update local packages state
      setLocalPackages(updated);
      const updatedPkg = updated.find((p) => p.id === selectedPackage.id);
      if (updatedPkg) {
        setSelectedPackage(updatedPkg);
      }

      // Optionally sync to backend if package has a package_id
      if (selectedPackage.package_id) {
        const token = await getToken();
        const headers: Record<string, string> = { 'Content-Type': 'application/json' };
        if (token) headers['Authorization'] = `Bearer ${token}`;

        await fetch(`/api/packages/${selectedPackage.package_id}`, {
          method: 'PUT',
          headers,
          body: JSON.stringify({ title: editTitleValue.trim() }),
        });
      }

      setEditingTitle(false);
    } catch (error) {
      console.error('Failed to save package title:', error);
    }
  };

  const handleCancelEdit = () => {
    setEditingTitle(false);
    setEditTitleValue('');
  };

  return (
    <AuthGuard>
    <div className="flex flex-col h-screen bg-gray-50">
      <TopNav />

      <main className="flex-1 overflow-y-auto">
        <div className="p-8">
          <PageHeader
            title="Acquisition Packages"
            description="Manage and track acquisition packages"
            actions={
              <button
                onClick={() => setShowNewModal(true)}
                className="flex items-center gap-2 px-4 py-2.5 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700 transition-colors shadow-md shadow-blue-200"
              >
                <Plus className="w-4 h-4" />
                New Package
              </button>
            }
          />

          {/* Filters */}
          <div className="mb-6 flex items-center gap-4">
            <div className="relative flex-1 max-w-md">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                placeholder="Search acquisition packages..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-10 pr-4 py-2.5 bg-white border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
              />
            </div>
            <button className="flex items-center gap-2 px-4 py-2.5 bg-white border border-gray-200 rounded-xl text-sm text-gray-600 hover:bg-gray-50">
              <Filter className="w-4 h-4" />
              Filters
            </button>
            <button className="flex items-center gap-2 px-4 py-2.5 bg-white border border-gray-200 rounded-xl text-sm text-gray-600 hover:bg-gray-50">
              <ArrowUpDown className="w-4 h-4" />
              Sort
            </button>
          </div>

          {/* Status Tabs */}
          <div className="mb-6">
            <Tabs tabs={statusTabs} activeTab={activeTab} onChange={setActiveTab} variant="pills" />
          </div>

          {/* Loading State */}
          {loading && (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="w-6 h-6 animate-spin text-blue-500 mr-2" />
              <span className="text-gray-500">Loading packages...</span>
            </div>
          )}

          {/* Workflow Grid */}
          {!loading && (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {filteredWorkflows.map((workflow) => (
                <div
                  key={workflow.id}
                  className="bg-white rounded-2xl border border-gray-200 p-5 hover:border-blue-300 hover:shadow-lg transition-all cursor-pointer group"
                  onClick={() => handleWorkflowClick(workflow)}
                >
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex-1">
                      <h3 className="font-semibold text-gray-900 group-hover:text-blue-600 transition-colors line-clamp-1">
                        {workflow.title}
                      </h3>
                      <p className="text-xs text-gray-500 mt-0.5">{workflow.id}</p>
                    </div>
                    <span className={`text-[10px] font-bold uppercase px-2 py-1 rounded-full ${getWorkflowStatusColor(workflow.status)}`}>
                      {workflow.status.replace('_', ' ')}
                    </span>
                  </div>

                  <p className="text-sm text-gray-600 mb-4 line-clamp-2">{workflow.description}</p>

                  <div className="flex flex-wrap gap-2 mb-4">
                    {workflow.acquisition_type && (
                      <Badge variant="primary" size="sm">
                        {getAcquisitionTypeLabel(workflow.acquisition_type)}
                      </Badge>
                    )}
                    {workflow.urgency_level === 'urgent' && (
                      <Badge variant="warning" size="sm">Urgent</Badge>
                    )}
                    {workflow.urgency_level === 'critical' && (
                      <Badge variant="danger" size="sm">Critical</Badge>
                    )}
                    {(workflow.metadata as Record<string, unknown>)?._source === 'localStorage' && (
                      <Badge variant="info" size="sm">AI Generated</Badge>
                    )}
                  </div>

                  <div className="flex items-center justify-between pt-4 border-t border-gray-100">
                    <div className="text-xs text-gray-500">
                      {workflow.estimated_value && (
                        <span className="font-semibold text-gray-700">{formatCurrency(workflow.estimated_value)}</span>
                      )}
                    </div>
                    <div className="text-xs text-gray-400">
                      {formatDate(workflow.updated_at)}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {!loading && filteredWorkflows.length === 0 && (
            <div className="text-center py-12">
              <FileText className="w-10 h-10 text-gray-300 mx-auto mb-3" />
              <p className="text-gray-500">No acquisition packages found.</p>
              <p className="text-sm text-gray-400 mt-1">Start a new intake in Chat to create your first package.</p>
            </div>
          )}
        </div>
      </main>

      {/* Backend Workflow Detail Modal */}
      <Modal
        isOpen={!!selectedWorkflow}
        onClose={() => setSelectedWorkflow(null)}
        title={selectedWorkflow?.title}
        size="lg"
        footer={
          <div className="flex justify-between">
            <button
              onClick={() => setSelectedWorkflow(null)}
              className="px-4 py-2 text-gray-600 hover:text-gray-800"
            >
              Close
            </button>
            <div className="flex gap-2">
              <button className="flex items-center gap-2 px-4 py-2 border border-gray-200 rounded-lg text-sm hover:bg-gray-50">
                <Edit2 className="w-4 h-4" />
                Edit
              </button>
              <button className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700">
                <Eye className="w-4 h-4" />
                View Full Details
              </button>
            </div>
          </div>
        }
      >
        {selectedWorkflow && (
          <div className="space-y-6">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-xs text-gray-500 uppercase tracking-wide">Status</label>
                <p className="mt-1">
                  <span className={`inline-block text-xs font-bold uppercase px-2 py-1 rounded-full ${getWorkflowStatusColor(selectedWorkflow.status)}`}>
                    {selectedWorkflow.status.replace('_', ' ')}
                  </span>
                </p>
              </div>
              <div>
                <label className="text-xs text-gray-500 uppercase tracking-wide">Type</label>
                <p className="mt-1 text-sm font-medium">
                  {selectedWorkflow.acquisition_type ? getAcquisitionTypeLabel(selectedWorkflow.acquisition_type) : 'Not set'}
                </p>
              </div>
              <div>
                <label className="text-xs text-gray-500 uppercase tracking-wide">Estimated Value</label>
                <p className="mt-1 text-sm font-medium">
                  {selectedWorkflow.estimated_value ? formatCurrency(selectedWorkflow.estimated_value) : 'TBD'}
                </p>
              </div>
              <div>
                <label className="text-xs text-gray-500 uppercase tracking-wide">Deadline</label>
                <p className="mt-1 text-sm font-medium">
                  {selectedWorkflow.timeline_deadline ? formatDate(selectedWorkflow.timeline_deadline) : 'Not set'}
                </p>
              </div>
            </div>

            <div>
              <label className="text-xs text-gray-500 uppercase tracking-wide">Description</label>
              <p className="mt-1 text-sm text-gray-700">{selectedWorkflow.description || 'No description'}</p>
            </div>
          </div>
        )}
      </Modal>

      {/* localStorage Package Detail Modal — Document Checklist */}
      <Modal
        isOpen={!!selectedPackage}
        onClose={() => {
          setSelectedPackage(null);
          setEditingTitle(false);
        }}
        size="lg"
        footer={
          <div className="flex justify-end">
            <button
              onClick={() => setSelectedPackage(null)}
              className="px-4 py-2 text-gray-600 hover:text-gray-800"
            >
              Close
            </button>
          </div>
        }
      >
        {selectedPackage && (
          <div className="space-y-6">
            {/* Editable title - double-click to edit */}
            <div className="-mt-2 -mx-6 px-6 pb-4 border-b border-gray-100">
              {editingTitle ? (
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={editTitleValue}
                    onChange={(e) => setEditTitleValue(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') handleSaveTitle();
                      if (e.key === 'Escape') handleCancelEdit();
                    }}
                    onBlur={handleSaveTitle}
                    autoFocus
                    className="flex-1 text-lg font-bold text-gray-900 px-2 py-1 -ml-2 border border-blue-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
              ) : (
                <h2
                  className="text-lg font-bold text-gray-900 cursor-pointer hover:text-blue-600 transition-colors"
                  onDoubleClick={handleEditTitle}
                  title="Double-click to edit"
                >
                  {selectedPackage.title}
                </h2>
              )}
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-xs text-gray-500 uppercase tracking-wide">Status</label>
                <p className="mt-1">
                  <span className={`inline-block text-xs font-bold uppercase px-2 py-1 rounded-full ${getWorkflowStatusColor(selectedPackage.status)}`}>
                    {selectedPackage.status.replace('_', ' ')}
                  </span>
                </p>
              </div>
              <div>
                <label className="text-xs text-gray-500 uppercase tracking-wide">Documents</label>
                <p className="mt-1 text-sm font-medium">
                  {selectedPackage.checklist.filter((c) => c.status === 'completed').length} / {selectedPackage.checklist.length} completed
                </p>
              </div>
              <div>
                <label className="text-xs text-gray-500 uppercase tracking-wide">Created</label>
                <p className="mt-1 text-sm font-medium">{formatDate(selectedPackage.created_at)}</p>
              </div>
              <div>
                <label className="text-xs text-gray-500 uppercase tracking-wide">Last Updated</label>
                <p className="mt-1 text-sm font-medium">{formatDate(selectedPackage.updated_at)}</p>
              </div>
            </div>

            <div>
              <label className="text-xs text-gray-500 uppercase tracking-wide mb-2 block">Document Checklist</label>
              <div className="space-y-2">
                {selectedPackage.checklist.map((item) => (
                  <div
                    key={item.document_type}
                    className={`flex items-center gap-3 p-3 rounded-lg ${
                      item.status === 'completed' ? 'bg-green-50' : 'bg-gray-50'
                    } ${item.document_id ? 'cursor-pointer hover:bg-green-100 transition-colors' : ''}`}
                    onClick={() => {
                      if (item.document_id) {
                        router.push(`/documents/${item.document_id}`);
                      }
                    }}
                  >
                    {item.status === 'completed' ? (
                      <CheckCircle2 className="w-5 h-5 text-green-600 shrink-0" />
                    ) : (
                      <Circle className="w-5 h-5 text-gray-300 shrink-0" />
                    )}
                    <div className="flex-1">
                      <p className={`text-sm font-medium ${item.status === 'completed' ? 'text-green-900' : 'text-gray-700'}`}>
                        {item.label}
                      </p>
                    </div>
                    <span className={`text-[10px] font-semibold uppercase px-2 py-0.5 rounded ${
                      item.status === 'completed' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'
                    }`}>
                      {item.status}
                    </span>
                    {item.document_id && (
                      <FileText className="w-4 h-4 text-green-600 shrink-0" />
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </Modal>

      {/* New Workflow Modal */}
      <Modal
        isOpen={showNewModal}
        onClose={() => setShowNewModal(false)}
        title="Create New Acquisition Package"
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
              Create Package
            </button>
          </div>
        }
      >
        <form className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Title *</label>
            <input
              type="text"
              placeholder="e.g., New CT Scanner Acquisition"
              className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
            <textarea
              rows={3}
              placeholder="Describe the acquisition requirement..."
              className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 resize-none"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Acquisition Type</label>
              <select className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 bg-white">
                <option value="">Select type...</option>
                <option value="micro_purchase">Micro-Purchase (&lt;$10K)</option>
                <option value="simplified">Simplified ($10K-$250K)</option>
                <option value="negotiated">Negotiated (&gt;$250K)</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Urgency</label>
              <select className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 bg-white">
                <option value="standard">Standard</option>
                <option value="urgent">Urgent</option>
                <option value="critical">Critical</option>
              </select>
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Estimated Value</label>
            <input
              type="text"
              placeholder="e.g., $500,000"
              className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Deadline</label>
            <input
              type="date"
              className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
            />
          </div>
        </form>
      </Modal>
    </div>
    </AuthGuard>
  );
}
