'use client';

import { useState } from 'react';
import { Plus, Search, Bot, Edit2, Trash2, Play, Pause, Zap, Settings, Terminal, Brain } from 'lucide-react';
import AuthGuard from '@/components/auth/auth-guard';
import SidebarNav from '@/components/layout/sidebar-nav';
import PageHeader from '@/components/layout/page-header';
import Badge from '@/components/ui/badge';
import Modal from '@/components/ui/modal';
import { Tabs, TabPanel } from '@/components/ui/tabs';
import {
  MOCK_AGENT_SKILLS,
  MOCK_SYSTEM_PROMPTS,
  getSkillTypeColor,
  formatDate,
} from '@/lib/mock-data';
import { AgentSkill, SystemPrompt, SkillType, AgentRole } from '@/types/schema';

const skillTypeLabels: Record<SkillType, string> = {
  document_gen: 'Document Generation',
  data_extraction: 'Data Extraction',
  validation: 'Validation',
  search: 'Search',
};

const agentRoleLabels: Record<AgentRole, string> = {
  intake_agent: 'Intake Agent',
  document_agent: 'Document Agent',
  review_agent: 'Review Agent',
  orchestrator: 'Orchestrator',
};

const tabs = [
  { id: 'skills', label: 'Agent Skills', icon: <Zap className="w-4 h-4" />, badge: MOCK_AGENT_SKILLS.length },
  { id: 'prompts', label: 'System Prompts', icon: <Brain className="w-4 h-4" />, badge: MOCK_SYSTEM_PROMPTS.length },
];

export default function SkillsPage() {
  const [activeTab, setActiveTab] = useState('skills');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedSkill, setSelectedSkill] = useState<AgentSkill | null>(null);
  const [selectedPrompt, setSelectedPrompt] = useState<SystemPrompt | null>(null);
  const [showNewSkillModal, setShowNewSkillModal] = useState(false);

  const filteredSkills = MOCK_AGENT_SKILLS.filter(s =>
    s.skill_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    s.description?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const filteredPrompts = MOCK_SYSTEM_PROMPTS.filter(p =>
    p.prompt_name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <AuthGuard>
    <div className="flex h-screen bg-gray-50">
      <SidebarNav />

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
              <button
                onClick={() => setShowNewSkillModal(true)}
                className="flex items-center gap-2 px-4 py-2.5 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700 transition-colors shadow-md shadow-blue-200"
              >
                <Plus className="w-4 h-4" />
                New Skill
              </button>
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
                placeholder={activeTab === 'skills' ? 'Search skills...' : 'Search prompts...'}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-10 pr-4 py-2.5 bg-white border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
              />
            </div>
          </div>

          {/* Skills Tab */}
          <TabPanel isActive={activeTab === 'skills'}>
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {filteredSkills.map((skill) => (
                <div
                  key={skill.id}
                  className="bg-white rounded-2xl border border-gray-200 p-5 hover:border-blue-300 hover:shadow-lg transition-all cursor-pointer group"
                  onClick={() => setSelectedSkill(skill)}
                >
                  <div className="flex items-start justify-between mb-3">
                    <div className={`p-3 rounded-xl ${skill.is_active ? 'bg-purple-100' : 'bg-gray-100'}`}>
                      <Bot className={`w-6 h-6 ${skill.is_active ? 'text-purple-600' : 'text-gray-400'}`} />
                    </div>
                    <div className="flex items-center gap-2">
                      {skill.is_active ? (
                        <span className="flex items-center gap-1 text-[10px] font-bold uppercase px-2 py-1 rounded-full bg-green-100 text-green-700">
                          <Play className="w-3 h-3" />
                          Active
                        </span>
                      ) : (
                        <span className="flex items-center gap-1 text-[10px] font-bold uppercase px-2 py-1 rounded-full bg-gray-100 text-gray-500">
                          <Pause className="w-3 h-3" />
                          Inactive
                        </span>
                      )}
                    </div>
                  </div>

                  <h3 className="font-semibold text-gray-900 mb-1 group-hover:text-blue-600 transition-colors">
                    {skill.skill_name}
                  </h3>
                  <p className="text-sm text-gray-500 mb-3 line-clamp-2">{skill.description}</p>

                  <div className="flex items-center gap-2 mb-3">
                    <span className={`text-[10px] font-bold uppercase px-2 py-1 rounded-full ${getSkillTypeColor(skill.skill_type)}`}>
                      {skillTypeLabels[skill.skill_type]}
                    </span>
                  </div>

                  <div className="pt-3 border-t border-gray-100">
                    <div className="flex items-center justify-between text-xs text-gray-500">
                      <span>Model: {skill.config.model || 'default'}</span>
                      <span>Temp: {skill.config.temperature ?? 'default'}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {filteredSkills.length === 0 && (
              <div className="text-center py-12">
                <Bot className="w-12 h-12 text-gray-300 mx-auto mb-4" />
                <p className="text-gray-500">No skills found.</p>
              </div>
            )}
          </TabPanel>

          {/* Prompts Tab */}
          <TabPanel isActive={activeTab === 'prompts'}>
            <div className="space-y-4">
              {filteredPrompts.map((prompt) => (
                <div
                  key={prompt.id}
                  className="bg-white rounded-xl border border-gray-200 p-5 hover:border-blue-300 hover:shadow-md transition-all cursor-pointer group"
                  onClick={() => setSelectedPrompt(prompt)}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex items-start gap-4">
                      <div className="p-3 bg-purple-100 rounded-xl">
                        <Brain className="w-6 h-6 text-purple-600" />
                      </div>
                      <div>
                        <h3 className="font-semibold text-gray-900 group-hover:text-blue-600 transition-colors">
                          {prompt.prompt_name}
                        </h3>
                        <div className="flex items-center gap-3 mt-1">
                          <span className="text-xs text-gray-500">{agentRoleLabels[prompt.agent_role]}</span>
                          <span className="text-xs text-gray-400">v{prompt.version}</span>
                          <span className="text-xs text-gray-400">Updated {formatDate(prompt.updated_at)}</span>
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {prompt.is_active ? (
                        <Badge variant="success" size="sm">Active</Badge>
                      ) : (
                        <Badge variant="default" size="sm">Inactive</Badge>
                      )}
                    </div>
                  </div>
                  <div className="mt-3 ml-16">
                    <p className="text-sm text-gray-600 line-clamp-2">{prompt.content}</p>
                  </div>
                </div>
              ))}
            </div>

            {filteredPrompts.length === 0 && (
              <div className="text-center py-12">
                <Brain className="w-12 h-12 text-gray-300 mx-auto mb-4" />
                <p className="text-gray-500">No prompts found.</p>
              </div>
            )}
          </TabPanel>
        </div>
      </main>

      {/* Skill Edit Modal */}
      <Modal
        isOpen={!!selectedSkill}
        onClose={() => setSelectedSkill(null)}
        title={selectedSkill ? `Edit: ${selectedSkill.skill_name}` : 'Skill Details'}
        size="lg"
        footer={
          <div className="flex justify-between">
            <button className="flex items-center gap-2 px-4 py-2 text-red-600 hover:text-red-700">
              <Trash2 className="w-4 h-4" />
              Delete
            </button>
            <div className="flex gap-3">
              <button
                onClick={() => setSelectedSkill(null)}
                className="px-4 py-2 text-gray-600 hover:text-gray-800"
              >
                Cancel
              </button>
              <button className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
                Save Changes
              </button>
            </div>
          </div>
        }
      >
        {selectedSkill && (
          <form className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Skill Name</label>
                <input
                  type="text"
                  defaultValue={selectedSkill.skill_name}
                  className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Skill Type</label>
                <select
                  defaultValue={selectedSkill.skill_type}
                  className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 bg-white"
                >
                  {Object.entries(skillTypeLabels).map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
              <textarea
                defaultValue={selectedSkill.description}
                rows={2}
                className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 resize-none"
              />
            </div>

            <div className="p-4 bg-gray-50 rounded-xl space-y-4">
              <h4 className="font-medium text-gray-900 flex items-center gap-2">
                <Settings className="w-4 h-4" />
                Configuration
              </h4>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Model</label>
                  <select
                    defaultValue={selectedSkill.config.model}
                    className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 bg-white"
                  >
                    <option value="claude-3-opus">Claude 3 Opus</option>
                    <option value="claude-3-sonnet">Claude 3 Sonnet</option>
                    <option value="claude-3-haiku">Claude 3 Haiku</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Temperature</label>
                  <input
                    type="number"
                    step="0.1"
                    min="0"
                    max="1"
                    defaultValue={selectedSkill.config.temperature}
                    className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Enabled Tools</label>
                <div className="flex flex-wrap gap-2">
                  {selectedSkill.config.tools_enabled?.map((tool) => (
                    <span key={tool} className="text-xs bg-blue-100 text-blue-700 px-2 py-1 rounded-lg flex items-center gap-1">
                      <Terminal className="w-3 h-3" />
                      {tool}
                    </span>
                  ))}
                </div>
              </div>
            </div>

            {selectedSkill.prompt_template && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Prompt Template</label>
                <textarea
                  defaultValue={selectedSkill.prompt_template}
                  rows={4}
                  className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 font-mono text-sm resize-none"
                />
              </div>
            )}

            <div className="flex items-center gap-3">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  defaultChecked={selectedSkill.is_active}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700">Active (skill can be used by agents)</span>
              </label>
            </div>
          </form>
        )}
      </Modal>

      {/* Prompt Edit Modal */}
      <Modal
        isOpen={!!selectedPrompt}
        onClose={() => setSelectedPrompt(null)}
        title={selectedPrompt ? `Edit: ${selectedPrompt.prompt_name}` : 'Prompt Details'}
        size="lg"
        footer={
          <div className="flex justify-end gap-3">
            <button
              onClick={() => setSelectedPrompt(null)}
              className="px-4 py-2 text-gray-600 hover:text-gray-800"
            >
              Cancel
            </button>
            <button className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
              Save Changes
            </button>
          </div>
        }
      >
        {selectedPrompt && (
          <form className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Prompt Name</label>
                <input
                  type="text"
                  defaultValue={selectedPrompt.prompt_name}
                  className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Agent Role</label>
                <select
                  defaultValue={selectedPrompt.agent_role}
                  className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 bg-white"
                >
                  {Object.entries(agentRoleLabels).map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">System Prompt Content</label>
              <textarea
                defaultValue={selectedPrompt.content}
                rows={12}
                className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 font-mono text-sm resize-none"
              />
            </div>

            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-500">Version {selectedPrompt.version}</span>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  defaultChecked={selectedPrompt.is_active}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700">Active</span>
              </label>
            </div>
          </form>
        )}
      </Modal>

      {/* New Skill Modal */}
      <Modal
        isOpen={showNewSkillModal}
        onClose={() => setShowNewSkillModal(false)}
        title="Create New Skill"
        size="lg"
        footer={
          <div className="flex justify-end gap-3">
            <button
              onClick={() => setShowNewSkillModal(false)}
              className="px-4 py-2 text-gray-600 hover:text-gray-800"
            >
              Cancel
            </button>
            <button className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
              Create Skill
            </button>
          </div>
        }
      >
        <form className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Skill Name *</label>
              <input
                type="text"
                placeholder="e.g., Document Summarizer"
                className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Skill Type *</label>
              <select className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 bg-white">
                <option value="">Select type...</option>
                {Object.entries(skillTypeLabels).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
            <textarea
              rows={2}
              placeholder="Describe what this skill does..."
              className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 resize-none"
            />
          </div>

          <div className="p-4 bg-gray-50 rounded-xl space-y-4">
            <h4 className="font-medium text-gray-900 flex items-center gap-2">
              <Settings className="w-4 h-4" />
              Configuration
            </h4>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Model</label>
                <select className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 bg-white">
                  <option value="claude-3-opus">Claude 3 Opus</option>
                  <option value="claude-3-sonnet">Claude 3 Sonnet</option>
                  <option value="claude-3-haiku">Claude 3 Haiku</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Temperature</label>
                <input
                  type="number"
                  step="0.1"
                  min="0"
                  max="1"
                  defaultValue="0.3"
                  className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
                />
              </div>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Prompt Template</label>
            <textarea
              rows={4}
              placeholder="Enter the prompt template for this skill..."
              className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 font-mono text-sm resize-none"
            />
          </div>

          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                defaultChecked={true}
                className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              />
              <span className="text-sm text-gray-700">Make active immediately</span>
            </label>
          </div>
        </form>
      </Modal>
    </div>
    </AuthGuard>
  );
}
