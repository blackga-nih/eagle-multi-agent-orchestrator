'use client';

import { useState, useRef, useEffect, useMemo } from 'react';
import {
  Brain, Cpu, ArrowRight, Code, User,
  ClipboardCheck, FileText, AlertCircle, CheckCircle2,
  ChevronDown, ChevronUp, MessageSquare, Zap,
} from 'lucide-react';
import { AuditLogEntry } from '@/types/stream';
import { getAgentColors, getAgentName, getAgentIcon } from '@/lib/agent-colors';
import TraceDetailModal from './trace-detail-modal';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** A display entry that may collapse multiple raw log entries. */
interface DisplayEntry {
  /** Primary log entry (or the last in a collapsed group). */
  log: AuditLogEntry;
  /** All raw log entries in this group (>1 when consecutive text events are collapsed). */
  group: AuditLogEntry[];
  /** Combined content for collapsed text groups. */
  mergedContent?: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatTime(timestamp: string): string {
  try {
    return new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return '';
  }
}

function formatEventType(type: string, log?: AuditLogEntry): string {
  switch (type) {
    case 'text':        return 'Report';
    case 'reasoning':   return 'Reasoning';
    case 'tool_use':    return `Tool: ${log?.tool_use?.name ?? 'Use'}`;
    case 'tool_result': return `Result: ${log?.tool_result?.name ?? ''}`;
    case 'handoff':     return 'Handoff';
    case 'complete':    return 'Complete';
    case 'error':       return 'Error';
    case 'user_input':  return 'User Input';
    case 'form_submit': return 'Form Submit';
    case 'metadata':    return 'Metadata';
    case 'elicitation': return 'Question';
    default:            return type;
  }
}

function getEventTypeBadge(type: string): string {
  switch (type) {
    case 'text':        return 'bg-blue-100 text-blue-700';
    case 'reasoning':   return 'bg-purple-100 text-purple-700';
    case 'tool_use':    return 'bg-yellow-100 text-yellow-800';
    case 'tool_result': return 'bg-orange-100 text-orange-700';
    case 'handoff':     return 'bg-pink-100 text-pink-700';
    case 'complete':    return 'bg-gray-100 text-gray-600';
    case 'error':       return 'bg-red-100 text-red-700';
    case 'user_input':  return 'bg-cyan-100 text-cyan-700';
    case 'form_submit': return 'bg-teal-100 text-teal-700';
    case 'metadata':    return 'bg-indigo-100 text-indigo-700';
    case 'elicitation': return 'bg-green-100 text-green-700';
    default:            return 'bg-gray-100 text-gray-600';
  }
}

function getEventIcon(type: string) {
  switch (type) {
    case 'text':        return <MessageSquare className="w-3 h-3" />;
    case 'reasoning':   return <Brain className="w-3 h-3" />;
    case 'tool_use':    return <Cpu className="w-3 h-3" />;
    case 'tool_result': return <FileText className="w-3 h-3" />;
    case 'handoff':     return <ArrowRight className="w-3 h-3" />;
    case 'complete':    return <CheckCircle2 className="w-3 h-3" />;
    case 'error':       return <AlertCircle className="w-3 h-3" />;
    case 'user_input':  return <User className="w-3 h-3" />;
    case 'form_submit': return <ClipboardCheck className="w-3 h-3" />;
    case 'metadata':    return <Code className="w-3 h-3" />;
    case 'elicitation': return <Zap className="w-3 h-3" />;
    default:            return <Code className="w-3 h-3" />;
  }
}

/**
 * Collapse consecutive text events from the same agent into a single entry.
 * Filter out reasoning events. All other event types pass through 1:1.
 */
function buildDisplayEntries(logs: AuditLogEntry[]): DisplayEntry[] {
  const entries: DisplayEntry[] = [];
  let textBuffer: AuditLogEntry[] = [];
  let textAgent: string | null = null;

  function flushTextBuffer() {
    if (textBuffer.length === 0) return;
    const merged = textBuffer.map(l => l.content ?? '').join('');
    entries.push({
      log: textBuffer[textBuffer.length - 1],
      group: [...textBuffer],
      mergedContent: merged,
    });
    textBuffer = [];
    textAgent = null;
  }

  for (const log of logs) {
    // bedrock_trace events have their own dedicated Bedrock tab — skip here
    if (log.type === 'bedrock_trace') continue;

    if (log.type === 'text') {
      // Collapse consecutive text from same agent
      if (textAgent && textAgent !== log.agent_id) {
        flushTextBuffer();
      }
      textAgent = log.agent_id;
      textBuffer.push(log);
    } else {
      flushTextBuffer();
      entries.push({ log, group: [log] });
    }
  }
  flushTextBuffer();
  return entries;
}

// ---------------------------------------------------------------------------
// Formatted Detail View (used inside TraceDetailModal)
// ---------------------------------------------------------------------------

function LogFormattedView({ entry }: { entry: DisplayEntry }) {
  const { log } = entry;
  const agentColors = getAgentColors(log.agent_id);

  return (
    <div className="space-y-4">
      {/* Text / merged text */}
      {log.type === 'text' && (
        <div>
          <h4 className="text-xs font-bold text-gray-500 uppercase mb-2">Response Content</h4>
          <div className="bg-gray-50 p-4 rounded-xl text-sm text-gray-700 whitespace-pre-wrap leading-relaxed">
            {entry.mergedContent || log.content}
          </div>
        </div>
      )}

      {/* Tool Use */}
      {log.type === 'tool_use' && log.tool_use && (
        <div>
          <h4 className="text-xs font-bold text-gray-500 uppercase mb-2">Tool Invocation</h4>
          <div className="bg-yellow-50 border border-yellow-200 p-4 rounded-xl">
            <div className="flex items-center gap-2 mb-3">
              <Cpu className="w-4 h-4 text-yellow-600" />
              <span className="font-bold text-yellow-800 text-sm">{log.tool_use.name}</span>
              {log.tool_use.execution_target && (
                <span className={`px-1.5 py-0.5 rounded text-[9px] font-medium ${log.tool_use.execution_target === 'client' ? 'bg-cyan-100 text-cyan-700' : 'bg-gray-100 text-gray-600'}`}>
                  {log.tool_use.execution_target}
                </span>
              )}
            </div>
            <h5 className="text-[10px] font-bold text-gray-400 uppercase mb-1">Input</h5>
            <pre className="bg-white p-3 rounded-lg text-xs overflow-x-auto border border-yellow-100 font-mono whitespace-pre-wrap break-all">
              {JSON.stringify(log.tool_use.input, null, 2)}
            </pre>
          </div>
        </div>
      )}

      {/* Tool Result */}
      {log.type === 'tool_result' && log.tool_result && (
        <div>
          <h4 className="text-xs font-bold text-gray-500 uppercase mb-2">Tool Result</h4>
          <div className="bg-orange-50 border border-orange-200 p-4 rounded-xl">
            <div className="flex items-center gap-2 mb-3">
              <FileText className="w-4 h-4 text-orange-600" />
              <span className="font-bold text-orange-800 text-sm">{log.tool_result.name}</span>
            </div>
            <h5 className="text-[10px] font-bold text-gray-400 uppercase mb-1">Output</h5>
            <pre className="bg-white p-3 rounded-lg text-xs overflow-x-auto border border-orange-100 font-mono whitespace-pre-wrap break-all">
              {typeof log.tool_result.result === 'string' ? log.tool_result.result : JSON.stringify(log.tool_result.result, null, 2)}
            </pre>
          </div>
        </div>
      )}

      {/* Handoff */}
      {log.type === 'handoff' && log.metadata && (
        <div>
          <h4 className="text-xs font-bold text-gray-500 uppercase mb-2">Agent Handoff</h4>
          <div className="bg-pink-50 border border-pink-200 p-4 rounded-xl">
            <div className="flex items-center gap-3 mb-3">
              <span className={`px-2 py-1 rounded text-xs font-bold ${agentColors.badge}`}>
                {getAgentName(log.agent_id)}
              </span>
              <ArrowRight className="w-4 h-4 text-pink-500" />
              <span className={`px-2 py-1 rounded text-xs font-bold ${getAgentColors(log.metadata.target_agent).badge}`}>
                {getAgentName(log.metadata.target_agent)}
              </span>
            </div>
            <p className="text-sm text-pink-800">{log.metadata.reason}</p>
          </div>
        </div>
      )}

      {/* Elicitation */}
      {log.type === 'elicitation' && log.elicitation && (
        <div>
          <h4 className="text-xs font-bold text-gray-500 uppercase mb-2">User Question</h4>
          <div className="bg-green-50 border border-green-200 p-4 rounded-xl">
            <p className="font-bold text-green-800 mb-2">{log.elicitation.question}</p>
            {log.elicitation.fields && log.elicitation.fields.length > 0 && (
              <pre className="bg-white p-3 rounded-lg text-xs overflow-x-auto border border-green-100 mt-2 font-mono">
                {JSON.stringify(log.elicitation.fields, null, 2)}
              </pre>
            )}
          </div>
        </div>
      )}

      {/* Reasoning */}
      {log.type === 'reasoning' && (
        <div>
          <h4 className="text-xs font-bold text-gray-500 uppercase mb-2">AI Reasoning</h4>
          <div className="bg-purple-50 border border-purple-200 p-4 rounded-xl">
            <div className="flex items-center gap-2 mb-3">
              <Brain className="w-4 h-4 text-purple-600" />
              <span className="font-bold text-purple-800 text-sm">Decision Rationale</span>
            </div>
            <pre className="bg-white p-3 rounded-lg text-xs overflow-x-auto border border-purple-100 font-mono whitespace-pre-wrap break-all">
              {(() => {
                try {
                  return JSON.stringify(JSON.parse(log.reasoning || log.content || '{}'), null, 2);
                } catch {
                  return log.reasoning || log.content || '';
                }
              })()}
            </pre>
          </div>
        </div>
      )}

      {/* User Input */}
      {log.type === 'user_input' && (
        <div>
          <h4 className="text-xs font-bold text-gray-500 uppercase mb-2">User Input</h4>
          <div className="bg-cyan-50 border border-cyan-200 p-4 rounded-xl flex items-start gap-2">
            <User className="w-4 h-4 text-cyan-600 shrink-0 mt-0.5" />
            <p className="text-sm text-cyan-800">{log.content}</p>
          </div>
        </div>
      )}

      {/* Form Submit */}
      {log.type === 'form_submit' && log.metadata && (
        <div>
          <h4 className="text-xs font-bold text-gray-500 uppercase mb-2">Form Submission</h4>
          <div className="bg-teal-50 border border-teal-200 p-4 rounded-xl">
            <div className="flex items-center gap-2 mb-3">
              <ClipboardCheck className="w-4 h-4 text-teal-600" />
              <span className="font-bold text-teal-800 text-sm">{log.metadata.formType || 'Form'}</span>
            </div>
            <pre className="bg-white p-3 rounded-lg text-xs overflow-x-auto border border-teal-100 font-mono whitespace-pre-wrap">
              {JSON.stringify(log.metadata, null, 2)}
            </pre>
          </div>
        </div>
      )}

      {/* Metadata */}
      {log.type === 'metadata' && log.metadata && (
        <div>
          <h4 className="text-xs font-bold text-gray-500 uppercase mb-2">Metadata</h4>
          <pre className="bg-indigo-50 border border-indigo-200 p-4 rounded-xl text-xs overflow-x-auto font-mono whitespace-pre-wrap">
            {JSON.stringify(log.metadata, null, 2)}
          </pre>
        </div>
      )}

      {/* Complete */}
      {log.type === 'complete' && (
        <div className="bg-gray-50 border border-gray-200 p-4 rounded-xl text-center">
          <CheckCircle2 className="w-6 h-6 text-gray-400 mx-auto mb-2" />
          <p className="text-gray-600 font-medium text-sm">Stream Complete</p>
          {log.metadata && (
            <pre className="text-xs text-gray-400 mt-2 font-mono">{JSON.stringify(log.metadata, null, 2)}</pre>
          )}
        </div>
      )}

      {/* Error */}
      {log.type === 'error' && (
        <div>
          <h4 className="text-xs font-bold text-gray-500 uppercase mb-2">Error</h4>
          <div className="bg-red-50 border border-red-200 p-4 rounded-xl flex items-start gap-2">
            <AlertCircle className="w-4 h-4 text-red-600 shrink-0 mt-0.5" />
            <p className="text-sm text-red-700 font-medium">{log.content}</p>
          </div>
        </div>
      )}

      {/* Event ID footer */}
      <div className="pt-3 border-t border-gray-100">
        <p className="text-[10px] text-gray-400 font-mono">
          {log.id} &middot; {formatTime(log.timestamp)}
        </p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Inline Log Card
// ---------------------------------------------------------------------------

function LogCard({ entry, onOpenDetail }: { entry: DisplayEntry; onOpenDetail: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const { log } = entry;
  const agentColors = getAgentColors(log.agent_id);
  const isText = log.type === 'text';
  const content = isText ? (entry.mergedContent ?? '') : '';

  // Compact preview text
  const preview = useMemo(() => {
    if (isText) return content.slice(0, 120) + (content.length > 120 ? '...' : '');
    if (log.type === 'tool_use' && log.tool_use) return log.tool_use.name;
    if (log.type === 'tool_result' && log.tool_result) {
      const r = typeof log.tool_result.result === 'string' ? log.tool_result.result : JSON.stringify(log.tool_result.result);
      return `${log.tool_result.name} \u2192 ${r.slice(0, 80)}`;
    }
    if (log.type === 'handoff' && log.metadata) return `\u2192 ${getAgentName(log.metadata.target_agent)}`;
    if (log.type === 'reasoning') {
      try {
        const r = JSON.parse(log.reasoning || log.content || '{}');
        return `${r.action || 'reasoning'}: ${r.determination || r.basis || ''}`.slice(0, 120);
      } catch { return log.reasoning?.slice(0, 120) || log.content?.slice(0, 120) || ''; }
    }
    if (log.type === 'user_input') return log.content?.slice(0, 120) ?? '';
    if (log.type === 'form_submit' && log.metadata) return `${log.metadata.formType || 'Form'}: ${log.content?.slice(0, 80) ?? 'Submitted'}`;
    if (log.type === 'elicitation' && log.elicitation) return log.elicitation.question;
    if (log.type === 'complete') return 'Stream complete';
    if (log.type === 'error') return log.content ?? 'Error';
    if (log.type === 'metadata') return JSON.stringify(log.metadata).slice(0, 80);
    return log.content?.slice(0, 80) ?? '';
  }, [log, isText, content]);

  // For text entries, show expand/collapse inline
  const hasExpandableContent = isText && content.length > 120;

  return (
    <div className={`rounded-xl border ${agentColors.border} ${agentColors.bg} font-mono text-[10px] leading-relaxed overflow-hidden transition-all group`}>
      {/* Header row */}
      <div
        className="flex items-center gap-1.5 px-3 py-2 cursor-pointer hover:brightness-95 transition"
        onClick={onOpenDetail}
      >
        <span className={`inline-flex items-center justify-center w-5 h-5 rounded-full text-[9px] font-bold text-white shrink-0 ${agentColors.icon}`}>
          {getAgentIcon(log.agent_id)}
        </span>
        <span className={`px-1.5 py-0.5 rounded text-[8px] font-bold uppercase shrink-0 ${agentColors.badge}`}>
          {getAgentName(log.agent_id)}
        </span>
        <span className={`px-1.5 py-0.5 rounded text-[8px] font-bold uppercase shrink-0 flex items-center gap-0.5 ${getEventTypeBadge(log.type)}`}>
          {getEventIcon(log.type)}
          {formatEventType(log.type, log)}
        </span>
        {entry.group.length > 1 && (
          <span className="px-1 py-0.5 rounded bg-white/60 text-[8px] text-gray-500 shrink-0">
            {entry.group.length}x
          </span>
        )}
        <span className="ml-auto text-[9px] text-gray-400 shrink-0">{formatTime(log.timestamp)}</span>
      </div>

      {/* Content preview */}
      <div className={`px-3 pb-2 ${agentColors.text}`}>
        {/* Inline tool_use — show input params compactly */}
        {log.type === 'tool_use' && log.tool_use && (
          <div className="flex items-center gap-1 text-[10px]">
            <Cpu className="w-3 h-3 shrink-0" />
            <span className="font-bold">{log.tool_use.name}</span>
            <span className="text-gray-500 truncate">({JSON.stringify(log.tool_use.input).slice(0, 60)})</span>
          </div>
        )}

        {/* Handoff — show source → target */}
        {log.type === 'handoff' && log.metadata && (
          <div className="flex items-center gap-2 text-[10px]">
            <ArrowRight className="w-3 h-3 shrink-0" />
            <span className="font-bold">Handoff to</span>
            <span className={`px-1 py-0.5 rounded ${getAgentColors(log.metadata.target_agent).badge}`}>
              {getAgentName(log.metadata.target_agent)}
            </span>
            {log.metadata.reason && <span className="text-gray-500 truncate">({log.metadata.reason})</span>}
          </div>
        )}

        {/* Text — collapsed or expanded */}
        {isText && (
          <div>
            <p className={`text-[10px] break-words ${expanded ? '' : 'line-clamp-2'}`}>
              {expanded ? content : preview}
            </p>
            {hasExpandableContent && (
              <button
                onClick={(e) => { e.stopPropagation(); setExpanded(!expanded); }}
                className="flex items-center gap-0.5 mt-1 text-[9px] text-gray-400 hover:text-gray-600 transition"
              >
                {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                {expanded ? 'Collapse' : `Show all (${content.length} chars)`}
              </button>
            )}
          </div>
        )}

        {/* User input */}
        {log.type === 'user_input' && (
          <div className="flex items-start gap-1 text-[10px]">
            <User className="w-3 h-3 shrink-0 mt-0.5" />
            <span className="break-words">{preview}</span>
          </div>
        )}

        {/* Tool result — compact */}
        {log.type === 'tool_result' && log.tool_result && (
          <div className="text-[10px] truncate">
            <span className="font-bold">{log.tool_result.name}</span>
            <span className="text-gray-500"> \u2192 </span>
            <span className="text-gray-600">
              {(typeof log.tool_result.result === 'string' ? log.tool_result.result : JSON.stringify(log.tool_result.result)).slice(0, 80)}
            </span>
          </div>
        )}

        {/* Elicitation */}
        {log.type === 'elicitation' && log.elicitation && (
          <div className="flex items-start gap-1 text-[10px]">
            <Zap className="w-3 h-3 shrink-0 mt-0.5" />
            <span>{log.elicitation.question}</span>
          </div>
        )}

        {/* Form submit */}
        {log.type === 'form_submit' && (
          <div className="flex items-start gap-1 text-[10px]">
            <ClipboardCheck className="w-3 h-3 shrink-0 mt-0.5" />
            <span>{preview}</span>
          </div>
        )}

        {/* Reasoning */}
        {log.type === 'reasoning' && (
          <div className="flex items-start gap-1 text-[10px]">
            <Brain className="w-3 h-3 shrink-0 mt-0.5 text-purple-600" />
            <span className="text-purple-700">{preview}</span>
          </div>
        )}

        {/* Error */}
        {log.type === 'error' && (
          <div className="flex items-start gap-1 text-[10px] text-red-600 font-bold">
            <AlertCircle className="w-3 h-3 shrink-0 mt-0.5" />
            <span>{log.content}</span>
          </div>
        )}

        {/* Complete */}
        {log.type === 'complete' && (
          <div className="text-[10px] text-gray-500">--- Stream Complete ---</div>
        )}

        {/* Metadata */}
        {log.type === 'metadata' && log.metadata && (
          <div className="text-[10px] text-gray-500 truncate">
            {JSON.stringify(log.metadata).slice(0, 100)}
          </div>
        )}
      </div>

      {/* Click hint */}
      <div className="px-3 pb-1.5 text-right">
        <span className="text-[8px] text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity">
          Click header to expand
        </span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

interface AgentLogsProps {
  logs: AuditLogEntry[];
}

export default function AgentLogs({ logs }: AgentLogsProps) {
  const [selectedEntry, setSelectedEntry] = useState<DisplayEntry | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const entries = useMemo(() => buildDisplayEntries(logs), [logs]);

  // Auto-scroll to bottom on new entries
  useEffect(() => {
    const el = scrollRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [entries.length]);

  if (entries.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-48 text-center px-4">
        <div className="w-10 h-10 rounded-full bg-gray-100 flex items-center justify-center mb-3">
          <Cpu className="w-5 h-5 text-gray-400" />
        </div>
        <p className="text-sm text-gray-500">No agent events yet.</p>
        <p className="text-xs text-gray-400 mt-1">Events will appear here as the agent processes your request.</p>
      </div>
    );
  }

  return (
    <>
      <div ref={scrollRef} className="space-y-2">
        {entries.map((entry, i) => (
          <LogCard
            key={entry.log.id + '-' + i}
            entry={entry}
            onOpenDetail={() => setSelectedEntry(entry)}
          />
        ))}
      </div>

      {selectedEntry && (
        <TraceDetailModal
          isOpen={true}
          onClose={() => setSelectedEntry(null)}
          data={selectedEntry.group.length > 1 ? selectedEntry.group : selectedEntry.log}
          downloadFilename={`agent-log-${selectedEntry.log.id}.json`}
          header={
            <>
              <span className={`inline-flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold text-white ${getAgentColors(selectedEntry.log.agent_id).icon}`}>
                {getAgentIcon(selectedEntry.log.agent_id)}
              </span>
              <span className={`px-2 py-1 rounded text-xs font-bold uppercase ${getAgentColors(selectedEntry.log.agent_id).badge}`}>
                {getAgentName(selectedEntry.log.agent_id)}
              </span>
              <span className={`px-2 py-1 rounded text-xs font-bold uppercase ${getEventTypeBadge(selectedEntry.log.type)}`}>
                {formatEventType(selectedEntry.log.type, selectedEntry.log)}
              </span>
              {selectedEntry.group.length > 1 && (
                <span className="text-[10px] text-gray-400">({selectedEntry.group.length} chunks)</span>
              )}
              <span className="text-xs text-gray-400 ml-auto">{formatTime(selectedEntry.log.timestamp)}</span>
            </>
          }
          formattedView={<LogFormattedView entry={selectedEntry} />}
        />
      )}
    </>
  );
}
