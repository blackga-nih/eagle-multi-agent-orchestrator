'use client';

import { useState, useRef, useEffect, useMemo } from 'react';
import { Cpu, MessageSquare, Zap, Clock, Hash, BarChart2, Radio, Square } from 'lucide-react';
import { AuditLogEntry } from '@/types/stream';
import { getAgentColors, getAgentName, getAgentIcon } from '@/lib/agent-colors';
import TraceDetailModal from './trace-detail-modal';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** A Bedrock trace event — derived from raw Bedrock ConverseStream chunk keys. */
interface BedrockTraceEntry {
  id: string;
  timestamp: string;
  /** Derived category from inspecting the raw event keys. */
  event_type:
    | 'block_start'
    | 'block_delta'
    | 'block_stop'
    | 'message_stop'
    | 'usage'
    | 'text_delta'
    | 'tool_stream'
    | 'result'
    | 'unknown';
  /** Human-readable label: tool name, delta type, token counts, etc. */
  label: string;
  /** Full raw event payload. */
  raw: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatTime(ts: string): string {
  try {
    return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return '';
  }
}

const CATEGORY_STYLES: Record<BedrockTraceEntry['event_type'], { badge: string; icon: React.ReactNode }> = {
  block_start:  { badge: 'bg-violet-100 text-violet-700',  icon: <Zap       className="w-3 h-3" /> },
  block_delta:  { badge: 'bg-blue-100 text-blue-700',      icon: <Radio     className="w-3 h-3" /> },
  block_stop:   { badge: 'bg-indigo-100 text-indigo-700',  icon: <Square    className="w-3 h-3" /> },
  message_stop: { badge: 'bg-gray-100 text-gray-600',      icon: <Hash      className="w-3 h-3" /> },
  usage:        { badge: 'bg-emerald-100 text-emerald-700',icon: <BarChart2  className="w-3 h-3" /> },
  text_delta:   { badge: 'bg-sky-100 text-sky-700',        icon: <MessageSquare className="w-3 h-3" /> },
  tool_stream:  { badge: 'bg-yellow-100 text-yellow-800',  icon: <Cpu       className="w-3 h-3" /> },
  result:       { badge: 'bg-orange-100 text-orange-700',  icon: <Cpu       className="w-3 h-3" /> },
  unknown:      { badge: 'bg-gray-100 text-gray-500',      icon: <Hash      className="w-3 h-3" /> },
};

/**
 * Classify a raw Bedrock trace payload into a BedrockTraceEntry.
 * Inspects top-level keys of the event to determine the category.
 */
function classifyBedrockEvent(
  id: string,
  timestamp: string,
  raw: Record<string, unknown>,
): BedrockTraceEntry {
  // Unwrap nested "event" key if present (backend wraps Bedrock events this way)
  const inner = (typeof raw.event === 'object' && raw.event !== null)
    ? raw.event as Record<string, unknown>
    : raw;

  // contentBlockStart — tool or text block beginning
  if ('contentBlockStart' in inner) {
    const cbs = inner.contentBlockStart as Record<string, unknown> | undefined;
    const start = cbs?.start as Record<string, unknown> | undefined;
    const toolName = (start?.toolUse as Record<string, unknown> | undefined)?.name as string | undefined;
    return {
      id, timestamp, raw,
      event_type: 'block_start',
      label: toolName ? `tool: ${toolName}` : 'text',
    };
  }

  // contentBlockDelta — streaming delta fragment
  if ('contentBlockDelta' in inner) {
    const cbd = inner.contentBlockDelta as Record<string, unknown> | undefined;
    const delta = cbd?.delta as Record<string, unknown> | undefined;
    const deltaType = delta ? Object.keys(delta)[0] ?? 'delta' : 'delta';
    return {
      id, timestamp, raw,
      event_type: 'block_delta',
      label: deltaType,
    };
  }

  // contentBlockStop
  if ('contentBlockStop' in inner) {
    return { id, timestamp, raw, event_type: 'block_stop', label: 'block stop' };
  }

  // messageStop — stop reason
  if ('messageStop' in inner) {
    const ms = inner.messageStop as Record<string, unknown> | undefined;
    const reason = (ms?.stopReason as string | undefined) ?? 'end_turn';
    return { id, timestamp, raw, event_type: 'message_stop', label: reason };
  }

  // metadata with usage — token counts
  if ('metadata' in inner) {
    const meta = inner.metadata as Record<string, unknown> | undefined;
    const usage = meta?.usage as Record<string, unknown> | undefined;
    if (usage) {
      const inp = (usage.inputTokens as number | undefined) ?? 0;
      const out = (usage.outputTokens as number | undefined) ?? 0;
      return {
        id, timestamp, raw,
        event_type: 'usage',
        label: `${inp} in / ${out} out tokens`,
      };
    }
  }

  // data (string) — text delta from simplified streaming
  if ('data' in inner && typeof inner.data === 'string') {
    const preview = (inner.data as string).slice(0, 40);
    return {
      id, timestamp, raw,
      event_type: 'text_delta',
      label: preview || 'text chunk',
    };
  }

  // current_tool_use — tool streaming state
  if ('current_tool_use' in inner) {
    const ctu = inner.current_tool_use as Record<string, unknown> | undefined;
    const name = (ctu?.name as string | undefined) ?? 'tool';
    return { id, timestamp, raw, event_type: 'tool_stream', label: name };
  }

  // result — tool/agent result payload
  if ('result' in inner) {
    return { id, timestamp, raw, event_type: 'result', label: 'result' };
  }

  return { id, timestamp, raw, event_type: 'unknown', label: Object.keys(inner).join(', ') || 'event' };
}

/**
 * Build BedrockTraceEntry[] from either raw bedrock traces (preferred) or
 * AuditLogEntry[] fallback when no bedrock_trace events have arrived yet.
 */
function buildBedrockEntries(
  bedrockTraces: Record<string, unknown>[],
  logs: AuditLogEntry[],
): BedrockTraceEntry[] {
  // Prefer raw bedrock traces when available
  if (bedrockTraces.length > 0) {
    return bedrockTraces.map((trace, i) => {
      const timestamp = (trace.timestamp as string | undefined) ?? new Date().toISOString();
      return classifyBedrockEvent(`bt-${i}`, timestamp, trace);
    });
  }

  // Fallback: derive entries from SSE audit logs (bedrock_trace type only)
  const entries: BedrockTraceEntry[] = [];
  for (const log of logs) {
    if (log.type !== 'bedrock_trace') continue;
    const raw = (log.metadata ?? {}) as Record<string, unknown>;
    entries.push(classifyBedrockEvent(log.id, log.timestamp, raw));
  }
  return entries;
}

// ---------------------------------------------------------------------------
// Trace Card
// ---------------------------------------------------------------------------

function TraceCard({ entry, onClick }: { entry: BedrockTraceEntry; onClick: () => void }) {
  const style = CATEGORY_STYLES[entry.event_type] ?? CATEGORY_STYLES.unknown;

  return (
    <div
      className="rounded-lg border border-gray-200 bg-white hover:shadow-sm transition cursor-pointer group"
      onClick={onClick}
    >
      <div className="flex items-center gap-1.5 px-3 py-2">
        {/* Event type badge */}
        <span className={`px-1.5 py-0.5 rounded text-[8px] font-bold uppercase shrink-0 flex items-center gap-0.5 ${style.badge}`}>
          {style.icon}
          {entry.event_type.replace(/_/g, ' ')}
        </span>

        {/* Label */}
        <span className="text-[10px] text-gray-700 font-mono truncate flex-1">{entry.label}</span>

        {/* Timestamp */}
        <span className="text-[9px] text-gray-400 shrink-0">{formatTime(entry.timestamp)}</span>
      </div>

      {/* Click hint */}
      <div className="px-3 pb-1 text-right">
        <span className="text-[8px] text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity">
          Click to expand
        </span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Formatted Detail View
// ---------------------------------------------------------------------------

function TraceFormattedView({ entry }: { entry: BedrockTraceEntry }) {
  const style = CATEGORY_STYLES[entry.event_type] ?? CATEGORY_STYLES.unknown;

  return (
    <div className="space-y-4">
      {/* Summary */}
      <div className="bg-gray-50 border border-gray-200 rounded-xl p-4">
        <div className="flex items-center gap-2 mb-2">
          <span className={`px-2 py-1 rounded text-xs font-bold uppercase flex items-center gap-1 ${style.badge}`}>
            {style.icon}
            {entry.event_type.replace(/_/g, ' ')}
          </span>
        </div>
        <p className="text-sm font-mono text-gray-700">{entry.label}</p>
        <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
          <span>{formatTime(entry.timestamp)}</span>
        </div>
      </div>

      {/* Usage stats */}
      {entry.event_type === 'usage' && (
        <div>
          <h4 className="text-xs font-bold text-gray-500 uppercase mb-2">Token Usage</h4>
          <pre className="bg-emerald-50 border border-emerald-200 p-4 rounded-xl text-xs font-mono whitespace-pre-wrap break-all">
            {JSON.stringify(
              ((entry.raw.metadata as Record<string, unknown> | undefined)?.usage) ?? entry.raw,
              null, 2
            )}
          </pre>
        </div>
      )}

      {/* Tool stream state */}
      {(entry.event_type === 'tool_stream' || entry.event_type === 'block_start') && (
        <div>
          <h4 className="text-xs font-bold text-gray-500 uppercase mb-2">Event Payload</h4>
          <pre className="bg-yellow-50 border border-yellow-200 p-4 rounded-xl text-xs font-mono whitespace-pre-wrap break-all">
            {JSON.stringify(entry.raw, null, 2)}
          </pre>
        </div>
      )}

      {/* Text delta content */}
      {entry.event_type === 'text_delta' && (
        <div>
          <h4 className="text-xs font-bold text-gray-500 uppercase mb-2">Content</h4>
          <div className="bg-sky-50 border border-sky-200 p-4 rounded-xl text-sm whitespace-pre-wrap">
            {(entry.raw.data as string | undefined) || JSON.stringify(entry.raw)}
          </div>
        </div>
      )}

      {/* Raw JSON fallback for all other types */}
      {!['usage', 'tool_stream', 'block_start', 'text_delta'].includes(entry.event_type) && (
        <div>
          <h4 className="text-xs font-bold text-gray-500 uppercase mb-2">Raw Payload</h4>
          <pre className="bg-gray-50 border border-gray-200 p-4 rounded-xl text-xs font-mono whitespace-pre-wrap break-all">
            {JSON.stringify(entry.raw, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

interface BedrockLogsProps {
  /** Raw Bedrock trace payloads (from onBedrockTrace). Preferred data source. */
  bedrockTraces?: Record<string, unknown>[];
  /** Fallback: SSE audit log entries (used when no bedrock traces yet). */
  logs?: AuditLogEntry[];
}

export default function BedrockLogs({ bedrockTraces = [], logs = [] }: BedrockLogsProps) {
  const [selectedEntry, setSelectedEntry] = useState<BedrockTraceEntry | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const entries = useMemo(() => buildBedrockEntries(bedrockTraces, logs), [bedrockTraces, logs]);

  // Auto-scroll to bottom
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [entries.length]);

  if (entries.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-48 text-center px-4">
        <div className="w-10 h-10 rounded-full bg-gray-100 flex items-center justify-center mb-3">
          <Cpu className="w-5 h-5 text-gray-400" />
        </div>
        <p className="text-sm text-gray-500">No Bedrock traces yet.</p>
        <p className="text-xs text-gray-400 mt-1">Traces will appear here as the agent processes requests.</p>
      </div>
    );
  }

  // Summary stats
  const usageEntry = entries.find(e => e.event_type === 'usage');
  const toolCount = entries.filter(e => e.event_type === 'block_start' && e.label.startsWith('tool:')).length;

  return (
    <>
      {/* Summary bar */}
      <div className="flex items-center gap-3 mb-3 text-[10px] text-gray-500">
        <span>{entries.length} events</span>
        {toolCount > 0 && <span>{toolCount} tool calls</span>}
        {usageEntry && <span className="font-mono">{usageEntry.label}</span>}
      </div>

      <div ref={scrollRef} className="space-y-1.5">
        {entries.map((entry) => (
          <TraceCard
            key={entry.id}
            entry={entry}
            onClick={() => setSelectedEntry(entry)}
          />
        ))}
      </div>

      {selectedEntry && (
        <TraceDetailModal
          isOpen={true}
          onClose={() => setSelectedEntry(null)}
          data={selectedEntry.raw}
          downloadFilename={`bedrock-trace-${selectedEntry.id}.json`}
          header={
            <>
              <Cpu className="w-4 h-4 text-violet-600 shrink-0" />
              <span className="text-sm font-bold text-gray-900">Bedrock Trace</span>
              <span className="text-xs text-gray-500">{selectedEntry.label}</span>
              <span className="text-xs text-gray-400 ml-auto">{formatTime(selectedEntry.timestamp)}</span>
            </>
          }
          formattedView={<TraceFormattedView entry={selectedEntry} />}
        />
      )}
    </>
  );
}
