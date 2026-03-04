'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  Layers, Plus, Trash2, CheckCircle2, Loader2, AlertCircle, RefreshCw,
  Shield, Globe, Lock, XCircle, ChevronDown, ChevronUp,
} from 'lucide-react';
import AuthGuard from '@/components/auth/auth-guard';
import TopNav from '@/components/layout/top-nav';
import PageHeader from '@/components/layout/page-header';
import Badge from '@/components/ui/badge';
import Modal from '@/components/ui/modal';
import { useAuth } from '@/contexts/auth-context';
import { workspaceApi } from '@/lib/admin-api';
import type { Workspace, WorkspaceOverride } from '@/types/admin';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDate(d: string): string {
  return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

const visibilityIcons: Record<string, React.ReactNode> = {
  private: <Lock className="w-3 h-3" />,
  tenant: <Shield className="w-3 h-3" />,
  public: <Globe className="w-3 h-3" />,
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function WorkspacesPage() {
  const { getToken } = useAuth();

  // Data
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [overrides, setOverrides] = useState<WorkspaceOverride[]>([]);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  // UI
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Modals
  const [showNewModal, setShowNewModal] = useState(false);
  const [newWs, setNewWs] = useState({ name: '', description: '', visibility: 'private', is_active: true });

  // -----------------------------------------------------------------------
  // Data fetching
  // -----------------------------------------------------------------------

  const fetchWorkspaces = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await workspaceApi.list(getToken);
      setWorkspaces(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load workspaces');
    } finally {
      setIsLoading(false);
    }
  }, [getToken]);

  useEffect(() => { fetchWorkspaces(); }, [fetchWorkspaces]);

  // -----------------------------------------------------------------------
  // Override fetching for expanded workspace
  // -----------------------------------------------------------------------

  const fetchOverrides = useCallback(async (wsId: string) => {
    try {
      const data = await workspaceApi.listOverrides(getToken, wsId);
      setOverrides(Array.isArray(data) ? data : []);
    } catch {
      setOverrides([]);
    }
  }, [getToken]);

  async function toggleExpand(wsId: string) {
    if (expandedId === wsId) {
      setExpandedId(null);
      setOverrides([]);
    } else {
      setExpandedId(wsId);
      await fetchOverrides(wsId);
    }
  }

  // -----------------------------------------------------------------------
  // Actions
  // -----------------------------------------------------------------------

  async function handleCreate() {
    setSaving(true);
    try {
      await workspaceApi.create(getToken, {
        name: newWs.name,
        description: newWs.description,
        visibility: newWs.visibility,
        is_active: newWs.is_active,
      });
      setShowNewModal(false);
      setNewWs({ name: '', description: '', visibility: 'private', is_active: true });
      await fetchWorkspaces();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create workspace');
    } finally {
      setSaving(false);
    }
  }

  async function handleActivate(wsId: string) {
    setSaving(true);
    try {
      await workspaceApi.activate(getToken, wsId);
      await fetchWorkspaces();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to activate workspace');
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(wsId: string) {
    setSaving(true);
    try {
      await workspaceApi.delete(getToken, wsId);
      if (expandedId === wsId) {
        setExpandedId(null);
        setOverrides([]);
      }
      await fetchWorkspaces();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete workspace');
    } finally {
      setSaving(false);
    }
  }

  async function handleRemoveOverride(wsId: string, entityType: string, name: string) {
    try {
      await workspaceApi.deleteOverride(getToken, wsId, entityType, name);
      await fetchOverrides(wsId);
      await fetchWorkspaces();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to remove override');
    }
  }

  async function handleResetOverrides(wsId: string) {
    setSaving(true);
    try {
      await workspaceApi.resetOverrides(getToken, wsId);
      setOverrides([]);
      await fetchWorkspaces();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to reset overrides');
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
            title="Workspaces"
            description="Manage prompt environments and override layers"
            breadcrumbs={[
              { label: 'Admin', href: '/admin' },
              { label: 'Workspaces' },
            ]}
            actions={
              <div className="flex items-center gap-2">
                <button
                  onClick={() => fetchWorkspaces()}
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
                  New Workspace
                </button>
              </div>
            }
          />

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
              <p className="text-gray-500 text-sm">Loading workspaces...</p>
            </div>
          )}

          {/* Workspaces Grid */}
          {!isLoading && (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {workspaces.map((ws) => (
                <div
                  key={ws.workspace_id}
                  className={`bg-white rounded-2xl border ${
                    ws.is_active ? 'border-green-300 ring-1 ring-green-100' : 'border-gray-200'
                  } transition-all`}
                >
                  {/* Card header */}
                  <div className="p-5">
                    <div className="flex items-start justify-between mb-3">
                      <div className={`p-3 rounded-xl ${ws.is_active ? 'bg-green-100' : 'bg-gray-100'}`}>
                        <Layers className={`w-6 h-6 ${ws.is_active ? 'text-green-600' : 'text-gray-500'}`} />
                      </div>
                      <div className="flex items-center gap-2">
                        {ws.is_default && (
                          <span className="text-[10px] font-bold uppercase px-2 py-1 rounded-full bg-blue-100 text-blue-700">
                            Default
                          </span>
                        )}
                        {ws.is_active ? (
                          <span className="flex items-center gap-1 text-[10px] font-bold uppercase px-2 py-1 rounded-full bg-green-100 text-green-700">
                            <CheckCircle2 className="w-3 h-3" />
                            Active
                          </span>
                        ) : (
                          <button
                            onClick={() => handleActivate(ws.workspace_id)}
                            disabled={saving}
                            className="text-[10px] font-bold uppercase px-2 py-1 rounded-full bg-gray-100 text-gray-500 hover:bg-green-100 hover:text-green-700 transition-colors disabled:opacity-50"
                          >
                            Activate
                          </button>
                        )}
                      </div>
                    </div>

                    <h3 className="font-semibold text-gray-900 mb-1">{ws.name}</h3>
                    {ws.description && (
                      <p className="text-sm text-gray-500 mb-3 line-clamp-2">{ws.description}</p>
                    )}

                    <div className="flex items-center gap-3 text-xs text-gray-500">
                      <span className="flex items-center gap-1">
                        {visibilityIcons[ws.visibility] || visibilityIcons.private}
                        {ws.visibility}
                      </span>
                      <span>{ws.override_count} override{ws.override_count !== 1 ? 's' : ''}</span>
                      <span>{formatDate(ws.updated_at)}</span>
                    </div>

                    {/* Action bar */}
                    <div className="flex items-center justify-between mt-4 pt-3 border-t border-gray-100">
                      <button
                        onClick={() => toggleExpand(ws.workspace_id)}
                        className="text-xs text-blue-600 hover:text-blue-800 font-medium flex items-center gap-1"
                      >
                        {expandedId === ws.workspace_id ? (
                          <><ChevronUp className="w-3 h-3" /> Hide Overrides</>
                        ) : (
                          <><ChevronDown className="w-3 h-3" /> View Overrides</>
                        )}
                      </button>
                      {!ws.is_default && (
                        <button
                          onClick={() => handleDelete(ws.workspace_id)}
                          disabled={saving}
                          className="text-xs text-red-500 hover:text-red-700 font-medium flex items-center gap-1 disabled:opacity-50"
                        >
                          <Trash2 className="w-3 h-3" /> Delete
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Expanded overrides */}
                  {expandedId === ws.workspace_id && (
                    <div className="border-t border-gray-100 bg-gray-50 p-4 rounded-b-2xl">
                      {overrides.length > 0 ? (
                        <div className="space-y-2">
                          {overrides.map((o) => (
                            <div key={`${o.entity_type}-${o.name}`} className="flex items-center justify-between bg-white rounded-lg p-3 border border-gray-100">
                              <div className="flex items-center gap-2">
                                <Badge variant="info" size="sm">{o.entity_type}</Badge>
                                <span className="text-sm font-medium text-gray-900">{o.name}</span>
                                {o.is_append && (
                                  <Badge variant="warning" size="sm">Append</Badge>
                                )}
                              </div>
                              <button
                                onClick={() => handleRemoveOverride(ws.workspace_id, o.entity_type, o.name)}
                                className="p-1 text-red-400 hover:text-red-600 rounded transition-colors"
                              >
                                <XCircle className="w-4 h-4" />
                              </button>
                            </div>
                          ))}
                          <button
                            onClick={() => handleResetOverrides(ws.workspace_id)}
                            disabled={saving}
                            className="w-full mt-2 text-xs text-red-600 hover:text-red-800 font-medium py-2 border border-red-200 rounded-lg hover:bg-red-50 transition-colors disabled:opacity-50"
                          >
                            Reset All Overrides
                          </button>
                        </div>
                      ) : (
                        <p className="text-sm text-gray-400 text-center py-4">No overrides in this workspace</p>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {!isLoading && workspaces.length === 0 && (
            <div className="text-center py-12">
              <Layers className="w-12 h-12 text-gray-300 mx-auto mb-4" />
              <p className="text-gray-500">No workspaces found.</p>
              <p className="text-sm text-gray-400 mt-1">Create your first workspace to get started.</p>
            </div>
          )}
        </div>
      </main>

      {/* ─── New Workspace Modal ─── */}
      <Modal
        isOpen={showNewModal}
        onClose={() => setShowNewModal(false)}
        title="Create New Workspace"
        size="md"
        footer={
          <div className="flex justify-end gap-3">
            <button onClick={() => setShowNewModal(false)} className="px-4 py-2 text-gray-600 hover:text-gray-800">
              Cancel
            </button>
            <button
              onClick={handleCreate}
              disabled={saving || !newWs.name.trim()}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
            >
              {saving ? 'Creating...' : 'Create Workspace'}
            </button>
          </div>
        }
      >
        <form className="space-y-4" onSubmit={(e) => e.preventDefault()}>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Name *</label>
            <input
              type="text"
              placeholder="e.g., Development, Testing, Production"
              value={newWs.name}
              onChange={(e) => setNewWs(p => ({ ...p, name: e.target.value }))}
              className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
            <textarea
              rows={2}
              placeholder="Describe the purpose of this workspace..."
              value={newWs.description}
              onChange={(e) => setNewWs(p => ({ ...p, description: e.target.value }))}
              className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 resize-none"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Visibility</label>
            <select
              value={newWs.visibility}
              onChange={(e) => setNewWs(p => ({ ...p, visibility: e.target.value }))}
              className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 bg-white"
            >
              <option value="private">Private</option>
              <option value="tenant">Tenant</option>
              <option value="public">Public</option>
            </select>
          </div>

          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={newWs.is_active}
              onChange={(e) => setNewWs(p => ({ ...p, is_active: e.target.checked }))}
              className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            />
            <span className="text-sm text-gray-700">Make active immediately</span>
          </label>
        </form>
      </Modal>
    </div>
    </AuthGuard>
  );
}
