'use client';

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import {
  RefreshCw, Brain, Cpu, FileText, CheckCircle2, AlertCircle,
  User, MessageSquare, Database, GitBranch, ChevronDown, ChevronRight,
  Clock, BarChart2, Filter,
} from 'lucide-react';
import { AuditLogEntry } from '@/types/stream';
import TraceDetailModal from './trace-detail-modal';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ActivitySource = 'sse' | 'cw' | 'langfuse';

export interface ActivityEvent {
  id: string;
  timestamp: string;
  source: ActivitySource;
  type: string;
  agent: string;
  label: string;
  detail?: string;
  tokens?: { in: number; out: number };
  duration_ms?: number;
  children?: ActivityEvent[];
  raw?: unknown;
}

interface CloudWatchLogEntry {
  timestamp: string;
  level: string;
  logger: string;
  msg: string;
  event_type?: string;
  tool_name?: string;
  tool_input?: string;
  result_preview?: string;
  duration_ms?: number;
  input_tokens?: number;
  output_tokens?: number;
  total_input_tokens?: number;
  total_output_tokens?: number;
  tools_called?: string[];
  state_delta?: Record<string, { before: unknown; after: unknown }>;
  success?: boolean;
  response_preview?: string;
  prompt_preview?: string;
  [key: string]: unknown;
}

interface InternalTool {
  name: string;
  input: Record<string, unknown>;
  output_preview: string | Record<string, unknown>;
}

interface SubagentStory {
  name: string;
  input_query: string;
  input_tokens: number;
  output_tokens: number;
  response_preview: string;
  internal_tools: InternalTool[];
}

interface TurnStory {
  turn: number;
  input_tokens: number;
  output_tokens: number;
  tool_calls: string[];
  has_reasoning: boolean;
  response_preview: string;
  subagents: SubagentStory[];
}

interface TraceStory {
  trace_id: string;
  session_id: string;
  timestamp: string;
  story: TurnStory[];
  total_tokens?: {
    supervisor: { input: number; output: number };
    subagents: { input: number; output: number };
    combined: { input: number; output: number };
  };
}

// ---------------------------------------------------------------------------
// Normalizers
// ---------------------------------------------------------------------------

let _idSeq = 0;
function uid() { return `ae-${++_idSeq}`; }

function relativeTime(base: string, current: string): string {
  try {
    const diff = Math.round((new Date(current).getTime() - new Date(base).getTime()) / 1000);
    if (diff < 0) return '0:00';
    const m = Math.floor(diff / 60);
    const s = diff % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  } catch {
    return '';
  }
}

function normalizeSSE(logs: AuditLogEntry[]): ActivityEvent[] {
  const events: ActivityEvent[] = [];
  let textBuffer: AuditLogEntry[] = [];
  let textAgent = '';

  const flushText = () => {
    if (!textBuffer.length) return;
    const last = textBuffer[textBuffer.length - 1];
    const merged = textBuffer.map(l => l.content ?? '').join('');
    events.push({
      id: uid(),
      timestamp: last.timestamp,
      source: 'sse',
      type: 'response',
      agent: last.agent_id ?? 'supervisor',
      label: 'response',
      detail: merged.slice(0, 200) + (merged.length > 200 ? '...' : ''),
      raw: textBuffer,
    });
    textBuffer = [];
    textAgent = '';
  };

  for (const log of logs) {
    if (log.type === 'text') {
      if (textAgent && textAgent !== (log.agent_id ?? '')) flushText();
      textAgent = log.agent_id ?? '';
      textBuffer.push(log);
      continue;
    }
    flushText();

    if (log.type === 'tool_use' && log.tool_use) {
      const name = log.tool_use.name;
      const isDoc = name === 'create_document' || name === 'generate_document';
      events.push({
        id: uid(),
        timestamp: log.timestamp,
        source: 'sse',
        type: 'tool_use',
        agent: log.agent_id ?? 'supervisor',
        label: `→ ${name}`,
        detail: JSON.stringify(log.tool_use.input).slice(0, 120),
        raw: log,
      });
      if (isDoc) {
        // Will be enriched when tool_result arrives
      }
    } else if (log.type === 'tool_result' && log.tool_result) {
      const name = log.tool_result.name;
      const result = log.tool_result.result;
      const isDoc = name === 'create_document' || name === 'generate_document';
      let detail = '';
      if (isDoc && typeof result === 'object' && result !== null) {
        const r = result as Record<string, unknown>;
        detail = [
          r.document_type && `Type: ${r.document_type}`,
          r.word_count && `${r.word_count} words`,
          r.version && `v${r.version}`,
          r.status && `[${r.status}]`,
        ].filter(Boolean).join(' · ');
      } else {
        const raw = typeof result === 'string' ? result : JSON.stringify(result);
        detail = raw.slice(0, 150);
      }
      events.push({
        id: uid(),
        timestamp: log.timestamp,
        source: 'sse',
        type: isDoc ? 'document' : 'tool_result',
        agent: log.agent_id ?? 'supervisor',
        label: `✓ ${name}`,
        detail,
        raw: log,
      });
    } else if (log.type === 'reasoning') {
      events.push({
        id: uid(),
        timestamp: log.timestamp,
        source: 'sse',
        type: 'reasoning',
        agent: log.agent_id ?? 'supervisor',
        label: '💭 reasoning',
        detail: (log.content ?? '').slice(0, 100),
        raw: log,
      });
    } else if (log.type === 'metadata' && log.metadata) {
      const meta = log.metadata as Record<string, unknown>;
      if (meta.persistence) {
        events.push({
          id: uid(),
          timestamp: log.timestamp,
          source: 'sse',
          type: 'persistence',
          agent: 'system',
          label: `💾 ${meta.persistence}`,
          raw: log,
        });
      } else {
        const phase = meta.phase ?? meta.state_type;
        events.push({
          id: uid(),
          timestamp: log.timestamp,
          source: 'sse',
          type: 'state_update',
          agent: 'system',
          label: phase ? `state: ${phase}` : 'state update',
          detail: meta.package_id ? `pkg: ${meta.package_id}` : undefined,
          raw: log,
        });
      }
    } else if (log.type === 'complete') {
      const usage = log.metadata?.usage as Record<string, number> | undefined;
      events.push({
        id: uid(),
        timestamp: log.timestamp,
        source: 'sse',
        type: 'turn_complete',
        agent: 'system',
        label: 'turn complete',
        tokens: usage ? { in: usage.inputTokens ?? 0, out: usage.outputTokens ?? 0 } : undefined,
        raw: log,
      });
    } else if (log.type === 'error') {
      events.push({
        id: uid(),
        timestamp: log.timestamp,
        source: 'sse',
        type: 'error',
        agent: 'system',
        label: 'error',
        detail: log.content ?? 'Unknown error',
        raw: log,
      });
    } else if (log.type === 'user_input') {
      events.push({
        id: uid(),
        timestamp: log.timestamp,
        source: 'sse',
        type: 'user_message',
        agent: 'user',
        label: 'user message',
        detail: (log.content ?? '').slice(0, 120),
        raw: log,
      });
    }
  }
  flushText();
  return events;
}

function normalizeCW(entries: CloudWatchLogEntry[]): ActivityEvent[] {
  return entries
    .filter(e => !!e.event_type)
    .map(e => {
      const et = e.event_type!;
      if (et === 'trace.completed') {
        return {
          id: uid(),
          timestamp: e.timestamp,
          source: 'cw' as ActivitySource,
          type: 'trace_complete',
          agent: 'system',
          label: `trace done  ${e.duration_ms ? `${(e.duration_ms / 1000).toFixed(1)}s` : ''}`,
          tokens: (e.total_input_tokens || e.total_output_tokens) ? {
            in: e.total_input_tokens ?? 0,
            out: e.total_output_tokens ?? 0,
          } : undefined,
          duration_ms: e.duration_ms,
          detail: e.tools_called?.join(', '),
          raw: e,
        };
      }
      if (et === 'tool.completed') {
        const delta = e.state_delta;
        const deltaDesc = delta && Object.keys(delta).length > 0
          ? 'state: ' + Object.keys(delta).join(', ')
          : undefined;
        return {
          id: uid(),
          timestamp: e.timestamp,
          source: 'cw' as ActivitySource,
          type: 'tool_timing',
          agent: 'system',
          label: `⏱ ${e.tool_name ?? 'tool'} ${e.duration_ms ? `+${e.duration_ms}ms` : ''}`,
          duration_ms: e.duration_ms,
          detail: deltaDesc,
          raw: e,
        };
      }
      if (et === 'tool.result') {
        return {
          id: uid(),
          timestamp: e.timestamp,
          source: 'cw' as ActivitySource,
          type: 'tool_timing',
          agent: 'system',
          label: `⏱ ${e.tool_name ?? 'tool'} ${e.duration_ms ? `+${e.duration_ms}ms` : ''}`,
          duration_ms: e.duration_ms,
          tokens: (e.input_tokens || e.output_tokens) ? {
            in: e.input_tokens ?? 0,
            out: e.output_tokens ?? 0,
          } : undefined,
          raw: e,
        };
      }
      // trace.started, agent.state_flush, etc.
      return {
        id: uid(),
        timestamp: e.timestamp,
        source: 'cw' as ActivitySource,
        type: et.replace('.', '_'),
        agent: 'system',
        label: et,
        detail: e.prompt_preview?.slice(0, 80) ?? e.response_preview?.slice(0, 80),
        raw: e,
      };
    });
}

function normalizeLangfuse(stories: TraceStory[]): ActivityEvent[] {
  const events: ActivityEvent[] = [];
  for (const trace of stories) {
    for (const turn of trace.story) {
      for (const sub of turn.subagents) {
        const children: ActivityEvent[] = sub.internal_tools.map(tool => ({
          id: uid(),
          timestamp: trace.timestamp,
          source: 'langfuse' as ActivitySource,
          type: 'subagent_tool',
          agent: sub.name,
          label: `  → ${tool.name}`,
          detail: JSON.stringify(tool.input).slice(0, 80),
          raw: tool,
        }));
        events.push({
          id: uid(),
          timestamp: trace.timestamp,
          source: 'langfuse',
          type: 'subagent',
          agent: sub.name,
          label: `◈ ${sub.name}`,
          tokens: { in: sub.input_tokens, out: sub.output_tokens },
          detail: sub.response_preview?.slice(0, 100),
          children,
          raw: sub,
        });
      }
    }
  }
  return events;
}

function mergeEvents(sse: ActivityEvent[], cw: ActivityEvent[], lf: ActivityEvent[]): ActivityEvent[] {
  const all = [...sse, ...cw, ...lf];
  all.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());

  // Deduplicate: CW tool_timing within 5s of SSE tool_use for same tool (by label match)
  const deduped: ActivityEvent[] = [];
  const sseLabelTimes = new Map<string, number>();
  for (const e of sse) {
    if (e.type === 'tool_use' || e.type === 'tool_result') {
      const toolName = e.label.replace(/^[→✓] /, '');
      sseLabelTimes.set(toolName, new Date(e.timestamp).getTime());
    }
  }

  for (const e of all) {
    if (e.source === 'cw' && e.type === 'tool_timing') {
      const toolName = (e.raw as CloudWatchLogEntry)?.tool_name ?? '';
      const sseTime = sseLabelTimes.get(toolName);
      if (sseTime !== undefined) {
        const cwTime = new Date(e.timestamp).getTime();
        if (Math.abs(cwTime - sseTime) < 5000) {
          // Merge duration/tokens into existing SSE event instead of showing twice
          const sseEvent = deduped.find(d =>
            d.source === 'sse' &&
            (d.type === 'tool_use' || d.type === 'tool_result') &&
            d.label.includes(toolName)
          );
          if (sseEvent) {
            sseEvent.duration_ms = e.duration_ms;
            if (e.tokens) sseEvent.tokens = e.tokens;
            continue; // skip adding the CW event separately
          }
        }
      }
    }
    deduped.push(e);
  }

  return deduped;
}

// ---------------------------------------------------------------------------
// Source badge colors
// ---------------------------------------------------------------------------

const SOURCE_STYLES: Record<ActivitySource, { dot: string; badge: string }> = {
  sse:      { dot: 'bg-green-400',  badge: 'text-green-700 bg-green-50' },
  cw:       { dot: 'bg-sky-400',    badge: 'text-sky-700 bg-sky-50' },
  langfuse: { dot: 'bg-violet-400', badge: 'text-violet-700 bg-violet-50' },
};

const TYPE_COLORS: Record<string, string> = {
  tool_use:       'text-yellow-700',
  tool_result:    'text-orange-700',
  document:       'text-blue-700',
  reasoning:      'text-purple-600',
  response:       'text-gray-700',
  state_update:   'text-indigo-600',
  persistence:    'text-teal-600',
  turn_complete:  'text-gray-500',
  error:          'text-red-600',
  user_message:   'text-cyan-700',
  subagent:       'text-violet-700',
  subagent_tool:  'text-violet-500',
  trace_complete: 'text-indigo-500',
  tool_timing:    'text-gray-400',
};

function getTypeColor(type: string): string {
  return TYPE_COLORS[type] ?? 'text-gray-600';
}

function getTypeIcon(type: string) {
  switch (type) {
    case 'tool_use':      return <Cpu className="w-3 h-3" />;
    case 'tool_result':   return <FileText className="w-3 h-3" />;
    case 'document':      return <FileText className="w-3 h-3 text-blue-600" />;
    case 'reasoning':     return <Brain className="w-3 h-3" />;
    case 'response':      return <MessageSquare className="w-3 h-3" />;
    case 'state_update':  return <Database className="w-3 h-3" />;
    case 'persistence':   return <Database className="w-3 h-3" />;
    case 'turn_complete': return <CheckCircle2 className="w-3 h-3" />;
    case 'error':         return <AlertCircle className="w-3 h-3" />;
    case 'user_message':  return <User className="w-3 h-3" />;
    case 'subagent':      return <GitBranch className="w-3 h-3" />;
    case 'trace_complete':return <CheckCircle2 className="w-3 h-3" />;
    case 'tool_timing':   return <Clock className="w-3 h-3" />;
    default:              return <Cpu className="w-3 h-3" />;
  }
}

// ---------------------------------------------------------------------------
// ActivityRow
// ---------------------------------------------------------------------------

function ActivityRow({
  event,
  baseTime,
  depth = 0,
  onOpenDetail,
}: {
  event: ActivityEvent;
  baseTime: string;
  depth?: number;
  onOpenDetail: (e: ActivityEvent) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const hasChildren = (event.children?.length ?? 0) > 0;
  const srcStyle = SOURCE_STYLES[event.source];
  const typeColor = getTypeColor(event.type);

  return (
    <div className={depth > 0 ? 'ml-4 border-l border-gray-100 pl-2' : ''}>
      <div
        className={`flex items-start gap-1.5 py-1 px-2 rounded-lg hover:bg-gray-50 cursor-pointer group transition ${depth > 0 ? 'text-[9px]' : 'text-[10px]'}`}
        onClick={() => onOpenDetail(event)}
      >
        {/* Source dot */}
        <span className={`w-1.5 h-1.5 rounded-full shrink-0 mt-1.5 ${srcStyle.dot}`} title={event.source} />

        {/* Time */}
        <span className="text-[9px] text-gray-400 font-mono shrink-0 mt-0.5 w-8">
          {relativeTime(baseTime, event.timestamp)}
        </span>

        {/* Agent badge */}
        <span className="text-[8px] font-bold uppercase text-gray-400 shrink-0 mt-0.5 w-20 truncate">
          {event.agent}
        </span>

        {/* Type icon */}
        <span className={`shrink-0 mt-0.5 ${typeColor}`}>
          {getTypeIcon(event.type)}
        </span>

        {/* Label */}
        <span className={`font-mono font-medium shrink-0 ${typeColor}`}>
          {event.label}
        </span>

        {/* Detail */}
        {event.detail && (
          <span className="text-gray-500 truncate flex-1 min-w-0">
            {event.detail}
          </span>
        )}

        {/* Tokens */}
        {event.tokens && (
          <span className="text-[8px] text-emerald-600 bg-emerald-50 px-1 rounded shrink-0 flex items-center gap-0.5">
            <BarChart2 className="w-2 h-2" />
            {event.tokens.in.toLocaleString()}↑ {event.tokens.out.toLocaleString()}↓
          </span>
        )}

        {/* Duration */}
        {event.duration_ms != null && (
          <span className="text-[8px] text-gray-400 bg-gray-100 px-1 rounded shrink-0">
            {event.duration_ms < 1000 ? `${event.duration_ms}ms` : `${(event.duration_ms / 1000).toFixed(1)}s`}
          </span>
        )}

        {/* Children toggle */}
        {hasChildren && (
          <span
            className="shrink-0 text-gray-400"
            onClick={(e) => { e.stopPropagation(); setExpanded(!expanded); }}
          >
            {expanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
          </span>
        )}
      </div>

      {/* Children */}
      {expanded && event.children?.map(child => (
        <ActivityRow key={child.id} event={child} baseTime={baseTime} depth={depth + 1} onOpenDetail={onOpenDetail} />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ActivityFeed — Main Export
// ---------------------------------------------------------------------------

interface ActivityFeedProps {
  sessionId?: string;
  logs: AuditLogEntry[];
  isStreaming: boolean;
}

export default function ActivityFeed({ sessionId, logs, isStreaming }: ActivityFeedProps) {
  const [cwLogs, setCwLogs] = useState<CloudWatchLogEntry[]>([]);
  const [lfStories, setLfStories] = useState<TraceStory[]>([]);
  const [historicalLogs, setHistoricalLogs] = useState<AuditLogEntry[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<ActivityEvent | null>(null);
  const [loading, setLoading] = useState(false);
  const [lastFetched, setLastFetched] = useState<Date | null>(null);
  const [filter, setFilter] = useState<ActivitySource | 'all'>('all');
  const scrollRef = useRef<HTMLDivElement>(null);
  const historicalFetchedRef = useRef(false);

  const fetchEnrichment = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    try {
      const [cwRes, lfRes] = await Promise.allSettled([
        fetch(`/api/logs/cloudwatch?session_id=${encodeURIComponent(sessionId)}&limit=100`),
        fetch(`/api/traces/story?session_id=${encodeURIComponent(sessionId)}`),
      ]);
      if (cwRes.status === 'fulfilled' && cwRes.value.ok) {
        const data = await cwRes.value.json();
        setCwLogs(data.logs ?? []);
      }
      if (lfRes.status === 'fulfilled' && lfRes.value.ok) {
        const data = await lfRes.value.json();
        // API may return a single story or array
        setLfStories(Array.isArray(data) ? data : data.story ? [data] : []);
      }
      setLastFetched(new Date());
    } catch {
      // non-fatal
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  // Hydrate historical audit logs from backend on mount (once per session)
  useEffect(() => {
    if (!sessionId || historicalFetchedRef.current) return;
    historicalFetchedRef.current = true;
    fetch(`/api/sessions/${encodeURIComponent(sessionId)}/audit-logs`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!data?.events?.length) return;
        const entries: AuditLogEntry[] = (data.events as Record<string, unknown>[]).map((e, i) => ({
          ...e,
          id: `hist-${i}`,
        } as AuditLogEntry));
        setHistoricalLogs(entries);
      })
      .catch(() => { /* non-fatal */ });
  }, [sessionId]);

  // Auto-fetch enrichment 35s after streaming ends
  useEffect(() => {
    if (!isStreaming && sessionId && logs.length > 0) {
      const timer = setTimeout(fetchEnrichment, 35_000);
      return () => clearTimeout(timer);
    }
  }, [isStreaming, sessionId, logs.length, fetchEnrichment]);

  // Auto-scroll to bottom during streaming
  useEffect(() => {
    if (isStreaming && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs.length, isStreaming]);

  const allEvents = useMemo(() => {
    const sse = normalizeSSE([...historicalLogs, ...logs]);
    const cw = normalizeCW(cwLogs);
    const lf = normalizeLangfuse(lfStories);
    return mergeEvents(sse, cw, lf);
  }, [historicalLogs, logs, cwLogs, lfStories]);

  const filteredEvents = useMemo(() =>
    filter === 'all' ? allEvents : allEvents.filter(e => e.source === filter),
    [allEvents, filter]
  );

  const baseTime = filteredEvents[0]?.timestamp ?? new Date().toISOString();

  const sseCnt = allEvents.filter(e => e.source === 'sse').length;
  const cwCnt  = allEvents.filter(e => e.source === 'cw').length;
  const lfCnt  = allEvents.filter(e => e.source === 'langfuse').length;

  if (logs.length === 0 && historicalLogs.length === 0 && cwLogs.length === 0 && lfStories.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-48 text-center px-4">
        <div className="w-10 h-10 rounded-full bg-gray-100 flex items-center justify-center mb-3">
          <GitBranch className="w-5 h-5 text-gray-400" />
        </div>
        <p className="text-sm text-gray-500">No activity yet.</p>
        <p className="text-xs text-gray-400 mt-1">Events will appear here as the agent processes your request.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center gap-1.5 mb-2 flex-wrap">
        {/* Filter pills */}
        <div className="flex items-center gap-1">
          <Filter className="w-3 h-3 text-gray-400" />
          {(['all', 'sse', 'cw', 'langfuse'] as const).map(src => (
            <button
              key={src}
              onClick={() => setFilter(src)}
              className={`px-2 py-0.5 rounded-full text-[9px] font-bold uppercase transition ${
                filter === src
                  ? 'bg-[#003366] text-white'
                  : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
              }`}
            >
              {src === 'all' ? `All ${allEvents.length}` :
               src === 'sse' ? `● SSE ${sseCnt}` :
               src === 'cw'  ? `◎ CW ${cwCnt}` :
               `◈ Traces ${lfCnt}`}
            </button>
          ))}
        </div>

        {/* Refresh + status */}
        <div className="ml-auto flex items-center gap-1.5">
          {isStreaming && (
            <span className="inline-flex items-center gap-1 text-[9px] text-green-600">
              <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
              live
            </span>
          )}
          {lastFetched && (
            <span className="text-[9px] text-gray-400">
              +CW {lastFetched.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
          )}
          <button
            onClick={fetchEnrichment}
            disabled={loading}
            className="flex items-center gap-0.5 px-1.5 py-0.5 text-[9px] text-gray-500 hover:text-gray-700 bg-gray-100 hover:bg-gray-200 rounded transition disabled:opacity-50"
          >
            <RefreshCw className={`w-2.5 h-2.5 ${loading ? 'animate-spin' : ''}`} />
            {loading ? '...' : 'Refresh'}
          </button>
        </div>
      </div>

      {/* Event list */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto space-y-0.5 min-h-0">
        {filteredEvents.map(event => (
          <ActivityRow key={event.id} event={event} baseTime={baseTime} onOpenDetail={setSelectedEvent} />
        ))}
      </div>

      {/* Detail modal */}
      {selectedEvent && (
        <TraceDetailModal
          isOpen={true}
          onClose={() => setSelectedEvent(null)}
          data={selectedEvent.raw ?? selectedEvent}
          header={
            <div className="flex items-center gap-2 text-sm">
              <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${SOURCE_STYLES[selectedEvent.source].badge}`}>
                {selectedEvent.source === 'sse' ? '● SSE' : selectedEvent.source === 'cw' ? '◎ CW' : '◈ Traces'}
              </span>
              <span className="text-gray-500 font-mono">{selectedEvent.type}</span>
              <span className="text-gray-700 font-medium">{selectedEvent.agent}</span>
              <span className="text-gray-400 ml-auto text-xs">{new Date(selectedEvent.timestamp).toLocaleTimeString()}</span>
            </div>
          }
          downloadFilename={`activity-${selectedEvent.id}.json`}
        />
      )}
    </div>
  );
}
