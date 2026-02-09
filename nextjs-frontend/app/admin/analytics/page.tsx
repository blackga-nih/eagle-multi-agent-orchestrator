'use client';

import { useState, useRef, useEffect } from 'react';
import AuthGuard from '@/components/auth/auth-guard';
import {
  Send,
  Database,
  BarChart3,
  Table,
  Sparkles,
  Clock,
  CheckCircle2,
  Loader2,
  Copy,
  Download,
  ChevronDown,
  TrendingUp,
  Users,
  FileText,
  DollarSign,
} from 'lucide-react';
import SidebarNav from '@/components/layout/sidebar-nav';
import PageHeader from '@/components/layout/page-header';
import {
  MOCK_USERS,
  PAST_WORKFLOWS,
  CURRENT_WORKFLOW,
  MOCK_DOCUMENTS,
  MOCK_AUDIT_LOGS,
  formatCurrency,
  formatDate,
} from '@/lib/mock-data';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  queryType?: 'sql' | 'summary' | 'chart';
  data?: any;
  sqlQuery?: string;
}

// Sample queries that the analytics agent can handle
const SAMPLE_QUERIES = [
  'How many workflows are currently in progress?',
  'What is the total value of all acquisitions?',
  'Show me workflows by status',
  'List all users and their roles',
  'What documents need attention?',
  'Show recent audit activity',
  'What is the average workflow completion time?',
];

// Mock analytics responses
function generateAnalyticsResponse(query: string): { content: string; data?: any; sqlQuery?: string; queryType?: 'sql' | 'summary' | 'chart' } {
  const lowerQuery = query.toLowerCase();
  const allWorkflows = [CURRENT_WORKFLOW, ...PAST_WORKFLOWS];

  if (lowerQuery.includes('in progress') || lowerQuery.includes('active workflow')) {
    const inProgress = allWorkflows.filter(w => w.status === 'in_progress');
    return {
      content: `There ${inProgress.length === 1 ? 'is' : 'are'} **${inProgress.length} workflow${inProgress.length === 1 ? '' : 's'}** currently in progress.`,
      sqlQuery: `SELECT COUNT(*) FROM workflows WHERE status = 'in_progress';`,
      queryType: 'summary',
      data: {
        type: 'count',
        value: inProgress.length,
        label: 'In Progress Workflows',
      },
    };
  }

  if (lowerQuery.includes('total value') || lowerQuery.includes('total cost')) {
    const totalValue = allWorkflows.reduce((sum, w) => sum + (w.estimated_value || 0), 0);
    return {
      content: `The total estimated value of all acquisitions is **${formatCurrency(totalValue)}**.`,
      sqlQuery: `SELECT SUM(estimated_value) as total_value FROM workflows WHERE archived = false;`,
      queryType: 'summary',
      data: {
        type: 'currency',
        value: totalValue,
        label: 'Total Acquisition Value',
      },
    };
  }

  if (lowerQuery.includes('by status') || lowerQuery.includes('workflow status')) {
    const statusCounts = allWorkflows.reduce((acc, w) => {
      acc[w.status] = (acc[w.status] || 0) + 1;
      return acc;
    }, {} as Record<string, number>);

    return {
      content: `Here's the breakdown of workflows by status:\n\n${Object.entries(statusCounts).map(([status, count]) => `- **${status.replace('_', ' ')}**: ${count}`).join('\n')}`,
      sqlQuery: `SELECT status, COUNT(*) as count FROM workflows GROUP BY status ORDER BY count DESC;`,
      queryType: 'chart',
      data: {
        type: 'bar',
        labels: Object.keys(statusCounts).map(s => s.replace('_', ' ')),
        values: Object.values(statusCounts),
      },
    };
  }

  if (lowerQuery.includes('users') && (lowerQuery.includes('list') || lowerQuery.includes('show') || lowerQuery.includes('role'))) {
    return {
      content: `Found **${MOCK_USERS.length} users** in the system:\n\n| Name | Role | Division |\n|------|------|----------|\n${MOCK_USERS.map(u => `| ${u.display_name} | ${u.role} | ${u.division || 'N/A'} |`).join('\n')}`,
      sqlQuery: `SELECT display_name, role, division FROM users WHERE archived = false ORDER BY display_name;`,
      queryType: 'sql',
      data: {
        type: 'table',
        columns: ['Name', 'Role', 'Division'],
        rows: MOCK_USERS.map(u => [u.display_name, u.role, u.division || 'N/A']),
      },
    };
  }

  if (lowerQuery.includes('document') && (lowerQuery.includes('attention') || lowerQuery.includes('pending') || lowerQuery.includes('need'))) {
    const pendingDocs = MOCK_DOCUMENTS.filter(d => d.status === 'not_started' || d.status === 'in_progress');
    return {
      content: `There are **${pendingDocs.length} documents** that need attention:\n\n${pendingDocs.map(d => `- **${d.title}** (${d.status.replace('_', ' ')})`).join('\n')}`,
      sqlQuery: `SELECT title, status, document_type FROM documents WHERE status IN ('not_started', 'in_progress');`,
      queryType: 'sql',
      data: {
        type: 'list',
        items: pendingDocs.map(d => ({ title: d.title, status: d.status })),
      },
    };
  }

  if (lowerQuery.includes('audit') || lowerQuery.includes('activity') || lowerQuery.includes('recent')) {
    const recentLogs = MOCK_AUDIT_LOGS.slice(0, 5);
    return {
      content: `Here are the **${recentLogs.length} most recent activities**:\n\n${recentLogs.map(l => `- **${l.action.replace('.', ': ').replace('_', ' ')}** at ${formatDate(l.timestamp)}`).join('\n')}`,
      sqlQuery: `SELECT action, resource_type, timestamp FROM audit_logs ORDER BY timestamp DESC LIMIT 5;`,
      queryType: 'sql',
      data: {
        type: 'timeline',
        items: recentLogs,
      },
    };
  }

  if (lowerQuery.includes('average') && (lowerQuery.includes('completion') || lowerQuery.includes('time'))) {
    return {
      content: `The average workflow completion time is approximately **4.2 days**.\n\nThis is calculated from ${allWorkflows.filter(w => w.completed_at).length} completed workflows.`,
      sqlQuery: `SELECT AVG(EXTRACT(EPOCH FROM (completed_at - created_at))/86400) as avg_days FROM workflows WHERE completed_at IS NOT NULL;`,
      queryType: 'summary',
      data: {
        type: 'metric',
        value: 4.2,
        unit: 'days',
        label: 'Avg Completion Time',
      },
    };
  }

  // Default response for unrecognized queries
  return {
    content: `I can help you analyze acquisition data. Here are some things I can answer:\n\n- Workflow counts and statuses\n- Total acquisition values\n- User and role information\n- Document status\n- Audit activity\n\nTry asking: "${SAMPLE_QUERIES[Math.floor(Math.random() * SAMPLE_QUERIES.length)]}"`,
    queryType: 'summary',
  };
}

export default function AnalyticsPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: '1',
      role: 'assistant',
      content: "Hello! I'm your **Analytics Assistant** with read-only access to the acquisition database. I can help you:\n\n- Query workflow statistics\n- Analyze document status\n- Review user activity\n- Generate reports\n\nWhat would you like to know?",
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async (query?: string) => {
    const messageText = query || input;
    if (!messageText.trim()) return;

    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: messageText,
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsTyping(true);
    setShowSuggestions(false);

    // Simulate API delay
    setTimeout(() => {
      const response = generateAnalyticsResponse(messageText);
      const assistantMessage: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: response.content,
        timestamp: new Date(),
        queryType: response.queryType,
        data: response.data,
        sqlQuery: response.sqlQuery,
      };
      setMessages(prev => [...prev, assistantMessage]);
      setIsTyping(false);
    }, 800 + Math.random() * 700);
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
  };

  return (
    <AuthGuard>
    <div className="flex h-screen bg-gray-50">
      <SidebarNav />

      <main className="flex-1 flex flex-col overflow-hidden">
        <div className="p-6 pb-0">
          <PageHeader
            title="Analytics Chat"
            description="Query acquisition data with natural language"
            breadcrumbs={[
              { label: 'Admin', href: '/admin' },
              { label: 'Analytics' },
            ]}
          />
        </div>

        {/* Quick Stats Bar */}
        <div className="px-6 py-4 flex gap-4 overflow-x-auto">
          {[
            { icon: <TrendingUp className="w-4 h-4" />, label: 'Active Workflows', value: '1', color: 'text-blue-600 bg-blue-50' },
            { icon: <DollarSign className="w-4 h-4" />, label: 'Total Value', value: '$1M+', color: 'text-green-600 bg-green-50' },
            { icon: <Users className="w-4 h-4" />, label: 'Users', value: '3', color: 'text-purple-600 bg-purple-50' },
            { icon: <FileText className="w-4 h-4" />, label: 'Documents', value: '3', color: 'text-amber-600 bg-amber-50' },
          ].map((stat, i) => (
            <div key={i} className={`flex items-center gap-3 px-4 py-2 rounded-xl ${stat.color}`}>
              {stat.icon}
              <div>
                <p className="text-xs opacity-75">{stat.label}</p>
                <p className="font-bold">{stat.value}</p>
              </div>
            </div>
          ))}
        </div>

        {/* Chat Area */}
        <div className="flex-1 overflow-y-auto px-6 space-y-4">
          {messages.map((message) => (
            <div
              key={message.id}
              className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-2xl rounded-2xl p-4 ${
                  message.role === 'user'
                    ? 'bg-blue-600 text-white'
                    : 'bg-white border border-gray-200 shadow-sm'
                }`}
              >
                {message.role === 'assistant' && (
                  <div className="flex items-center gap-2 mb-2 pb-2 border-b border-gray-100">
                    <div className="w-6 h-6 bg-gradient-to-br from-purple-500 to-blue-500 rounded-lg flex items-center justify-center">
                      <Database className="w-3 h-3 text-white" />
                    </div>
                    <span className="text-xs font-semibold text-gray-500">Analytics Agent</span>
                    {message.queryType && (
                      <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
                        message.queryType === 'sql' ? 'bg-blue-100 text-blue-700' :
                        message.queryType === 'chart' ? 'bg-purple-100 text-purple-700' :
                        'bg-green-100 text-green-700'
                      }`}>
                        {message.queryType === 'sql' ? 'Table Query' : message.queryType === 'chart' ? 'Chart Data' : 'Summary'}
                      </span>
                    )}
                  </div>
                )}

                {/* Message content with markdown-like formatting */}
                <div className={`text-sm whitespace-pre-wrap ${message.role === 'user' ? '' : 'text-gray-700'}`}>
                  {message.content.split('\n').map((line, i) => {
                    // Bold text
                    const parts = line.split(/\*\*(.*?)\*\*/g);
                    return (
                      <p key={i} className={i > 0 ? 'mt-2' : ''}>
                        {parts.map((part, j) =>
                          j % 2 === 1 ? <strong key={j}>{part}</strong> : part
                        )}
                      </p>
                    );
                  })}
                </div>

                {/* SQL Query display */}
                {message.sqlQuery && (
                  <div className="mt-3 p-3 bg-gray-900 rounded-xl">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-[10px] text-gray-400 uppercase tracking-wide font-semibold">SQL Query</span>
                      <button
                        onClick={() => copyToClipboard(message.sqlQuery!)}
                        className="text-gray-400 hover:text-white transition-colors"
                      >
                        <Copy className="w-3 h-3" />
                      </button>
                    </div>
                    <code className="text-xs text-green-400 font-mono">{message.sqlQuery}</code>
                  </div>
                )}

                {/* Data visualization */}
                {message.data?.type === 'bar' && (
                  <div className="mt-3 p-4 bg-gray-50 rounded-xl">
                    <div className="space-y-2">
                      {message.data.labels.map((label: string, i: number) => (
                        <div key={i} className="flex items-center gap-3">
                          <span className="text-xs text-gray-600 w-24 truncate capitalize">{label}</span>
                          <div className="flex-1 h-6 bg-gray-200 rounded-full overflow-hidden">
                            <div
                              className="h-full bg-gradient-to-r from-blue-500 to-purple-500 rounded-full"
                              style={{ width: `${(message.data.values[i] / Math.max(...message.data.values)) * 100}%` }}
                            />
                          </div>
                          <span className="text-xs font-bold text-gray-700 w-8">{message.data.values[i]}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Timestamp */}
                <div className={`mt-2 text-[10px] ${message.role === 'user' ? 'text-blue-200' : 'text-gray-400'}`}>
                  {message.timestamp.toLocaleTimeString()}
                </div>
              </div>
            </div>
          ))}

          {isTyping && (
            <div className="flex justify-start">
              <div className="bg-white border border-gray-200 rounded-2xl p-4 shadow-sm">
                <div className="flex items-center gap-2">
                  <Loader2 className="w-4 h-4 text-blue-600 animate-spin" />
                  <span className="text-sm text-gray-500">Querying database...</span>
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Suggestions */}
        {showSuggestions && messages.length <= 1 && (
          <div className="px-6 py-3">
            <p className="text-xs text-gray-500 mb-2 font-medium">Try asking:</p>
            <div className="flex flex-wrap gap-2">
              {SAMPLE_QUERIES.slice(0, 4).map((query, i) => (
                <button
                  key={i}
                  onClick={() => handleSend(query)}
                  className="text-xs px-3 py-1.5 bg-white border border-gray-200 rounded-full text-gray-600 hover:bg-blue-50 hover:border-blue-300 hover:text-blue-700 transition-colors"
                >
                  {query}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Input Area */}
        <div className="p-6 bg-white border-t border-gray-200">
          <div className="flex gap-3 max-w-4xl mx-auto">
            <div className="flex-1 relative">
              <Database className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && handleSend()}
                placeholder="Ask about workflows, documents, users, or metrics..."
                className="w-full pl-11 pr-4 py-3 bg-gray-50 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 text-sm"
              />
            </div>
            <button
              onClick={() => handleSend()}
              disabled={!input.trim() || isTyping}
              className="px-4 py-3 bg-blue-600 text-white rounded-xl hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-md shadow-blue-200"
            >
              <Send className="w-4 h-4" />
            </button>
          </div>
          <p className="text-[10px] text-gray-400 text-center mt-2">
            Read-only database access • Queries are logged for audit purposes
          </p>
        </div>
      </main>
    </div>
    </AuthGuard>
  );
}
