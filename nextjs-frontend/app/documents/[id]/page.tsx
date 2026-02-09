'use client';

import { useState, use } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowLeft, Save, MessageSquare, FileText, CheckSquare, Send, Bot, User, Sparkles } from 'lucide-react';
import SidebarNav from '@/components/layout/sidebar-nav';
import { Tabs } from '@/components/ui/tabs';
import MarkdownRenderer from '@/components/ui/markdown-renderer';
import DocumentRequirements from '@/components/documents/document-requirements';
import { MOCK_DOCUMENTS, getDocumentStatusColor, formatDate } from '@/lib/mock-data';

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function DocumentEditorPage({ params }: PageProps) {
  const { id } = use(params);
  const router = useRouter();
  const [activeTab, setActiveTab] = useState('content');
  const [isEditing, setIsEditing] = useState(false);
  const [chatMessages, setChatMessages] = useState<Array<{ role: 'user' | 'assistant'; content: string }>>([
    { role: 'assistant', content: 'I can help you edit this document. What would you like to change?' }
  ]);
  const [chatInput, setChatInput] = useState('');

  const document = MOCK_DOCUMENTS.find(d => d.id === id);

  if (!document) {
    return (
      <div className="flex h-screen bg-gray-50">
        <SidebarNav />
        <main className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <FileText className="w-16 h-16 text-gray-300 mx-auto mb-4" />
            <h2 className="text-xl font-semibold text-gray-900 mb-2">Document Not Found</h2>
            <p className="text-gray-500 mb-4">The document you&apos;re looking for doesn&apos;t exist.</p>
            <button
              onClick={() => router.push('/documents')}
              className="text-blue-600 hover:text-blue-700"
            >
              Back to Documents
            </button>
          </div>
        </main>
      </div>
    );
  }

  const tabs = [
    { id: 'content', label: 'Content', icon: <FileText className="w-4 h-4" /> },
    { id: 'requirements', label: 'Requirements', icon: <CheckSquare className="w-4 h-4" />, badge: 6 },
  ];

  const handleSendMessage = () => {
    if (!chatInput.trim()) return;
    setChatMessages(prev => [
      ...prev,
      { role: 'user', content: chatInput },
      { role: 'assistant', content: `I understand you want to "${chatInput}". Let me help you with that...` }
    ]);
    setChatInput('');
  };

  return (
    <div className="flex h-screen bg-gray-50">
      <SidebarNav />

      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <header className="bg-white border-b border-gray-200 px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <button
                onClick={() => router.push('/documents')}
                className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
              >
                <ArrowLeft className="w-5 h-5" />
              </button>
              <div>
                <h1 className="text-xl font-semibold text-gray-900">{document.title}</h1>
                <div className="flex items-center gap-3 mt-1 text-sm text-gray-500">
                  <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full ${getDocumentStatusColor(document.status)}`}>
                    {document.status.replace('_', ' ')}
                  </span>
                  <span>v{document.version}</span>
                  <span>Last updated {formatDate(document.updated_at)}</span>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <button className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700 transition-colors">
                <Save className="w-4 h-4" />
                Save Changes
              </button>
            </div>
          </div>
        </header>

        {/* Main Content Area */}
        <div className="flex-1 flex overflow-hidden">
          {/* Left Panel - Document */}
          <div className="flex-1 flex flex-col border-r border-gray-200 bg-white" style={{ width: '65%' }}>
            {/* Tabs */}
            <div className="px-6 pt-4 border-b border-gray-100">
              <div className="flex gap-1">
                {tabs.map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`flex items-center gap-2 px-4 py-2.5 rounded-t-lg text-sm font-medium transition-colors ${
                      activeTab === tab.id
                        ? 'bg-gray-100 text-gray-900 border-b-2 border-blue-600'
                        : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50'
                    }`}
                  >
                    {tab.icon}
                    {tab.label}
                    {tab.badge && (
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                        activeTab === tab.id ? 'bg-blue-100 text-blue-700' : 'bg-gray-200 text-gray-600'
                      }`}>
                        {tab.badge}
                      </span>
                    )}
                  </button>
                ))}
              </div>
            </div>

            {/* Tab Content */}
            <div className="flex-1 overflow-y-auto p-6">
              {activeTab === 'content' && (
                <div className="max-w-3xl">
                  {isEditing ? (
                    <textarea
                      className="w-full h-[600px] p-4 border border-gray-200 rounded-xl font-mono text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
                      defaultValue={document.content || ''}
                    />
                  ) : (
                    <div className="prose prose-sm max-w-none">
                      <MarkdownRenderer content={document.content || ''} />
                    </div>
                  )}
                  <div className="mt-4">
                    <button
                      onClick={() => setIsEditing(!isEditing)}
                      className="text-sm text-blue-600 hover:text-blue-700"
                    >
                      {isEditing ? 'Preview' : 'Edit Markdown'}
                    </button>
                  </div>
                </div>
              )}

              {activeTab === 'requirements' && (
                <DocumentRequirements documentId={document.id} />
              )}
            </div>
          </div>

          {/* Right Panel - Chat */}
          <div className="flex flex-col bg-gray-50" style={{ width: '35%' }}>
            {/* Chat Header */}
            <div className="px-4 py-3 bg-white border-b border-gray-200">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 bg-gradient-to-br from-violet-500 to-purple-600 rounded-lg flex items-center justify-center">
                  <Bot className="w-4 h-4 text-white" />
                </div>
                <div>
                  <h3 className="font-medium text-gray-900 text-sm">Document Assistant</h3>
                  <p className="text-xs text-gray-500">AI-powered editing help</p>
                </div>
              </div>
            </div>

            {/* Chat Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {chatMessages.map((msg, i) => (
                <div key={i} className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${
                    msg.role === 'assistant'
                      ? 'bg-gradient-to-br from-violet-500 to-purple-600'
                      : 'bg-blue-500'
                  }`}>
                    {msg.role === 'assistant' ? (
                      <Sparkles className="w-4 h-4 text-white" />
                    ) : (
                      <User className="w-4 h-4 text-white" />
                    )}
                  </div>
                  <div className={`max-w-[80%] px-4 py-2.5 rounded-2xl text-sm ${
                    msg.role === 'assistant'
                      ? 'bg-white border border-gray-200 text-gray-700'
                      : 'bg-blue-600 text-white'
                  }`}>
                    {msg.content}
                  </div>
                </div>
              ))}
            </div>

            {/* Chat Input */}
            <div className="p-4 bg-white border-t border-gray-200">
              <div className="flex gap-2">
                <input
                  type="text"
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSendMessage()}
                  placeholder="Ask for help editing..."
                  className="flex-1 px-4 py-2.5 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
                />
                <button
                  onClick={handleSendMessage}
                  className="px-4 py-2.5 bg-blue-600 text-white rounded-xl hover:bg-blue-700 transition-colors"
                >
                  <Send className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
