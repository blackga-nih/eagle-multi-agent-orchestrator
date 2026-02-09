'use client';

import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { Brain, Search, FileText, Cpu, ChevronDown, ChevronUp, ArrowRight, X, Copy, Check, Code, User, ClipboardCheck } from 'lucide-react';
import { StreamEvent, AuditLogEntry } from '@/types/stream';
import { getAgentColors, getAgentName, AgentColorScheme } from '@/lib/agent-colors';

interface MultiAgentLogsProps {
  logs: AuditLogEntry[];
}

/**
 * Multi-Agent Audit Logs Component
 *
 * Displays a timeline of events from multiple agents with:
 * - Color-coded entries by agent
 * - Grouped "Report" blocks for text/reasoning
 * - Handoff visualization between agents
 * - Click to view full details in modal
 */
export default function MultiAgentLogs({ logs }: MultiAgentLogsProps) {
  const [expandedLogs, setExpandedLogs] = useState<Set<string>>(new Set());
  const [selectedLog, setSelectedLog] = useState<AuditLogEntry | null>(null);
  const [showRawJson, setShowRawJson] = useState(false);
  const [copied, setCopied] = useState(false);

  const toggleExpand = (id: string) => {
    setExpandedLogs(prev => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const openDetail = (log: AuditLogEntry) => {
    setSelectedLog(log);
    setShowRawJson(false);
    setCopied(false);
  };

  const closeDetail = () => {
    setSelectedLog(null);
    setShowRawJson(false);
  };

  const copyToClipboard = async (text: string) => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Group consecutive text/reasoning logs from the same agent
  const groupedLogs = groupLogs(logs);

  return (
    <>
      <div className="space-y-3">
        {groupedLogs.length === 0 ? (
          <div className="text-center py-10 text-gray-400 text-sm italic">
            No stream data yet. Start a conversation to see live agent activity.
          </div>
        ) : (
          groupedLogs.map((log) => {
            const colors = getAgentColors(log.agent_id);
            const agentName = log.agent_name || getAgentName(log.agent_id);
            const isExpanded = expandedLogs.has(log.id);

            return (
              <div
                key={log.id}
                className={`p-3 ${colors.bg} border ${colors.border} rounded-xl font-mono text-[10px] leading-relaxed relative overflow-hidden group transition-all cursor-pointer hover:shadow-md`}
                onClick={() => openDetail(log)}
              >
                {/* Header */}
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-2">
                    {/* Agent Badge */}
                    <span className={`px-1.5 py-0.5 rounded text-[8px] font-bold uppercase ${colors.badge}`}>
                      {agentName}
                    </span>

                    {/* Event Type */}
                    <span className={`px-1.5 py-0.5 rounded text-[8px] font-bold uppercase ${getEventTypeBadge(log.type)}`}>
                      {formatEventType(log.type, log)}
                    </span>
                  </div>

                  {/* Timestamp */}
                  <span className="text-[9px] text-gray-400">
                    {new Date(log.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                  </span>
                </div>

                {/* Content Preview */}
                <div className={`${colors.text} break-words transition-all line-clamp-2`}>
                  {log.type === 'text' && (
                    <span>{(log.content || '').slice(0, 100)}...</span>
                  )}

                  {log.type === 'reasoning' && (
                    <div className="flex items-start gap-1.5 italic">
                      <Brain className="w-3 h-3 mt-0.5 flex-shrink-0" />
                      {log.reasoning || log.content}
                    </div>
                  )}

                  {log.type === 'tool_use' && log.tool_use && (
                    <div className="flex items-center gap-1">
                      <Cpu className="w-3 h-3" />
                      <span className="font-bold">{log.tool_use.name}</span>
                      <span className="text-gray-500">({JSON.stringify(log.tool_use.input).slice(0, 50)}...)</span>
                    </div>
                  )}

                  {log.type === 'tool_result' && log.tool_result && (
                    <div className="flex items-center gap-1">
                      <span className="font-bold">{log.tool_result.name} →</span>
                      <span>{JSON.stringify(log.tool_result.result).slice(0, 80)}...</span>
                    </div>
                  )}

                  {log.type === 'elicitation' && log.elicitation && (
                    <div className="flex items-center gap-1">
                      <span className="font-bold">Question:</span>
                      {log.elicitation.question}
                    </div>
                  )}

                  {log.type === 'metadata' && log.metadata && (
                    <div className="flex items-center gap-1">
                      <span className="font-bold">Data Sync:</span>
                      {JSON.stringify(log.metadata).slice(0, 100)}...
                    </div>
                  )}

                  {log.type === 'handoff' && log.metadata && (
                    <div className="flex items-center gap-2">
                      <ArrowRight className="w-3 h-3" />
                      <span className="font-bold">Handoff to:</span>
                      <span className={`px-1 py-0.5 rounded ${getAgentColors(log.metadata.target_agent).badge}`}>
                        {getAgentName(log.metadata.target_agent)}
                      </span>
                      <span className="text-gray-500">({log.metadata.reason})</span>
                    </div>
                  )}

                  {log.type === 'user_input' && (
                    <div className="flex items-start gap-1.5">
                      <User className="w-3 h-3 mt-0.5 flex-shrink-0" />
                      <span className="font-medium">{(log.content || '').slice(0, 100)}{(log.content || '').length > 100 ? '...' : ''}</span>
                    </div>
                  )}

                  {log.type === 'form_submit' && log.metadata && (
                    <div className="flex items-start gap-1.5">
                      <ClipboardCheck className="w-3 h-3 mt-0.5 flex-shrink-0" />
                      <span className="font-medium">{log.metadata.form_type || 'Form'}: {log.metadata.summary || 'Submitted'}</span>
                    </div>
                  )}

                  {log.type === 'complete' && (
                    <div className="text-gray-500">--- Stream Complete ---</div>
                  )}

                  {log.type === 'error' && (
                    <div className="text-red-600 font-bold">Error: {log.content}</div>
                  )}
                </div>

                {/* Click hint */}
                <div className="absolute bottom-1 right-2 text-[8px] text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity">
                  Click to expand
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Detail Modal */}
      {selectedLog && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={closeDetail}>
          <div
            className="bg-white rounded-2xl shadow-2xl max-w-2xl w-full max-h-[80vh] overflow-hidden flex flex-col"
            onClick={e => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className={`p-4 border-b ${getAgentColors(selectedLog.agent_id).bg} flex items-center justify-between`}>
              <div className="flex items-center gap-3">
                <span className={`px-2 py-1 rounded text-xs font-bold uppercase ${getAgentColors(selectedLog.agent_id).badge}`}>
                  {selectedLog.agent_name || getAgentName(selectedLog.agent_id)}
                </span>
                <span className={`px-2 py-1 rounded text-xs font-bold uppercase ${getEventTypeBadge(selectedLog.type)}`}>
                  {formatEventType(selectedLog.type, selectedLog)}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-500">
                  {new Date(selectedLog.timestamp).toLocaleString()}
                </span>
                <button
                  onClick={closeDetail}
                  className="p-1 hover:bg-gray-200 rounded-lg transition-colors"
                >
                  <X className="w-5 h-5 text-gray-500" />
                </button>
              </div>
            </div>

            {/* Modal Content */}
            <div className="flex-1 overflow-y-auto p-4">
              {/* Toggle Raw JSON */}
              <div className="flex items-center justify-end mb-3 gap-2">
                <button
                  onClick={() => copyToClipboard(JSON.stringify(selectedLog, null, 2))}
                  className="flex items-center gap-1 px-2 py-1 text-xs bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
                >
                  {copied ? <Check className="w-3 h-3 text-green-600" /> : <Copy className="w-3 h-3" />}
                  {copied ? 'Copied!' : 'Copy JSON'}
                </button>
                <button
                  onClick={() => setShowRawJson(!showRawJson)}
                  className={`flex items-center gap-1 px-2 py-1 text-xs rounded-lg transition-colors ${showRawJson ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 hover:bg-gray-200'}`}
                >
                  <Code className="w-3 h-3" />
                  {showRawJson ? 'Formatted' : 'Raw JSON'}
                </button>
              </div>

              {showRawJson ? (
                <pre className="bg-gray-900 text-green-400 p-4 rounded-xl text-xs overflow-x-auto font-mono">
                  {JSON.stringify(selectedLog, null, 2)}
                </pre>
              ) : (
                <div className="space-y-4">
                  {/* Event Type Specific Content */}
                  {selectedLog.type === 'text' && selectedLog.content && (
                    <div>
                      <h4 className="text-xs font-bold text-gray-500 uppercase mb-2">Response Content</h4>
                      <div className="prose prose-sm max-w-none bg-gray-50 p-4 rounded-xl">
                        <ReactMarkdown>{selectedLog.content}</ReactMarkdown>
                      </div>
                    </div>
                  )}

                  {selectedLog.type === 'reasoning' && (
                    <div>
                      <h4 className="text-xs font-bold text-gray-500 uppercase mb-2">Agent Reasoning</h4>
                      <div className="bg-purple-50 border border-purple-200 p-4 rounded-xl flex items-start gap-2">
                        <Brain className="w-5 h-5 text-purple-600 flex-shrink-0 mt-0.5" />
                        <p className="text-sm text-purple-800 italic">{selectedLog.reasoning || selectedLog.content}</p>
                      </div>
                    </div>
                  )}

                  {selectedLog.type === 'tool_use' && selectedLog.tool_use && (
                    <div>
                      <h4 className="text-xs font-bold text-gray-500 uppercase mb-2">Tool Invocation</h4>
                      <div className="bg-yellow-50 border border-yellow-200 p-4 rounded-xl">
                        <div className="flex items-center gap-2 mb-3">
                          <Cpu className="w-5 h-5 text-yellow-600" />
                          <span className="font-bold text-yellow-800">{selectedLog.tool_use.name}</span>
                        </div>
                        <h5 className="text-xs font-bold text-gray-500 mb-1">Input Parameters:</h5>
                        <pre className="bg-white p-3 rounded-lg text-xs overflow-x-auto border border-yellow-100">
                          {JSON.stringify(selectedLog.tool_use.input, null, 2)}
                        </pre>
                      </div>
                    </div>
                  )}

                  {selectedLog.type === 'tool_result' && selectedLog.tool_result && (
                    <div>
                      <h4 className="text-xs font-bold text-gray-500 uppercase mb-2">Tool Result</h4>
                      <div className="bg-orange-50 border border-orange-200 p-4 rounded-xl">
                        <div className="flex items-center gap-2 mb-3">
                          <span className="font-bold text-orange-800">{selectedLog.tool_result.name}</span>
                          <ArrowRight className="w-4 h-4 text-orange-500" />
                          <span className="text-xs text-orange-600">Result</span>
                        </div>
                        <h5 className="text-xs font-bold text-gray-500 mb-1">Output:</h5>
                        <pre className="bg-white p-3 rounded-lg text-xs overflow-x-auto border border-orange-100">
                          {JSON.stringify(selectedLog.tool_result.result, null, 2)}
                        </pre>
                      </div>
                    </div>
                  )}

                  {selectedLog.type === 'handoff' && selectedLog.metadata && (
                    <div>
                      <h4 className="text-xs font-bold text-gray-500 uppercase mb-2">Agent Handoff</h4>
                      <div className="bg-pink-50 border border-pink-200 p-4 rounded-xl">
                        <div className="flex items-center gap-3 mb-3">
                          <span className={`px-2 py-1 rounded text-xs font-bold ${getAgentColors(selectedLog.agent_id).badge}`}>
                            {selectedLog.agent_name || getAgentName(selectedLog.agent_id)}
                          </span>
                          <ArrowRight className="w-5 h-5 text-pink-500" />
                          <span className={`px-2 py-1 rounded text-xs font-bold ${getAgentColors(selectedLog.metadata.target_agent).badge}`}>
                            {selectedLog.metadata.target_agent_name || getAgentName(selectedLog.metadata.target_agent)}
                          </span>
                        </div>
                        <h5 className="text-xs font-bold text-gray-500 mb-1">Reason:</h5>
                        <p className="text-sm text-pink-800">{selectedLog.metadata.reason}</p>
                      </div>
                    </div>
                  )}

                  {selectedLog.type === 'elicitation' && selectedLog.elicitation && (
                    <div>
                      <h4 className="text-xs font-bold text-gray-500 uppercase mb-2">User Elicitation</h4>
                      <div className="bg-green-50 border border-green-200 p-4 rounded-xl">
                        <p className="font-bold text-green-800 mb-2">{selectedLog.elicitation.question}</p>
                        {selectedLog.elicitation.fields && selectedLog.elicitation.fields.length > 0 && (
                          <div className="mt-3">
                            <h5 className="text-xs font-bold text-gray-500 mb-1">Fields:</h5>
                            <pre className="bg-white p-3 rounded-lg text-xs overflow-x-auto border border-green-100">
                              {JSON.stringify(selectedLog.elicitation.fields, null, 2)}
                            </pre>
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {selectedLog.type === 'metadata' && selectedLog.metadata && (
                    <div>
                      <h4 className="text-xs font-bold text-gray-500 uppercase mb-2">Metadata</h4>
                      <pre className="bg-indigo-50 border border-indigo-200 p-4 rounded-xl text-xs overflow-x-auto">
                        {JSON.stringify(selectedLog.metadata, null, 2)}
                      </pre>
                    </div>
                  )}

                  {selectedLog.type === 'complete' && (
                    <div className="bg-gray-100 border border-gray-200 p-4 rounded-xl text-center">
                      <p className="text-gray-600 font-medium">Stream Complete</p>
                      <p className="text-xs text-gray-400 mt-1">Agent finished processing the request</p>
                    </div>
                  )}

                  {selectedLog.type === 'error' && (
                    <div>
                      <h4 className="text-xs font-bold text-gray-500 uppercase mb-2">Error Details</h4>
                      <div className="bg-red-50 border border-red-200 p-4 rounded-xl">
                        <p className="text-red-700 font-medium">{selectedLog.content}</p>
                      </div>
                    </div>
                  )}

                  {selectedLog.type === 'user_input' && (
                    <div>
                      <h4 className="text-xs font-bold text-gray-500 uppercase mb-2">User Input</h4>
                      <div className="bg-cyan-50 border border-cyan-200 p-4 rounded-xl">
                        <div className="flex items-start gap-2">
                          <User className="w-5 h-5 text-cyan-600 flex-shrink-0 mt-0.5" />
                          <p className="text-sm text-cyan-800">{selectedLog.content}</p>
                        </div>
                      </div>
                    </div>
                  )}

                  {selectedLog.type === 'form_submit' && selectedLog.metadata && (
                    <div>
                      <h4 className="text-xs font-bold text-gray-500 uppercase mb-2">Form Submission</h4>
                      <div className="bg-teal-50 border border-teal-200 p-4 rounded-xl">
                        <div className="flex items-center gap-2 mb-3">
                          <ClipboardCheck className="w-5 h-5 text-teal-600" />
                          <span className="font-bold text-teal-800">{selectedLog.metadata.form_type || 'Form'}</span>
                        </div>
                        <h5 className="text-xs font-bold text-gray-500 mb-1">Submitted Data:</h5>
                        <pre className="bg-white p-3 rounded-lg text-xs overflow-x-auto border border-teal-100">
                          {JSON.stringify(selectedLog.metadata.data || selectedLog.metadata, null, 2)}
                        </pre>
                      </div>
                    </div>
                  )}

                  {/* Event ID */}
                  <div className="pt-3 border-t border-gray-100">
                    <p className="text-xs text-gray-400">
                      Event ID: <code className="bg-gray-100 px-1 rounded">{selectedLog.id}</code>
                    </p>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

// Helper functions

function groupLogs(logs: AuditLogEntry[]): AuditLogEntry[] {
  // Filter out reasoning logs - they clutter the stream without adding user value
  return logs.filter(log => log.type !== 'reasoning');
}

function formatEventType(type: string, log: AuditLogEntry): string {
  if (type === 'text') return 'Report (text)';
  if (type === 'reasoning') return 'Report (reasoning)';
  if (type === 'tool_use') return 'Tool Use';
  if (type === 'tool_result') return 'Tool Result';
  if (type === 'elicitation') return 'Elicitation';
  if (type === 'metadata') return 'Metadata';
  if (type === 'handoff') return 'Handoff';
  if (type === 'complete') return 'Complete';
  if (type === 'error') return 'Error';
  if (type === 'user_input') return 'User Input';
  if (type === 'form_submit') return 'Form Submit';
  return type;
}

function getEventTypeBadge(type: string): string {
  switch (type) {
    case 'text':
      return 'bg-blue-100 text-blue-700';
    case 'reasoning':
      return 'bg-purple-100 text-purple-700';
    case 'tool_use':
      return 'bg-yellow-100 text-yellow-700';
    case 'tool_result':
      return 'bg-orange-100 text-orange-700';
    case 'elicitation':
      return 'bg-green-100 text-green-700';
    case 'metadata':
      return 'bg-indigo-100 text-indigo-700';
    case 'handoff':
      return 'bg-pink-100 text-pink-700';
    case 'complete':
      return 'bg-gray-100 text-gray-700';
    case 'error':
      return 'bg-red-100 text-red-700';
    case 'user_input':
      return 'bg-cyan-100 text-cyan-700';
    case 'form_submit':
      return 'bg-teal-100 text-teal-700';
    default:
      return 'bg-gray-100 text-gray-700';
  }
}
