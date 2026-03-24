'use client';

import { useState, useRef, useEffect, useMemo, useCallback } from 'react';
import { X, Copy, Check, Code } from 'lucide-react';
import { AuditLogEntry } from '@/types/stream';
import { TOOL_META } from './tool-use-display';
import { ToolTimingSummary } from './tool-result-panels';

// ---------------------------------------------------------------------------
// Tool helpers (mirrors SSE event viewer)
// ---------------------------------------------------------------------------

function getToolMeta(name: string) {
  return TOOL_META[name] ?? { icon: '\u2699\uFE0F', label: name.replace(/_/g, ' ') };
}

function summarizeToolInput(name: string, input: Record<string, unknown>): string {
  if (!input || Object.keys(input).length === 0) return '';
  switch (name) {
    case 'think': { const t = String(input.thought ?? ''); return t.slice(0, 60) + (t.length > 60 ? '...' : ''); }
    case 'search_far': return String(input.query ?? '');
    case 'web_search': return String(input.query ?? '');
    case 'web_fetch': {
      const u = String(input.url ?? '');
      try { return new URL(u).hostname + new URL(u).pathname.slice(0, 30); } catch { return u.slice(0, 60); }
    }
    case 'knowledge_search': return String(input.query ?? input.topic ?? '');
    case 'knowledge_fetch': { const k = String(input.s3_key ?? ''); return k.split('/').pop() || k; }
    case 'create_document': {
      const dt = String(input.doc_type ?? '').replace(/_/g, ' ');
      return input.title ? dt + ': ' + String(input.title) : dt;
    }
    case 'edit_docx_document': { const k = String(input.document_key ?? ''); return k.split('/').pop() || k; }
    case 'load_skill': return String(input.name ?? '');
    default: { const q = String(input.query ?? input.prompt ?? input.message ?? ''); return q.slice(0, 60) + (q.length > 60 ? '...' : ''); }
  }
}

function summarizeToolResult(name: string, result: unknown): string {
  if (typeof result === 'string') return result.slice(0, 50);
  if (!result || typeof result !== 'object') return '';
  const r = result as Record<string, unknown>;
  if (r.clauses) return String(r.results_count ?? '') + ' results';
  if (r.sources) return String(r.source_count ?? '') + ' sources';
  if (Array.isArray(r.results)) return r.results.length + ' results';
  if (r.document_type) return String(r.document_type ?? '').replace(/_/g, ' ');
  if (r.report) return 'report';
  return '';
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** A display entry that may collapse multiple raw log entries. */
interface DisplayEntry {
  log: AuditLogEntry;
  group: AuditLogEntry[];
  mergedContent?: string;
  nested: boolean;
}

// ---------------------------------------------------------------------------
// Build display entries with nesting detection
// ---------------------------------------------------------------------------

/** Subagent tool names (matches SSE viewer logic). */
const SUBAGENT_TOOLS = new Set([
  'oa_intake', 'legal_counsel', 'market_intelligence', 'tech_translator',
  'tech_review', 'public_interest', 'compliance', 'policy_analyst',
  'policy_librarian', 'policy_supervisor', 'document_generator',
  'ingest_document', 'knowledge_retrieval',
]);

function buildDisplayEntries(logs: AuditLogEntry[]): DisplayEntry[] {
  const entries: DisplayEntry[] = [];
  let textBuffer: AuditLogEntry[] = [];
  let textAgent: string | null = null;

  function flushTextBuffer() {
    if (textBuffer.length === 0) return;
    const merged = textBuffer.map(l => l.content ?? '').join('');
    if (merged.trim() !== '') {
      entries.push({
        log: textBuffer[textBuffer.length - 1],
        group: [...textBuffer],
        mergedContent: merged,
        nested: false,
      });
    }
    textBuffer = [];
    textAgent = null;
  }

  for (const log of logs) {
    if (log.type === 'text') {
      if (textAgent && textAgent !== log.agent_id) flushTextBuffer();
      textAgent = log.agent_id;
      textBuffer.push(log);
    } else {
      flushTextBuffer();
      entries.push({ log, group: [log], nested: false });
    }
  }
  flushTextBuffer();

  // Mark nested entries: tool events that occur between a subagent tool_use
  // and its tool_result are "nested" (internal to the subagent).
  const openSubagents = new Set<string>();
  for (const entry of entries) {
    const { log } = entry;
    if (log.type === 'tool_use' && log.tool_use && SUBAGENT_TOOLS.has(log.tool_use.name)) {
      openSubagents.add(log.tool_use.name);
    } else if (log.type === 'tool_result' && log.tool_result && openSubagents.has(log.tool_result.name)) {
      openSubagents.delete(log.tool_result.name);
    } else if (openSubagents.size > 0) {
      // Any event while a subagent is open is nested
      if (log.type === 'tool_use' || log.type === 'tool_result' || log.type === 'agent_status') {
        entry.nested = true;
      }
    }
  }

  return entries;
}

// ---------------------------------------------------------------------------
// Badge styles (matches SSE event viewer colors)
// ---------------------------------------------------------------------------

const BADGE_STYLES: Record<string, string> = {
  text:          'bg-[#E8F0FE] text-[#003366]',
  tool_use:      'bg-[#E8F0FE] text-[#004488]',
  tool_result:   'bg-[#F3EAFF] text-[#7740A4]',
  agent_status:  'bg-[#FFF3E0] text-[#E65100]',
  reasoning:     'bg-gray-100 text-gray-500',
  handoff:       'bg-[#FFF3E0] text-[#E65100]',
  complete:      'bg-gray-100 text-gray-500',
  error:         'bg-[#FDECEA] text-[#BB0E3D]',
  metadata:      'bg-gray-100 text-gray-400',
  user_input:    'bg-[#E3F2FD] text-[#0B6ED7]',
  elicitation:   'bg-[#E8F5E9] text-[#037F0C]',
};

function getBadgeStyle(type: string) {
  return BADGE_STYLES[type] ?? 'bg-gray-100 text-gray-400';
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatTime(timestamp: string): string {
  try {
    return new Date(timestamp).toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return '';
  }
}

function getSummary(entry: DisplayEntry): string {
  const { log } = entry;
  switch (log.type) {
    case 'text':
      return (entry.mergedContent ?? log.content ?? '').slice(0, 60) + ((entry.mergedContent ?? log.content ?? '').length > 60 ? '...' : '');
    case 'tool_use': {
      if (!log.tool_use) return '';
      const tm = getToolMeta(log.tool_use.name);
      const inp = summarizeToolInput(log.tool_use.name, (log.tool_use.input ?? {}) as Record<string, unknown>);
      return tm.icon + ' ' + tm.label + (inp ? ' \u2014 "' + inp.slice(0, 40) + (inp.length > 40 ? '...' : '') + '"' : '');
    }
    case 'tool_result': {
      if (!log.tool_result) return '';
      const trm = getToolMeta(log.tool_result.name);
      const detail = summarizeToolResult(log.tool_result.name, log.tool_result.result);
      return (entry.nested ? '\u2514 ' : '') + trm.icon + ' ' + trm.label + (detail ? ' (' + detail + ')' : '');
    }
    case 'agent_status':
      return (log.metadata as Record<string, string>)?.status ?? '';
    case 'handoff':
      return '\u2192 ' + ((log.metadata as Record<string, string>)?.target_agent ?? 'specialist');
    case 'reasoning':
      return 'Thinking...';
    case 'complete': {
      const ms = (log.metadata as Record<string, number>)?.duration_ms ?? 0;
      return ms ? ms + 'ms total' : 'Stream complete';
    }
    case 'error':
      return log.content ?? 'Error';
    case 'user_input':
      return (log.content ?? '').slice(0, 60);
    default:
      return log.content?.slice(0, 60) ?? log.type;
  }
}

// ---------------------------------------------------------------------------
// Detail Modal
// ---------------------------------------------------------------------------

function LogDetailModal({ entry, onClose }: { entry: DisplayEntry; onClose: () => void }) {
  const [showRaw, setShowRaw] = useState(false);
  const [copied, setCopied] = useState(false);
  const { log } = entry;

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, [onClose]);

  const handleCopy = useCallback(async () => {
    const payload = entry.group.length > 1 ? entry.group : log;
    await navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [entry, log]);

  const content = entry.mergedContent ?? log.content ?? '';
  const meta = log.metadata as Record<string, unknown> | undefined;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div
        className="bg-white rounded-xl shadow-2xl max-w-2xl w-full max-h-[80vh] flex flex-col overflow-hidden border border-[#D8DEE6]"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#D8DEE6]">
          <div className="flex items-center gap-2">
            <span className={`px-2 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider ${getBadgeStyle(log.type)}`}>
              {log.type === 'text' ? 'agent' : log.type === 'user_input' ? 'user' : log.type.replace('_', ' ')}
            </span>
            {log.tool_use && (
              <span className="text-xs text-gray-800">{getToolMeta(log.tool_use.name).icon} {log.tool_use.name}</span>
            )}
            {log.tool_result && (
              <span className="text-xs text-gray-800">{getToolMeta(log.tool_result.name).icon} {log.tool_result.name}</span>
            )}
            {entry.group.length > 1 && (
              <span className="text-[10px] text-gray-400">({entry.group.length} chunks)</span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-gray-400 font-mono">{formatTime(log.timestamp)}</span>
            <button onClick={onClose} className="p-1 hover:bg-gray-100 rounded transition">
              <X className="w-4 h-4 text-gray-400" />
            </button>
          </div>
        </div>

        {/* Toggle bar */}
        <div className="flex items-center justify-end gap-2 px-4 py-2 border-b border-[#D8DEE6]">
          <button onClick={handleCopy} className="flex items-center gap-1 px-2 py-1 text-[10px] text-gray-500 bg-[#F5F7FA] hover:bg-[#EDF0F4] rounded border border-[#D8DEE6] transition">
            {copied ? <Check className="w-3 h-3 text-[#037F0C]" /> : <Copy className="w-3 h-3" />}
            {copied ? 'Copied!' : 'Copy JSON'}
          </button>
          <button
            onClick={() => setShowRaw(!showRaw)}
            className={`flex items-center gap-1 px-2 py-1 text-[10px] rounded border transition ${
              showRaw ? 'bg-[#003366] text-white border-[#003366]' : 'text-gray-500 bg-[#F5F7FA] hover:bg-[#EDF0F4] border-[#D8DEE6]'
            }`}
          >
            <Code className="w-3 h-3" />
            {showRaw ? 'Formatted' : 'Raw JSON'}
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4">
          {showRaw ? (
            <pre className="text-[#003366] bg-[#F5F7FA] p-4 rounded-lg text-xs font-mono whitespace-pre-wrap break-all">
              {JSON.stringify(entry.group.length > 1 ? entry.group : log, null, 2)}
            </pre>
          ) : (
            <div className="space-y-4">
              {/* Text */}
              {log.type === 'text' && (
                <div className="bg-[#F5F7FA] p-4 rounded-lg text-sm text-gray-800 whitespace-pre-wrap leading-relaxed">
                  {content}
                </div>
              )}

              {/* Reasoning */}
              {log.type === 'reasoning' && (
                <div className="bg-[#F5F7FA] border border-[#D8DEE6] p-4 rounded-lg">
                  <p className="text-sm text-gray-500 italic whitespace-pre-wrap">{content}</p>
                </div>
              )}

              {/* Tool Use */}
              {log.type === 'tool_use' && log.tool_use && (
                <div className="bg-[#F5F7FA] border border-[#D8DEE6] p-4 rounded-lg">
                  <div className="flex items-center gap-2 mb-3">
                    <span className="text-lg">{getToolMeta(log.tool_use.name).icon}</span>
                    <span className="font-bold text-[#004488] text-sm">{getToolMeta(log.tool_use.name).label}</span>
                    <span className="text-[10px] text-gray-400 font-mono">{log.tool_use.name}</span>
                  </div>
                  <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-1">Input</div>
                  <pre className="bg-white border border-[#D8DEE6] p-3 rounded text-xs text-gray-800 font-mono whitespace-pre-wrap break-all">
                    {JSON.stringify(log.tool_use.input, null, 2)}
                  </pre>
                </div>
              )}

              {/* Tool Result */}
              {log.type === 'tool_result' && log.tool_result && (
                <div className="bg-[#F5F7FA] border border-[#D8DEE6] p-4 rounded-lg">
                  <div className="flex items-center gap-2 mb-3">
                    <span className="text-lg">{getToolMeta(log.tool_result.name).icon}</span>
                    <span className="font-bold text-[#7740A4] text-sm">{getToolMeta(log.tool_result.name).label}</span>
                  </div>
                  <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-1">Output</div>
                  <pre className="bg-white border border-[#D8DEE6] p-3 rounded text-xs text-gray-800 font-mono whitespace-pre-wrap break-all max-h-[300px] overflow-y-auto">
                    {typeof log.tool_result.result === 'string' ? log.tool_result.result : JSON.stringify(log.tool_result.result, null, 2)}
                  </pre>
                </div>
              )}

              {/* Handoff */}
              {log.type === 'handoff' && meta && (
                <div className="bg-[#FFF3E0] border border-[#E65100]/20 p-4 rounded-lg">
                  <div className="flex items-center gap-3">
                    <span className="text-[#E65100] font-bold">{'\u{1F91D}'} Handing off to</span>
                    <span className="px-2 py-1 rounded bg-white text-[#E65100] text-xs font-bold border border-[#E65100]/20">
                      {String(meta.target_agent ?? '')}
                    </span>
                  </div>
                  {meta.reason ? <p className="text-sm text-gray-500 mt-2">{String(meta.reason)}</p> : null}
                </div>
              )}

              {/* Agent Status */}
              {log.type === 'agent_status' && meta && (
                <div className="bg-[#FFF3E0] border border-[#E65100]/20 p-4 rounded-lg">
                  <p className="text-sm text-[#E65100] font-medium">{String(meta.status ?? '')}</p>
                  {meta.detail ? <p className="text-xs text-gray-400 mt-1">{String(meta.detail)}</p> : null}
                </div>
              )}

              {/* Complete */}
              {log.type === 'complete' && (
                <div className="bg-[#F5F7FA] border border-[#D8DEE6] p-4 rounded-lg">
                  {meta?.tool_timings ? (
                    <ToolTimingSummary metadata={meta} />
                  ) : (
                    <pre className="text-xs text-gray-500 font-mono">{JSON.stringify(meta, null, 2)}</pre>
                  )}
                </div>
              )}

              {/* Error */}
              {log.type === 'error' && (
                <div className="bg-[#FDECEA] border border-[#BB0E3D]/20 p-4 rounded-lg">
                  <p className="text-sm text-[#BB0E3D] font-medium">{content}</p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Timeline Row
// ---------------------------------------------------------------------------

function TimelineRow({ entry, isSelected, onSelect }: {
  entry: DisplayEntry;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const { log, nested } = entry;
  const summary = getSummary(entry);

  return (
    <div
      className={`flex items-start gap-2.5 py-2 px-3 cursor-pointer border-l-[3px] transition-colors ${
        isSelected
          ? 'bg-[#E8F0FE] border-l-[#003366]'
          : 'border-l-transparent hover:bg-[#F5F7FA]'
      }`}
      style={nested ? { paddingLeft: '28px' } : undefined}
      onClick={onSelect}
    >
      {/* Badge */}
      <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider whitespace-nowrap min-w-[56px] text-center shrink-0 mt-0.5 ${
        nested ? 'bg-[#FFF3E0] text-[#E65100] text-[8px]' : getBadgeStyle(log.type)
      }`}>
        {nested ? 'nested' : log.type === 'text' ? 'agent' : log.type === 'user_input' ? 'user' : log.type.replace('_', ' ')}
      </span>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="text-[12px] text-gray-800 truncate">
          {summary}
        </div>
        <div className="text-[10px] text-gray-400 font-mono mt-0.5">
          {formatTime(log.timestamp)}
          {nested && (
            <span className="text-[#E65100] text-[9px] ml-2">via subagent</span>
          )}
        </div>
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
  const [selectedIdx, setSelectedIdx] = useState<number>(-1);
  const scrollRef = useRef<HTMLDivElement>(null);

  const entries = useMemo(() => buildDisplayEntries(logs), [logs]);

  // Auto-scroll to bottom on new entries
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [entries.length]);

  const selectedEntry = selectedIdx >= 0 && selectedIdx < entries.length ? entries[selectedIdx] : null;

  if (entries.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-48 text-center px-4">
        <div className="text-2xl mb-2">{'\u{1F4E1}'}</div>
        <p className="text-sm text-gray-500">No events yet</p>
        <p className="text-xs text-gray-400 mt-1">Events will appear as the agent processes your request.</p>
      </div>
    );
  }

  return (
    <>
      {/* Event count header */}
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] text-gray-400 font-semibold uppercase tracking-wider">
          {entries.length} event{entries.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Timeline */}
      <div
        ref={scrollRef}
        className="bg-white rounded-lg border border-[#D8DEE6] overflow-y-auto -mx-4"
        style={{ maxHeight: 'calc(100vh - 240px)' }}
      >
        {entries.map((entry, i) => (
          <TimelineRow
            key={entry.log.id + '-' + i}
            entry={entry}
            isSelected={i === selectedIdx}
            onSelect={() => setSelectedIdx(i === selectedIdx ? -1 : i)}
          />
        ))}
      </div>

      {/* Detail modal */}
      {selectedEntry && (
        <LogDetailModal entry={selectedEntry} onClose={() => setSelectedIdx(-1)} />
      )}
    </>
  );
}
