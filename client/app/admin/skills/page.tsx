'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  Plus, Search, Bot, Trash2, Zap, Brain, Loader2, AlertCircle, RefreshCw,
  Play, Pause, Package, Send, CheckCircle2, Eye, Edit2, XCircle, Save, History,
} from 'lucide-react';
import AuthGuard from '@/components/auth/auth-guard';
import TopNav from '@/components/layout/top-nav';
import PageHeader from '@/components/layout/page-header';
import Badge from '@/components/ui/badge';
import Modal from '@/components/ui/modal';
import { Tabs, TabPanel } from '@/components/ui/tabs';
import { useAuth } from '@/contexts/auth-context';
import { pluginApi, promptApi, skillApi } from '@/lib/admin-api';
import type { PluginEntity, PromptOverride, CustomSkill, SkillStatus } from '@/types/admin';

// ---------------------------------------------------------------------------
// Status helpers
// ---------------------------------------------------------------------------

const statusConfig: Record<SkillStatus, { label: string; color: string; icon: React.ReactNode }> = {
  draft: { label: 'Draft', color: 'bg-amber-100 text-amber-700', icon: <Edit2 className="w-3 h-3" /> },
  review: { label: 'In Review', color: 'bg-blue-100 text-blue-700', icon: <Eye className="w-3 h-3" /> },
  active: { label: 'Active', color: 'bg-green-100 text-green-700', icon: <Play className="w-3 h-3" /> },
  disabled: { label: 'Disabled', color: 'bg-gray-100 text-gray-500', icon: <Pause className="w-3 h-3" /> },
};

function formatDate(d: string): string {
  return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function SkillsPage() {
  const { getToken } = useAuth();

  // Data state
  const [pluginAgents, setPluginAgents] = useState<PluginEntity[]>([]);
  const [promptOverrides, setPromptOverrides] = useState<PromptOverride[]>([]);
  const [pluginSkills, setPluginSkills] = useState<PluginEntity[]>([]);
  const [customSkills, setCustomSkills] = useState<CustomSkill[]>([]);

  // UI state
  const [activeTab, setActiveTab] = useState('skills');
  const [searchQuery, setSearchQuery] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Notifications
  const [notification, setNotification] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // Auto-dismiss notifications
  useEffect(() => {
    if (!notification) return;
    const t = setTimeout(() => setNotification(null), 5000);
    return () => clearTimeout(t);
  }, [notification]);

  // Modals
  const [selectedPluginSkill, setSelectedPluginSkill] = useState<PluginEntity | null>(null);
  const [selectedCustomSkill, setSelectedCustomSkill] = useState<CustomSkill | null>(null);
  const [selectedAgent, setSelectedAgent] = useState<PluginEntity | null>(null);
  const [showNewSkillModal, setShowNewSkillModal] = useState(false);

  // Prompt editing — single unified editor
  const [promptBody, setPromptBody] = useState('');
  const [promptDirty, setPromptDirty] = useState(false);

  // New skill form
  const [newSkill, setNewSkill] = useState({
    name: '', display_name: '', description: '', prompt_body: '',
    triggers: '', tools: '', model: '', visibility: 'private',
  });

  // -----------------------------------------------------------------------
  // Data fetching
  // -----------------------------------------------------------------------

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [agents, skills, overrides, custom] = await Promise.all([
        pluginApi.list(getToken, 'agents'),
        pluginApi.list(getToken, 'skills'),
        promptApi.list(getToken),
        skillApi.list(getToken),
      ]);
      setPluginAgents(agents);
      setPluginSkills(skills);
      setPromptOverrides(overrides);
      setCustomSkills(custom);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data');
    } finally {
      setIsLoading(false);
    }
  }, [getToken]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // -----------------------------------------------------------------------
  // Tab counts
  // -----------------------------------------------------------------------

  const tabs = [
    { id: 'skills', label: 'Skills', icon: <Zap className="w-4 h-4" />, badge: pluginSkills.length + customSkills.length },
    { id: 'prompts', label: 'Agent Prompts', icon: <Brain className="w-4 h-4" />, badge: pluginAgents.length },
  ];

  // -----------------------------------------------------------------------
  // Filtering
  // -----------------------------------------------------------------------

  const q = searchQuery.toLowerCase();
  const filteredPluginSkills = pluginSkills.filter(s =>
    s.name.toLowerCase().includes(q) || (s.metadata?.description as string || '').toLowerCase().includes(q),
  );
  const filteredCustomSkills = customSkills.filter(s =>
    s.name.toLowerCase().includes(q) || s.display_name.toLowerCase().includes(q) || s.description.toLowerCase().includes(q),
  );
  const filteredAgents = pluginAgents.filter(a =>
    a.name.toLowerCase().includes(q) || (a.metadata?.description as string || '').toLowerCase().includes(q),
  );

  // -----------------------------------------------------------------------
  // Prompt helpers
  // -----------------------------------------------------------------------

  function getOverrideForAgent(agentName: string): PromptOverride | undefined {
    return promptOverrides.find(o => o.agent_name === agentName);
  }

  /** Get the effective prompt content: override body if exists, otherwise base content. */
  function getEffectivePrompt(agent: PluginEntity): string {
    const override = getOverrideForAgent(agent.name);
    return override ? override.prompt_body : agent.content;
  }

  /** Get the effective version number for display. */
  function getEffectiveVersion(agent: PluginEntity): number {
    const override = getOverrideForAgent(agent.name);
    return override ? override.version : agent.version;
  }

  /** Format version label: "v1 2026-01-15 (base)" or "v3 2026-03-04" */
  function formatVersionLabel(agent: PluginEntity): string {
    const override = getOverrideForAgent(agent.name);
    if (!override) {
      return `v${agent.version} ${formatDate(agent.updated_at)} (base prompt)`;
    }
    return `v${override.version} ${formatDate(override.updated_at)}`;
  }

  /** Build the version timeline string. */
  function getVersionTimeline(agent: PluginEntity): string {
    const override = getOverrideForAgent(agent.name);
    const basePart = `v${agent.version} ${formatDate(agent.created_at)} (base)`;
    if (!override) return basePart;
    return `${basePart} → v${override.version} ${formatDate(override.updated_at)}`;
  }

  function openAgentModal(agent: PluginEntity) {
    setSelectedAgent(agent);
    setPromptBody(getEffectivePrompt(agent));
    setPromptDirty(false);
  }

  async function savePrompt() {
    if (!selectedAgent || !promptBody.trim()) return;
    setSaving(true);
    try {
      // Save as a full replacement (is_append=false) since it's a single unified editor
      await promptApi.set(getToken, selectedAgent.name, { prompt_body: promptBody, is_append: false });
      const override = getOverrideForAgent(selectedAgent.name);
      const newVersion = (override?.version || selectedAgent.version) + 1;
      setNotification({
        type: 'success',
        message: `Prompt for "${selectedAgent.name}" saved as v${newVersion} (${new Date().toLocaleDateString('en-US', { year: 'numeric', month: '2-digit', day: '2-digit' })})`,
      });
      setSelectedAgent(null);
      await fetchData();
    } catch (err) {
      setNotification({
        type: 'error',
        message: err instanceof Error ? err.message : 'Failed to save prompt',
      });
    } finally {
      setSaving(false);
    }
  }

  async function resetToBase() {
    if (!selectedAgent) return;
    const override = getOverrideForAgent(selectedAgent.name);
    if (!override) return;
    setSaving(true);
    try {
      await promptApi.delete(getToken, selectedAgent.name);
      setNotification({
        type: 'success',
        message: `Prompt for "${selectedAgent.name}" reset to base prompt (v${selectedAgent.version})`,
      });
      setSelectedAgent(null);
      await fetchData();
    } catch (err) {
      setNotification({
        type: 'error',
        message: err instanceof Error ? err.message : 'Failed to reset prompt',
      });
    } finally {
      setSaving(false);
    }
  }

  // -----------------------------------------------------------------------
  // Custom skill actions
  // -----------------------------------------------------------------------

  async function handleCreateSkill() {
    setSaving(true);
    try {
      await skillApi.create(getToken, {
        name: newSkill.name,
        display_name: newSkill.display_name,
        description: newSkill.description,
        prompt_body: newSkill.prompt_body,
        triggers: newSkill.triggers ? newSkill.triggers.split(',').map(t => t.trim()) : [],
        tools: newSkill.tools ? newSkill.tools.split(',').map(t => t.trim()) : [],
        model: newSkill.model || undefined,
        visibility: newSkill.visibility,
      });
      setShowNewSkillModal(false);
      setNewSkill({ name: '', display_name: '', description: '', prompt_body: '', triggers: '', tools: '', model: '', visibility: 'private' });
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create skill');
    } finally {
      setSaving(false);
    }
  }

  async function handleSubmitSkill(id: string) {
    try {
      await skillApi.submit(getToken, id);
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to submit skill');
    }
  }

  async function handlePublishSkill(id: string) {
    try {
      await skillApi.publish(getToken, id);
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to publish skill');
    }
  }

  async function handleDeleteSkill(id: string) {
    try {
      await skillApi.delete(getToken, id);
      setSelectedCustomSkill(null);
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete skill');
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
            title="Agent Skills & Prompts"
            description="Configure AI agent capabilities and system prompts"
            breadcrumbs={[
              { label: 'Admin', href: '/admin' },
              { label: 'Agent Skills' },
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
                  onClick={() => setShowNewSkillModal(true)}
                  className="flex items-center gap-2 px-4 py-2.5 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700 transition-colors shadow-md shadow-blue-200"
                >
                  <Plus className="w-4 h-4" />
                  New Skill
                </button>
              </div>
            }
          />

          {/* Tabs */}
          <div className="mb-6">
            <Tabs tabs={tabs} activeTab={activeTab} onChange={setActiveTab} variant="pills" />
          </div>

          {/* Search */}
          <div className="mb-6">
            <div className="relative max-w-md">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                placeholder={activeTab === 'skills' ? 'Search skills...' : 'Search agent prompts...'}
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

          {/* Notification */}
          {notification && (
            <div className={`mb-6 flex items-center gap-3 p-4 rounded-xl border ${
              notification.type === 'success'
                ? 'bg-green-50 border-green-200 text-green-700'
                : 'bg-red-50 border-red-200 text-red-700'
            }`}>
              {notification.type === 'success' ? (
                <CheckCircle2 className="w-5 h-5 flex-shrink-0" />
              ) : (
                <AlertCircle className="w-5 h-5 flex-shrink-0" />
              )}
              <p className="flex-1 text-sm font-medium">{notification.message}</p>
              <button onClick={() => setNotification(null)} className="text-xs opacity-60 hover:opacity-100">
                <XCircle className="w-4 h-4" />
              </button>
            </div>
          )}

          {/* Loading */}
          {isLoading && (
            <div className="flex flex-col items-center justify-center py-20">
              <Loader2 className="w-8 h-8 text-[#003149] animate-spin mb-4" />
              <p className="text-gray-500 text-sm">Loading data...</p>
            </div>
          )}

          {/* ─── Skills Tab ─── */}
          {!isLoading && (
            <TabPanel isActive={activeTab === 'skills'}>
              {/* Bundled Skills Section */}
              {filteredPluginSkills.length > 0 && (
                <>
                  <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">Bundled Skills</h3>
                  <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 mb-8">
                    {filteredPluginSkills.map((skill) => (
                      <div
                        key={skill.name}
                        className="bg-white rounded-2xl border border-gray-200 p-5 hover:border-blue-300 hover:shadow-lg transition-all cursor-pointer group"
                        onClick={() => setSelectedPluginSkill(skill)}
                      >
                        <div className="flex items-start justify-between mb-3">
                          <div className="p-3 rounded-xl bg-gray-100">
                            <Package className="w-6 h-6 text-gray-600" />
                          </div>
                          <span className="text-[10px] font-bold uppercase px-2 py-1 rounded-full bg-gray-100 text-gray-500">
                            Bundled
                          </span>
                        </div>
                        <h3 className="font-semibold text-gray-900 mb-1 group-hover:text-blue-600 transition-colors">
                          {skill.name}
                        </h3>
                        <p className="text-sm text-gray-500 mb-3 line-clamp-2">
                          {(skill.metadata?.description as string) || skill.content.slice(0, 120) + '...'}
                        </p>
                        <div className="pt-3 border-t border-gray-100 flex items-center justify-between text-xs text-gray-500">
                          <span>v{skill.version}</span>
                          <span>{formatDate(skill.updated_at)}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              )}

              {/* Custom Skills Section */}
              {filteredCustomSkills.length > 0 && (
                <>
                  <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">Custom Skills</h3>
                  <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 mb-8">
                    {filteredCustomSkills.map((skill) => {
                      const cfg = statusConfig[skill.status];
                      return (
                        <div
                          key={skill.skill_id}
                          className="bg-white rounded-2xl border border-gray-200 p-5 hover:border-blue-300 hover:shadow-lg transition-all cursor-pointer group"
                          onClick={() => setSelectedCustomSkill(skill)}
                        >
                          <div className="flex items-start justify-between mb-3">
                            <div className="p-3 rounded-xl bg-purple-100">
                              <Bot className="w-6 h-6 text-purple-600" />
                            </div>
                            <span className={`flex items-center gap-1 text-[10px] font-bold uppercase px-2 py-1 rounded-full ${cfg.color}`}>
                              {cfg.icon}
                              {cfg.label}
                            </span>
                          </div>
                          <h3 className="font-semibold text-gray-900 mb-1 group-hover:text-blue-600 transition-colors">
                            {skill.display_name || skill.name}
                          </h3>
                          <p className="text-sm text-gray-500 mb-3 line-clamp-2">{skill.description}</p>
                          {skill.triggers.length > 0 && (
                            <div className="flex flex-wrap gap-1 mb-3">
                              {skill.triggers.slice(0, 3).map((t) => (
                                <span key={t} className="text-[10px] bg-blue-50 text-blue-600 px-1.5 py-0.5 rounded">{t}</span>
                              ))}
                              {skill.triggers.length > 3 && (
                                <span className="text-[10px] text-gray-400">+{skill.triggers.length - 3}</span>
                              )}
                            </div>
                          )}
                          <div className="pt-3 border-t border-gray-100 flex items-center justify-between text-xs text-gray-500">
                            <span>v{skill.version}</span>
                            <div className="flex gap-2">
                              {skill.status === 'draft' && (
                                <button
                                  onClick={(e) => { e.stopPropagation(); handleSubmitSkill(skill.skill_id); }}
                                  className="text-blue-600 hover:text-blue-800 font-medium flex items-center gap-1"
                                >
                                  <Send className="w-3 h-3" /> Submit
                                </button>
                              )}
                              {skill.status === 'review' && (
                                <button
                                  onClick={(e) => { e.stopPropagation(); handlePublishSkill(skill.skill_id); }}
                                  className="text-green-600 hover:text-green-800 font-medium flex items-center gap-1"
                                >
                                  <CheckCircle2 className="w-3 h-3" /> Publish
                                </button>
                              )}
                              {(skill.status === 'draft' || skill.status === 'disabled') && (
                                <button
                                  onClick={(e) => { e.stopPropagation(); handleDeleteSkill(skill.skill_id); }}
                                  className="text-red-500 hover:text-red-700 font-medium flex items-center gap-1"
                                >
                                  <Trash2 className="w-3 h-3" /> Delete
                                </button>
                              )}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </>
              )}

              {filteredPluginSkills.length === 0 && filteredCustomSkills.length === 0 && (
                <div className="text-center py-12">
                  <Bot className="w-12 h-12 text-gray-300 mx-auto mb-4" />
                  <p className="text-gray-500">No skills found.</p>
                </div>
              )}
            </TabPanel>
          )}

          {/* ─── Prompts Tab ─── */}
          {!isLoading && (
            <TabPanel isActive={activeTab === 'prompts'}>
              <div className="space-y-4">
                {filteredAgents.map((agent) => {
                  const override = getOverrideForAgent(agent.name);
                  const effectiveVersion = getEffectiveVersion(agent);
                  return (
                    <div
                      key={agent.name}
                      className="bg-white rounded-xl border border-gray-200 p-5 hover:border-blue-300 hover:shadow-md transition-all cursor-pointer group"
                      onClick={() => openAgentModal(agent)}
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex items-start gap-4">
                          <div className="p-3 bg-purple-100 rounded-xl">
                            <Brain className="w-6 h-6 text-purple-600" />
                          </div>
                          <div>
                            <h3 className="font-semibold text-gray-900 group-hover:text-blue-600 transition-colors">
                              {agent.name}
                            </h3>
                            <div className="flex items-center gap-3 mt-1">
                              <span className="text-xs text-gray-500">{(agent.metadata?.description as string) || agent.entity_type}</span>
                            </div>
                            {/* Version timeline */}
                            <div className="flex items-center gap-1.5 mt-1.5">
                              <History className="w-3 h-3 text-gray-400" />
                              <span className="text-[11px] text-gray-400 font-mono">
                                {getVersionTimeline(agent)}
                              </span>
                            </div>
                          </div>
                        </div>
                        <div className="flex flex-col items-end gap-1.5">
                          {override ? (
                            <Badge variant="warning" size="sm">Edited v{override.version}</Badge>
                          ) : (
                            <Badge variant="default" size="sm">Base v{agent.version}</Badge>
                          )}
                          <span className="text-[10px] text-gray-400">
                            {formatDate(override ? override.updated_at : agent.updated_at)}
                          </span>
                        </div>
                      </div>
                      <div className="mt-3 ml-16">
                        <p className="text-sm text-gray-600 line-clamp-2 font-mono">
                          {getEffectivePrompt(agent).slice(0, 200)}...
                        </p>
                      </div>
                    </div>
                  );
                })}
              </div>

              {filteredAgents.length === 0 && (
                <div className="text-center py-12">
                  <Brain className="w-12 h-12 text-gray-300 mx-auto mb-4" />
                  <p className="text-gray-500">No agent prompts found.</p>
                </div>
              )}
            </TabPanel>
          )}
        </div>
      </main>

      {/* ─── Bundled Skill View Modal ─── */}
      <Modal
        isOpen={!!selectedPluginSkill}
        onClose={() => setSelectedPluginSkill(null)}
        title={selectedPluginSkill ? `Bundled Skill: ${selectedPluginSkill.name}` : ''}
        size="lg"
      >
        {selectedPluginSkill && (
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <Badge variant="default" size="sm">Bundled (Read-Only)</Badge>
              <span className="text-xs text-gray-400">v{selectedPluginSkill.version}</span>
            </div>
            {typeof selectedPluginSkill.metadata?.description === 'string' && (
              <p className="text-sm text-gray-600">{selectedPluginSkill.metadata.description}</p>
            )}
            <div>
              <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Content</h4>
              <div className="bg-gray-900 rounded-xl p-4 overflow-x-auto max-h-96 overflow-y-auto">
                <pre className="text-sm text-gray-100 whitespace-pre-wrap font-mono">
                  {selectedPluginSkill.content}
                </pre>
              </div>
            </div>
            {Object.keys(selectedPluginSkill.metadata || {}).length > 0 && (
              <div>
                <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Metadata</h4>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(selectedPluginSkill.metadata).map(([k, v]) => (
                    k !== 'description' && (
                      <span key={k} className="text-xs bg-gray-100 text-gray-600 px-2 py-1 rounded-lg">
                        {k}: {typeof v === 'string' ? v : JSON.stringify(v)}
                      </span>
                    )
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </Modal>

      {/* ─── Custom Skill Detail Modal ─── */}
      <Modal
        isOpen={!!selectedCustomSkill}
        onClose={() => setSelectedCustomSkill(null)}
        title={selectedCustomSkill ? `Custom Skill: ${selectedCustomSkill.display_name || selectedCustomSkill.name}` : ''}
        size="lg"
        footer={selectedCustomSkill && (
          <div className="flex justify-between">
            {(selectedCustomSkill.status === 'draft' || selectedCustomSkill.status === 'disabled') && (
              <button
                onClick={() => handleDeleteSkill(selectedCustomSkill.skill_id)}
                className="flex items-center gap-2 px-4 py-2 text-red-600 hover:text-red-700"
              >
                <Trash2 className="w-4 h-4" />
                Delete
              </button>
            )}
            <div className="flex gap-3 ml-auto">
              <button onClick={() => setSelectedCustomSkill(null)} className="px-4 py-2 text-gray-600 hover:text-gray-800">
                Close
              </button>
              {selectedCustomSkill.status === 'draft' && (
                <button
                  onClick={() => handleSubmitSkill(selectedCustomSkill.skill_id)}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                >
                  Submit for Review
                </button>
              )}
              {selectedCustomSkill.status === 'review' && (
                <button
                  onClick={() => handlePublishSkill(selectedCustomSkill.skill_id)}
                  className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700"
                >
                  Publish
                </button>
              )}
            </div>
          </div>
        )}
      >
        {selectedCustomSkill && (
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              {(() => {
                const cfg = statusConfig[selectedCustomSkill.status];
                return (
                  <span className={`flex items-center gap-1 text-xs font-bold uppercase px-2 py-1 rounded-full ${cfg.color}`}>
                    {cfg.icon} {cfg.label}
                  </span>
                );
              })()}
              <span className="text-xs text-gray-400">v{selectedCustomSkill.version}</span>
              <span className="text-xs text-gray-400">{selectedCustomSkill.visibility}</span>
            </div>

            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-gray-500">Name:</span>{' '}
                <span className="font-medium">{selectedCustomSkill.name}</span>
              </div>
              <div>
                <span className="text-gray-500">Display Name:</span>{' '}
                <span className="font-medium">{selectedCustomSkill.display_name}</span>
              </div>
            </div>

            <div>
              <p className="text-sm text-gray-600">{selectedCustomSkill.description}</p>
            </div>

            {selectedCustomSkill.triggers.length > 0 && (
              <div>
                <h4 className="text-xs font-semibold text-gray-500 uppercase mb-1">Triggers</h4>
                <div className="flex flex-wrap gap-1">
                  {selectedCustomSkill.triggers.map((t) => (
                    <span key={t} className="text-xs bg-blue-50 text-blue-700 px-2 py-1 rounded-lg">{t}</span>
                  ))}
                </div>
              </div>
            )}

            {selectedCustomSkill.tools.length > 0 && (
              <div>
                <h4 className="text-xs font-semibold text-gray-500 uppercase mb-1">Tools</h4>
                <div className="flex flex-wrap gap-1">
                  {selectedCustomSkill.tools.map((t) => (
                    <span key={t} className="text-xs bg-purple-50 text-purple-700 px-2 py-1 rounded-lg">{t}</span>
                  ))}
                </div>
              </div>
            )}

            <div>
              <h4 className="text-xs font-semibold text-gray-500 uppercase mb-2">Prompt Body</h4>
              <div className="bg-gray-900 rounded-xl p-4 overflow-x-auto max-h-64 overflow-y-auto">
                <pre className="text-sm text-gray-100 whitespace-pre-wrap font-mono">
                  {selectedCustomSkill.prompt_body}
                </pre>
              </div>
            </div>
          </div>
        )}
      </Modal>

      {/* ─── Agent Prompt Editor Modal ─── */}
      <Modal
        isOpen={!!selectedAgent}
        onClose={() => setSelectedAgent(null)}
        title={selectedAgent ? `Edit Prompt: ${selectedAgent.name}` : ''}
        size="xl"
        footer={selectedAgent && (
          <div className="flex justify-between">
            {getOverrideForAgent(selectedAgent.name) && (
              <button
                onClick={resetToBase}
                disabled={saving}
                className="flex items-center gap-2 px-4 py-2 text-amber-600 hover:text-amber-700 disabled:opacity-50"
              >
                <History className="w-4 h-4" />
                Reset to Base
              </button>
            )}
            <div className="flex gap-3 ml-auto">
              <button onClick={() => setSelectedAgent(null)} className="px-4 py-2 text-gray-600 hover:text-gray-800">
                Cancel
              </button>
              <button
                onClick={savePrompt}
                disabled={saving || !promptBody.trim() || !promptDirty}
                className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
              >
                <Save className="w-4 h-4" />
                {saving ? 'Saving...' : 'Save Prompt'}
              </button>
            </div>
          </div>
        )}
      >
        {selectedAgent && (() => {
          const override = getOverrideForAgent(selectedAgent.name);
          const currentVersion = override ? override.version : selectedAgent.version;
          return (
            <div className="space-y-4">
              {/* Version info bar */}
              <div className="flex items-center justify-between bg-gray-50 rounded-xl px-4 py-3 border border-gray-200">
                <div className="flex items-center gap-3">
                  <History className="w-4 h-4 text-gray-400" />
                  <div>
                    <span className="text-sm font-medium text-gray-700">
                      {formatVersionLabel(selectedAgent)}
                    </span>
                    {override && (
                      <span className="text-xs text-gray-400 ml-2">
                        (base: v{selectedAgent.version} {formatDate(selectedAgent.created_at)})
                      </span>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {override ? (
                    <Badge variant="warning" size="sm">Edited</Badge>
                  ) : (
                    <Badge variant="default" size="sm">Base Prompt</Badge>
                  )}
                  {promptDirty && (
                    <Badge variant="info" size="sm">Unsaved Changes</Badge>
                  )}
                </div>
              </div>

              {/* Version timeline */}
              <div className="flex items-center gap-2 text-xs text-gray-400 px-1">
                <span className="font-mono">{getVersionTimeline(selectedAgent)}</span>
                {promptDirty && (
                  <span className="font-mono text-blue-500">→ v{currentVersion + 1} (pending save)</span>
                )}
              </div>

              {/* Single unified editor */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">System Prompt</label>
                <textarea
                  value={promptBody}
                  onChange={(e) => {
                    setPromptBody(e.target.value);
                    setPromptDirty(true);
                  }}
                  rows={20}
                  className="w-full px-4 py-3 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 font-mono text-sm resize-y min-h-[300px]"
                />
              </div>
            </div>
          );
        })()}
      </Modal>

      {/* ─── New Custom Skill Modal ─── */}
      <Modal
        isOpen={showNewSkillModal}
        onClose={() => setShowNewSkillModal(false)}
        title="Create Custom Skill"
        size="lg"
        footer={
          <div className="flex justify-end gap-3">
            <button onClick={() => setShowNewSkillModal(false)} className="px-4 py-2 text-gray-600 hover:text-gray-800">
              Cancel
            </button>
            <button
              onClick={handleCreateSkill}
              disabled={saving || !newSkill.name || !newSkill.display_name || !newSkill.prompt_body}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
            >
              {saving ? 'Creating...' : 'Create Skill'}
            </button>
          </div>
        }
      >
        <form className="space-y-4" onSubmit={(e) => e.preventDefault()}>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Skill Name *</label>
              <input
                type="text"
                placeholder="e.g., document-summarizer"
                value={newSkill.name}
                onChange={(e) => setNewSkill(p => ({ ...p, name: e.target.value }))}
                className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Display Name *</label>
              <input
                type="text"
                placeholder="e.g., Document Summarizer"
                value={newSkill.display_name}
                onChange={(e) => setNewSkill(p => ({ ...p, display_name: e.target.value }))}
                className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
            <textarea
              rows={2}
              placeholder="Describe what this skill does..."
              value={newSkill.description}
              onChange={(e) => setNewSkill(p => ({ ...p, description: e.target.value }))}
              className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 resize-none"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Prompt Body *</label>
            <textarea
              rows={6}
              placeholder="Enter the prompt template for this skill..."
              value={newSkill.prompt_body}
              onChange={(e) => setNewSkill(p => ({ ...p, prompt_body: e.target.value }))}
              className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 font-mono text-sm resize-none"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Triggers (comma-separated)</label>
              <input
                type="text"
                placeholder="summarize, tldr, digest"
                value={newSkill.triggers}
                onChange={(e) => setNewSkill(p => ({ ...p, triggers: e.target.value }))}
                className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Tools (comma-separated)</label>
              <input
                type="text"
                placeholder="search_documents, create_document"
                value={newSkill.tools}
                onChange={(e) => setNewSkill(p => ({ ...p, tools: e.target.value }))}
                className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Model (optional)</label>
              <input
                type="text"
                placeholder="e.g., us.anthropic.claude-sonnet-4-20250514"
                value={newSkill.model}
                onChange={(e) => setNewSkill(p => ({ ...p, model: e.target.value }))}
                className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Visibility</label>
              <select
                value={newSkill.visibility}
                onChange={(e) => setNewSkill(p => ({ ...p, visibility: e.target.value }))}
                className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 bg-white"
              >
                <option value="private">Private</option>
                <option value="tenant">Tenant</option>
                <option value="public">Public</option>
              </select>
            </div>
          </div>
        </form>
      </Modal>
    </div>
    </AuthGuard>
  );
}
