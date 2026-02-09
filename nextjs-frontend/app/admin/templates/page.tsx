'use client';

import { useState } from 'react';
import { Plus, Search, FileStack, Edit2, Trash2, Copy, Eye, Code, CheckCircle2, XCircle } from 'lucide-react';
import AuthGuard from '@/components/auth/auth-guard';
import SidebarNav from '@/components/layout/sidebar-nav';
import PageHeader from '@/components/layout/page-header';
import Badge from '@/components/ui/badge';
import Modal from '@/components/ui/modal';
import {
  MOCK_DOCUMENT_TEMPLATES,
  formatDate,
} from '@/lib/mock-data';
import { DocumentTemplate, DocumentType } from '@/types/schema';

const documentTypeLabels: Record<DocumentType, string> = {
  sow: 'Statement of Work',
  igce: 'Cost Estimate (IGCE)',
  market_research: 'Market Research',
  acquisition_plan: 'Acquisition Plan',
  justification: 'Justification',
  funding_doc: 'Funding Document',
};

const documentTypeColors: Record<DocumentType, string> = {
  sow: 'bg-blue-100 text-blue-700',
  igce: 'bg-green-100 text-green-700',
  market_research: 'bg-purple-100 text-purple-700',
  acquisition_plan: 'bg-amber-100 text-amber-700',
  justification: 'bg-red-100 text-red-700',
  funding_doc: 'bg-cyan-100 text-cyan-700',
};

export default function TemplatesPage() {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedTemplate, setSelectedTemplate] = useState<DocumentTemplate | null>(null);
  const [showNewModal, setShowNewModal] = useState(false);
  const [showPreviewModal, setShowPreviewModal] = useState(false);
  const [previewTemplate, setPreviewTemplate] = useState<DocumentTemplate | null>(null);

  const filteredTemplates = MOCK_DOCUMENT_TEMPLATES.filter(t =>
    t.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    t.description?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const handlePreview = (template: DocumentTemplate, e: React.MouseEvent) => {
    e.stopPropagation();
    setPreviewTemplate(template);
    setShowPreviewModal(true);
  };

  return (
    <AuthGuard>
    <div className="flex h-screen bg-gray-50">
      <SidebarNav />

      <main className="flex-1 overflow-y-auto">
        <div className="p-8">
          <PageHeader
            title="Document Templates"
            description="Manage reusable document templates"
            breadcrumbs={[
              { label: 'Admin', href: '/admin' },
              { label: 'Templates' },
            ]}
            actions={
              <button
                onClick={() => setShowNewModal(true)}
                className="flex items-center gap-2 px-4 py-2.5 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700 transition-colors shadow-md shadow-blue-200"
              >
                <Plus className="w-4 h-4" />
                New Template
              </button>
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

          {/* Templates Grid */}
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {filteredTemplates.map((template) => (
              <div
                key={template.id}
                className="bg-white rounded-2xl border border-gray-200 p-5 hover:border-blue-300 hover:shadow-lg transition-all cursor-pointer group"
                onClick={() => setSelectedTemplate(template)}
              >
                <div className="flex items-start justify-between mb-3">
                  <div className="p-3 bg-gray-100 rounded-xl group-hover:bg-blue-50 transition-colors">
                    <FileStack className="w-6 h-6 text-gray-600 group-hover:text-blue-600" />
                  </div>
                  <div className="flex items-center gap-2">
                    {template.is_active ? (
                      <span className="flex items-center gap-1 text-[10px] font-bold uppercase px-2 py-1 rounded-full bg-green-100 text-green-700">
                        <CheckCircle2 className="w-3 h-3" />
                        Active
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-[10px] font-bold uppercase px-2 py-1 rounded-full bg-gray-100 text-gray-500">
                        <XCircle className="w-3 h-3" />
                        Inactive
                      </span>
                    )}
                  </div>
                </div>

                <h3 className="font-semibold text-gray-900 mb-1 group-hover:text-blue-600 transition-colors">
                  {template.name}
                </h3>
                <p className="text-sm text-gray-500 mb-3 line-clamp-2">{template.description}</p>

                <div className="flex items-center justify-between pt-3 border-t border-gray-100">
                  <span className={`text-[10px] font-bold uppercase px-2 py-1 rounded-full ${documentTypeColors[template.document_type]}`}>
                    {documentTypeLabels[template.document_type]}
                  </span>
                  <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button
                      onClick={(e) => handlePreview(template, e)}
                      className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                    >
                      <Eye className="w-4 h-4" />
                    </button>
                    <button className="p-1.5 text-gray-400 hover:text-green-600 hover:bg-green-50 rounded-lg transition-colors">
                      <Copy className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {filteredTemplates.length === 0 && (
            <div className="text-center py-12">
              <FileStack className="w-12 h-12 text-gray-300 mx-auto mb-4" />
              <p className="text-gray-500">No templates found.</p>
            </div>
          )}
        </div>
      </main>

      {/* Template Edit Modal */}
      <Modal
        isOpen={!!selectedTemplate}
        onClose={() => setSelectedTemplate(null)}
        title={selectedTemplate ? `Edit: ${selectedTemplate.name}` : 'Template Details'}
        size="lg"
        footer={
          <div className="flex justify-between">
            <button className="flex items-center gap-2 px-4 py-2 text-red-600 hover:text-red-700">
              <Trash2 className="w-4 h-4" />
              Delete
            </button>
            <div className="flex gap-3">
              <button
                onClick={() => setSelectedTemplate(null)}
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
        {selectedTemplate && (
          <form className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Template Name</label>
                <input
                  type="text"
                  defaultValue={selectedTemplate.name}
                  className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Document Type</label>
                <select
                  defaultValue={selectedTemplate.document_type}
                  className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 bg-white"
                >
                  {Object.entries(documentTypeLabels).map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
              <textarea
                defaultValue={selectedTemplate.description}
                rows={2}
                className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 resize-none"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                <span className="flex items-center gap-2">
                  <Code className="w-4 h-4" />
                  Template Content (Markdown with placeholders)
                </span>
              </label>
              <textarea
                defaultValue={selectedTemplate.content_template}
                rows={10}
                className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 font-mono text-sm resize-none"
              />
              <p className="text-xs text-gray-500 mt-1">Use {'{{placeholder}}'} syntax for dynamic fields</p>
            </div>

            <div className="flex items-center gap-3">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  defaultChecked={selectedTemplate.is_active}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700">Active (available for use)</span>
              </label>
            </div>
          </form>
        )}
      </Modal>

      {/* Template Preview Modal */}
      <Modal
        isOpen={showPreviewModal}
        onClose={() => setShowPreviewModal(false)}
        title={previewTemplate ? `Preview: ${previewTemplate.name}` : 'Template Preview'}
        size="lg"
      >
        {previewTemplate && (
          <div className="space-y-4">
            <div className="flex items-center gap-2 mb-4">
              <span className={`text-xs font-bold uppercase px-2 py-1 rounded-full ${documentTypeColors[previewTemplate.document_type]}`}>
                {documentTypeLabels[previewTemplate.document_type]}
              </span>
              {previewTemplate.is_active ? (
                <Badge variant="success" size="sm">Active</Badge>
              ) : (
                <Badge variant="default" size="sm">Inactive</Badge>
              )}
            </div>

            <div>
              <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Template Content</h4>
              <div className="bg-gray-900 rounded-xl p-4 overflow-x-auto">
                <pre className="text-sm text-gray-100 whitespace-pre-wrap font-mono">
                  {previewTemplate.content_template}
                </pre>
              </div>
            </div>

            <div>
              <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Required Fields</h4>
              <div className="flex flex-wrap gap-2">
                {Object.keys(previewTemplate.schema_definition).map((field) => (
                  <span key={field} className="text-xs bg-blue-50 text-blue-700 px-2 py-1 rounded-lg font-mono">
                    {`{{${field}}}`}
                  </span>
                ))}
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
            <button
              onClick={() => setShowNewModal(false)}
              className="px-4 py-2 text-gray-600 hover:text-gray-800"
            >
              Cancel
            </button>
            <button className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
              Create Template
            </button>
          </div>
        }
      >
        <form className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Template Name *</label>
              <input
                type="text"
                placeholder="e.g., Standard SOW Template"
                className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Document Type *</label>
              <select className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 bg-white">
                <option value="">Select type...</option>
                {Object.entries(documentTypeLabels).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
            <textarea
              rows={2}
              placeholder="Describe when to use this template..."
              className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 resize-none"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Template Content *</label>
            <textarea
              rows={10}
              placeholder="# Document Title&#10;&#10;## Section 1&#10;{{placeholder}}&#10;..."
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
