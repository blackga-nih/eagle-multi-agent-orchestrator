'use client';

import { useState, useRef, useEffect } from 'react';
import { Send, Loader2, Trash2, Bot, User, Download, FileText, History, Cloud, CloudOff, RefreshCw } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { AgentConfig, AgentMessage, ToolResult } from '@/types/mcp';
import { useMCPClient } from '@/hooks/use-mcp-client';
import { USE_MOCK_MCP } from '@/lib/mcp-config';
import MCPToolResult from './mcp-tool-result';
import AgentSidebar from './agent-sidebar';

interface AgentChatProps {
  config: AgentConfig;
}

export default function AgentChat({ config }: AgentChatProps) {
  const [input, setInput] = useState('');
  const [toolResults, setToolResults] = useState<ToolResult[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const {
    isConnected,
    isLoading,
    tools,
    messages,
    sendMessage,
    clearMessages,
    error,
    messageCount,
    exportAsMarkdown,
    exportAsJSON,
    isSynced,
    hasPendingChanges,
    forceSync,
  } = useMCPClient({
    agentId: config.id,
    onToolResult: (result) => {
      setToolResults((prev) => [...prev, result]);
    },
  });

  const [isSyncing, setIsSyncing] = useState(false);

  const handleForceSync = async () => {
    setIsSyncing(true);
    try {
      await forceSync();
    } finally {
      setIsSyncing(false);
    }
  };

  // Export conversation handlers
  const handleExportMarkdown = () => {
    const markdown = exportAsMarkdown();
    const blob = new Blob([markdown], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${config.id}-conversation.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleExportJSON = () => {
    const json = exportAsJSON();
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${config.id}-conversation.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;
    const query = input;
    setInput('');
    await sendMessage(query);
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleClear = () => {
    clearMessages();
    setToolResults([]);
  };

  return (
    <div className="h-full flex">
      {/* Chat Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.length === 0 && (
            <div className="h-full flex flex-col items-center justify-center text-center p-8">
              <div className={`p-4 rounded-2xl ${config.bgColor} ${config.color} mb-4`}>
                <Bot className="w-8 h-8" />
              </div>
              <h3 className="text-lg font-semibold text-gray-900 mb-2">{config.name}</h3>
              <p className="text-sm text-gray-500 max-w-md">{config.description}</p>
              <div className="mt-6 space-y-2">
                <p className="text-xs font-medium text-gray-400">Try asking:</p>
                <div className="flex flex-wrap gap-2 justify-center">
                  {getSuggestedQuestions(config.id).map((q, i) => (
                    <button
                      key={i}
                      onClick={() => setInput(q)}
                      className="px-3 py-1.5 text-xs bg-gray-100 hover:bg-gray-200 text-gray-600 rounded-full transition-colors"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {messages.map((message) => (
            <div
              key={message.id}
              className={`flex gap-3 ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              {message.role === 'assistant' && (
                <div className={`w-8 h-8 rounded-lg ${config.bgColor} ${config.color} flex items-center justify-center flex-shrink-0`}>
                  <Bot className="w-4 h-4" />
                </div>
              )}

              <div
                className={`max-w-[80%] ${
                  message.role === 'user'
                    ? 'bg-blue-600 text-white rounded-2xl rounded-br-md px-4 py-3'
                    : 'bg-white border border-gray-200 rounded-2xl rounded-bl-md px-4 py-3 shadow-sm'
                }`}
              >
                {message.role === 'user' ? (
                  <p className="text-sm whitespace-pre-wrap">{message.content}</p>
                ) : (
                  <div className="prose prose-sm max-w-none">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {message.content}
                    </ReactMarkdown>
                  </div>
                )}

                {/* Tool Results */}
                {message.toolCalls && message.toolCalls.length > 0 && (
                  <div className="mt-3 space-y-2">
                    {message.toolCalls.map((tc, idx) => (
                      <MCPToolResult key={`${tc.name}-${idx}`} toolResult={tc} />
                    ))}
                  </div>
                )}

                <p className="text-[10px] mt-2 opacity-60">
                  {new Date(message.timestamp).toLocaleTimeString()}
                </p>
              </div>

              {message.role === 'user' && (
                <div className="w-8 h-8 rounded-lg bg-blue-100 text-blue-600 flex items-center justify-center flex-shrink-0">
                  <User className="w-4 h-4" />
                </div>
              )}
            </div>
          ))}

          {/* Loading indicator */}
          {isLoading && (
            <div className="flex gap-3">
              <div className={`w-8 h-8 rounded-lg ${config.bgColor} ${config.color} flex items-center justify-center flex-shrink-0`}>
                <Bot className="w-4 h-4" />
              </div>
              <div className="bg-white border border-gray-200 rounded-2xl rounded-bl-md px-4 py-3 shadow-sm">
                <div className="flex items-center gap-2 text-gray-500">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span className="text-sm">Thinking...</span>
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input Area */}
        <div className="border-t bg-white p-4">
          {/* Session info bar */}
          {messageCount > 0 && (
            <div className="mb-3 flex items-center justify-between text-xs text-gray-400">
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-2">
                  <History className="w-3 h-3" />
                  <span>{messageCount} messages</span>
                </div>
                {/* Sync status indicator */}
                <div className="flex items-center gap-1.5">
                  {isSyncing ? (
                    <RefreshCw className="w-3 h-3 animate-spin text-blue-500" />
                  ) : isSynced ? (
                    <Cloud className="w-3 h-3 text-green-500" />
                  ) : hasPendingChanges ? (
                    <CloudOff className="w-3 h-3 text-amber-500" />
                  ) : (
                    <CloudOff className="w-3 h-3 text-gray-300" />
                  )}
                  <span className={isSynced ? 'text-green-600' : hasPendingChanges ? 'text-amber-600' : ''}>
                    {isSyncing ? 'Syncing...' : isSynced ? 'Synced' : hasPendingChanges ? 'Pending' : 'Offline'}
                  </span>
                  {(hasPendingChanges || !isSynced) && !isSyncing && (
                    <button
                      onClick={handleForceSync}
                      className="ml-1 p-1 hover:bg-gray-100 rounded transition-colors"
                      title="Force sync now"
                    >
                      <RefreshCw className="w-3 h-3" />
                    </button>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={handleExportMarkdown}
                  className="p-1.5 hover:bg-gray-100 rounded transition-colors"
                  title="Export as Markdown"
                >
                  <FileText className="w-3 h-3" />
                </button>
                <button
                  onClick={handleExportJSON}
                  className="p-1.5 hover:bg-gray-100 rounded transition-colors"
                  title="Export as JSON"
                >
                  <Download className="w-3 h-3" />
                </button>
              </div>
            </div>
          )}
          {error && (
            <div className="mb-3 px-3 py-2 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
              {error}
            </div>
          )}
          <div className="flex gap-2">
            <button
              onClick={handleClear}
              disabled={messages.length === 0}
              className="p-3 rounded-xl text-gray-400 hover:text-gray-600 hover:bg-gray-100 disabled:opacity-30 transition-colors"
              title="Clear chat history"
            >
              <Trash2 className="w-5 h-5" />
            </button>
            <div className="flex-1 relative">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder={`Ask ${config.name}...`}
                disabled={isLoading}
                rows={1}
                className="w-full px-4 py-3 bg-gray-50 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all text-sm resize-none disabled:opacity-50"
                style={{ minHeight: '48px', maxHeight: '120px' }}
              />
            </div>
            <button
              onClick={handleSend}
              disabled={!input.trim() || isLoading}
              className={`p-3 rounded-xl transition-all ${
                input.trim() && !isLoading
                  ? `${config.bgColor} ${config.color} hover:opacity-80`
                  : 'bg-gray-100 text-gray-400'
              } disabled:opacity-30`}
            >
              {isLoading ? (
                <Loader2 className="w-5 h-5 animate-spin" />
              ) : (
                <Send className="w-5 h-5" />
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Sidebar */}
      <div className="w-80 border-l bg-white p-4 overflow-y-auto hidden lg:block">
        <AgentSidebar
          config={config}
          isConnected={isConnected}
          isMockMode={USE_MOCK_MCP}
          tools={tools}
          recentToolResults={toolResults}
        />
      </div>
    </div>
  );
}

function getSuggestedQuestions(agentId: string): string[] {
  const suggestions: Record<string, string[]> = {
    frontend: [
      'How is the sidebar component structured?',
      'What styling patterns are used?',
      'Review the chat interface code',
    ],
    backend: [
      'Show me the database schema',
      'How does the API handle errors?',
      'List all API endpoints',
    ],
    aws_admin: [
      'Check CloudWatch logs for errors',
      'What EC2 instances are running?',
      'Show Lambda function status',
    ],
    analyst: [
      'How many users are active?',
      'Generate a workflow report',
      'Analyze data trends',
    ],
  };

  return suggestions[agentId] || ['How can you help me?'];
}
