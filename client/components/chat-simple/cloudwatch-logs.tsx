'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Cloud, RefreshCw, AlertCircle, Info, AlertTriangle, Bug,
  Zap, Play, Square, BarChart2, MessageSquare, Cpu, ChevronDown, ChevronRight,
} from 'lucide-react';
import TraceDetailModal from './trace-detail-modal';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface CloudWatchLogEntry {
  timestamp: string;
  level: string;
  logger: string;
  msg: string;
  event_type?: string;
  tenant_id?: string;
  user_id?: string;
  session_id?: string;
  exc?: string;
  // Telemetry fields
  prompt_preview?: string;
  response_preview?: string;
  tool_name?: string;
  tool_input?: string;
  tool_use_id?: string;
  result_preview?: string;
  duration_ms?: number;
  input_tokens?: number;
  output_tokens?: number;
  total_input_tokens?: number;
  total_output_tokens?: number;
  has_reasoning?: boolean;
  success?: boolean;
  tools_called?: string[];
  tool_metrics?: Record<string, Record<string, unknown>>;
  cycle_count?: number;
  trace_id?: string;
  // API request fields
  method?: string;
  path?: string;
  status_code?: number;
  query_params?: Record<string, string>;
  [key: string]: unknown;
}

interface CloudWatchResponse {
  logs: CloudWatchLogEntry[];
  log_group: string;
  count: number;
  user_id: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatTime(ts: string): string {
  try {
    return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return ts;
  }
}

function formatDuration(ms?: number): string {
  if (!ms) return '';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function formatTokens(input?: number, output?: number): string {
  if (!input && !output) return '';
  return `${(input || 0).toLocaleString()} in / ${(output || 0).toLocaleString()} out`;
}

// Event type → style mapping for telemetry events
const EVENT_STYLES: Record<string, { badge: string; icon: React.ReactNode; label: string }> = {
  'trace.started':  { badge: 'bg-green-100 text-green-700', icon: <Play className="w-3 h-3" />, label: 'Trace Started' },
  'trace.completed': { badge: 'bg-indigo-100 text-indigo-700', icon: <Square className="w-3 h-3" />, label: 'Trace Completed' },
  'tool.started':   { badge: 'bg-violet-100 text-violet-700', icon: <Zap className="w-3 h-3" />, label: 'Tool Started' },
  'tool.result':    { badge: 'bg-orange-100 text-orange-700', icon: <Cpu className="w-3 h-3" />, label: 'Tool Result' },
  'tool.completed': { badge: 'bg-yellow-100 text-yellow-800', icon: <Cpu className="w-3 h-3" />, label: 'Tool Done' },
  'error.occurred': { badge: 'bg-red-100 text-red-700', icon: <AlertCircle className="w-3 h-3" />, label: 'Error' },
  'feedback.submitted': { badge: 'bg-sky-100 text-sky-700', icon: <MessageSquare className="w-3 h-3" />, label: 'Feedback' },
  'api.request':      { badge: 'bg-cyan-100 text-cyan-700', icon: <Zap className="w-3 h-3" />, label: 'API Request' },
};

const LEVEL_STYLES: Record<string, { badge: string; icon: React.ReactNode }> = {
  DEBUG:    { badge: 'bg-gray-100 text-gray-500', icon: <Bug className="w-3 h-3" /> },
  INFO:     { badge: 'bg-blue-100 text-blue-700', icon: <Info className="w-3 h-3" /> },
  WARNING:  { badge: 'bg-amber-100 text-amber-700', icon: <AlertTriangle className="w-3 h-3" /> },
  ERROR:    { badge: 'bg-red-100 text-red-700', icon: <AlertCircle className="w-3 h-3" /> },
};

// ---------------------------------------------------------------------------
// Collapsible Section
// ---------------------------------------------------------------------------

function Collapsible({ title, children, defaultOpen = false }: {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1 text-[10px] font-bold text-gray-500 uppercase hover:text-gray-700 transition"
      >
        {open ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        {title}
      </button>
      {open && <div className="mt-1.5">{children}</div>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Telemetry Event Card (rich rendering)
// ---------------------------------------------------------------------------

function TelemetryCard({ entry, onClick }: { entry: CloudWatchLogEntry; onClick: () => void }) {
  const eventType = entry.event_type || '';
  const style = EVENT_STYLES[eventType] || { badge: 'bg-gray-100 text-gray-600', icon: <Info className="w-3 h-3" />, label: eventType };

  return (
    <div
      className="rounded-lg border border-gray-200 bg-white hover:shadow-sm transition cursor-pointer group"
      onClick={onClick}
    >
      {/* Header row */}
      <div className="flex items-center gap-1.5 px-3 py-2">
        <span className={`px-1.5 py-0.5 rounded text-[8px] font-bold uppercase shrink-0 flex items-center gap-0.5 ${style.badge}`}>
          {style.icon}
          {style.label}
        </span>

        {/* Context label: API path, tool name, or prompt preview */}
        <span className="text-[10px] text-gray-700 font-mono truncate flex-1">
          {eventType === 'api.request'
            ? `${entry.method} ${entry.path}`
            : (entry.tool_name || entry.prompt_preview?.slice(0, 60) || entry.response_preview?.slice(0, 60) || '')}
        </span>

        {/* HTTP status badge for API requests */}
        {eventType === 'api.request' && entry.status_code && (
          <span className={`text-[9px] px-1 rounded shrink-0 font-mono ${
            entry.status_code < 400 ? 'text-green-700 bg-green-50' : 'text-red-700 bg-red-50'
          }`}>
            {entry.status_code}
          </span>
        )}

        {/* Duration badge */}
        {entry.duration_ms ? (
          <span className="text-[9px] text-gray-500 bg-gray-100 px-1 rounded shrink-0">
            {formatDuration(entry.duration_ms)}
          </span>
        ) : null}

        {/* Token badge */}
        {(entry.input_tokens || entry.output_tokens || entry.total_input_tokens || entry.total_output_tokens) ? (
          <span className="text-[9px] text-emerald-600 bg-emerald-50 px-1 rounded shrink-0 flex items-center gap-0.5">
            <BarChart2 className="w-2.5 h-2.5" />
            {formatTokens(
              entry.input_tokens || entry.total_input_tokens,
              entry.output_tokens || entry.total_output_tokens,
            )}
          </span>
        ) : null}

        <span className="text-[9px] text-gray-400 shrink-0">{formatTime(entry.timestamp)}</span>
      </div>

      {/* Prompt preview for trace.started */}
      {eventType === 'trace.started' && entry.prompt_preview && (
        <div className="px-3 pb-2">
          <p className="text-[10px] text-gray-500 bg-gray-50 rounded p-1.5 font-mono line-clamp-2">
            {entry.prompt_preview}
          </p>
        </div>
      )}

      {/* Tool input preview for tool.started */}
      {eventType === 'tool.started' && entry.tool_input && (
        <div className="px-3 pb-2">
          <p className="text-[10px] text-violet-600 bg-violet-50 rounded p-1.5 font-mono line-clamp-2">
            {typeof entry.tool_input === 'string' ? entry.tool_input.slice(0, 120) : JSON.stringify(entry.tool_input).slice(0, 120)}
          </p>
        </div>
      )}

      {/* Result preview for tool.result */}
      {eventType === 'tool.result' && entry.result_preview && (
        <div className="px-3 pb-2">
          <div className="flex items-center gap-1.5 mb-1">
            {entry.has_reasoning && (
              <span className="text-[8px] text-amber-600 bg-amber-50 px-1 rounded">reasoning</span>
            )}
            {entry.success === false && (
              <span className="text-[8px] text-red-600 bg-red-50 px-1 rounded">failed</span>
            )}
          </div>
          <p className="text-[10px] text-orange-600 bg-orange-50 rounded p-1.5 font-mono line-clamp-2">
            {entry.result_preview.slice(0, 120)}
          </p>
        </div>
      )}

      {/* Response preview + tools for trace.completed */}
      {eventType === 'trace.completed' && (
        <div className="px-3 pb-2 space-y-1">
          {entry.tools_called && entry.tools_called.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {entry.tools_called.map((t, i) => (
                <span key={i} className="text-[8px] text-violet-600 bg-violet-50 px-1.5 py-0.5 rounded font-mono">
                  {t}
                </span>
              ))}
            </div>
          )}
          {entry.response_preview && (
            <p className="text-[10px] text-gray-500 bg-gray-50 rounded p-1.5 font-mono line-clamp-2">
              {entry.response_preview.slice(0, 120)}
            </p>
          )}
          {/* Per-tool metrics */}
          {entry.tool_metrics && Object.keys(entry.tool_metrics).length > 0 && (
            <div className="flex flex-wrap gap-1">
              {Object.entries(entry.tool_metrics).map(([name, m]) => (
                <span key={name} className="text-[8px] text-emerald-600 bg-emerald-50 px-1.5 py-0.5 rounded font-mono">
                  {name}: {formatTokens(m?.input_tokens as number, m?.output_tokens as number)}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="px-3 pb-1 text-right">
        <span className="text-[8px] text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity">
          Click to expand
        </span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Legacy Log Card (non-telemetry app logs)
// ---------------------------------------------------------------------------

function LogCard({ entry, onClick }: { entry: CloudWatchLogEntry; onClick: () => void }) {
  const style = LEVEL_STYLES[entry.level.toUpperCase()] || LEVEL_STYLES.INFO;

  return (
    <div
      className="rounded-lg border border-gray-200 bg-white hover:shadow-sm transition cursor-pointer group"
      onClick={onClick}
    >
      <div className="flex items-center gap-1.5 px-3 py-2">
        <span className={`px-1.5 py-0.5 rounded text-[8px] font-bold uppercase shrink-0 flex items-center gap-0.5 ${style.badge}`}>
          {style.icon}
          {entry.level}
        </span>
        <span className="text-[9px] text-gray-400 font-mono shrink-0">{entry.logger}</span>
        <span className="text-[10px] text-gray-700 truncate flex-1">{entry.msg}</span>
        <span className="text-[9px] text-gray-400 shrink-0">{formatTime(entry.timestamp)}</span>
      </div>
      {entry.exc && (
        <div className="px-3 pb-1.5">
          <p className="text-[9px] text-red-500 font-mono truncate">{entry.exc.split('\n')[0]}</p>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Formatted Detail View (for modal)
// ---------------------------------------------------------------------------

function TelemetryDetailView({ entry }: { entry: CloudWatchLogEntry }) {
  const eventType = entry.event_type || '';
  const style = EVENT_STYLES[eventType] || EVENT_STYLES['trace.started'];

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="bg-gray-50 border border-gray-200 rounded-xl p-4">
        <div className="flex items-center gap-2 mb-2">
          <span className={`px-2 py-1 rounded text-xs font-bold uppercase flex items-center gap-1 ${style.badge}`}>
            {style.icon}
            {style.label}
          </span>
          {entry.tool_name && (
            <span className="text-xs font-mono text-violet-600">{entry.tool_name}</span>
          )}
          <span className="text-xs text-gray-400 ml-auto">{formatTime(entry.timestamp)}</span>
        </div>
        <div className="flex items-center gap-4 text-xs text-gray-500">
          {entry.duration_ms ? <span>{formatDuration(entry.duration_ms)}</span> : null}
          {(entry.input_tokens || entry.output_tokens || entry.total_input_tokens || entry.total_output_tokens) ? (
            <span className="font-mono">
              {formatTokens(
                entry.input_tokens || entry.total_input_tokens,
                entry.output_tokens || entry.total_output_tokens,
              )}
            </span>
          ) : null}
          {entry.cycle_count ? <span>{entry.cycle_count} cycles</span> : null}
          {entry.trace_id && <span className="font-mono text-gray-400">{entry.trace_id}</span>}
        </div>
      </div>

      {/* Prompt preview */}
      {entry.prompt_preview && (
        <Collapsible title="Prompt" defaultOpen>
          <div className="bg-green-50 border border-green-200 p-4 rounded-xl text-sm font-mono whitespace-pre-wrap break-all">
            {entry.prompt_preview}
          </div>
        </Collapsible>
      )}

      {/* Response preview */}
      {entry.response_preview && (
        <Collapsible title="Response" defaultOpen>
          <div className="bg-indigo-50 border border-indigo-200 p-4 rounded-xl text-sm whitespace-pre-wrap break-all">
            {entry.response_preview}
          </div>
        </Collapsible>
      )}

      {/* Tool input */}
      {entry.tool_input && (
        <Collapsible title="Tool Input" defaultOpen>
          <pre className="bg-violet-50 border border-violet-200 p-4 rounded-xl text-xs font-mono whitespace-pre-wrap break-all">
            {typeof entry.tool_input === 'string'
              ? (() => { try { return JSON.stringify(JSON.parse(entry.tool_input), null, 2); } catch { return entry.tool_input; } })()
              : JSON.stringify(entry.tool_input, null, 2)}
          </pre>
        </Collapsible>
      )}

      {/* Tool result */}
      {entry.result_preview && (
        <Collapsible title="Tool Result" defaultOpen>
          <div className="flex items-center gap-2 mb-2">
            {entry.has_reasoning && (
              <span className="text-[10px] text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded">has reasoning</span>
            )}
            {entry.success === false && (
              <span className="text-[10px] text-red-600 bg-red-50 px-1.5 py-0.5 rounded">failed</span>
            )}
          </div>
          <pre className="bg-orange-50 border border-orange-200 p-4 rounded-xl text-xs font-mono whitespace-pre-wrap break-all">
            {(() => { try { return JSON.stringify(JSON.parse(entry.result_preview), null, 2); } catch { return entry.result_preview; } })()}
          </pre>
        </Collapsible>
      )}

      {/* Tools called */}
      {entry.tools_called && entry.tools_called.length > 0 && (
        <div>
          <h4 className="text-xs font-bold text-gray-500 uppercase mb-2">Tools Called</h4>
          <div className="flex flex-wrap gap-1.5">
            {entry.tools_called.map((t, i) => (
              <span key={i} className="text-xs text-violet-600 bg-violet-50 px-2 py-1 rounded font-mono">
                {t}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Per-tool metrics */}
      {entry.tool_metrics && Object.keys(entry.tool_metrics).length > 0 && (
        <div>
          <h4 className="text-xs font-bold text-gray-500 uppercase mb-2">Per-Tool Token Breakdown</h4>
          <div className="bg-emerald-50 border border-emerald-200 rounded-xl overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-emerald-200 text-left">
                  <th className="px-3 py-2 font-bold text-emerald-700">Tool</th>
                  <th className="px-3 py-2 font-bold text-emerald-700">Input Tokens</th>
                  <th className="px-3 py-2 font-bold text-emerald-700">Output Tokens</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(entry.tool_metrics).map(([name, m]) => (
                  <tr key={name} className="border-b border-emerald-100 last:border-0">
                    <td className="px-3 py-1.5 font-mono">{name}</td>
                    <td className="px-3 py-1.5 font-mono">{((m?.input_tokens as number) || 0).toLocaleString()}</td>
                    <td className="px-3 py-1.5 font-mono">{((m?.output_tokens as number) || 0).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Raw payload */}
      <Collapsible title="Raw JSON">
        <pre className="bg-gray-50 border border-gray-200 p-4 rounded-xl text-xs font-mono whitespace-pre-wrap break-all">
          {JSON.stringify(entry, null, 2)}
        </pre>
      </Collapsible>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Turn Summary
// ---------------------------------------------------------------------------

function TurnSummary({ logs }: { logs: CloudWatchLogEntry[] }) {
  const traceCompleted = logs.filter(l => l.event_type === 'trace.completed');
  const toolResults = logs.filter(l => l.event_type === 'tool.result');
  const toolStarted = logs.filter(l => l.event_type === 'tool.started');

  if (traceCompleted.length === 0 && toolResults.length === 0) return null;

  const totalIn = traceCompleted.reduce((s, t) => s + (t.total_input_tokens || 0), 0);
  const totalOut = traceCompleted.reduce((s, t) => s + (t.total_output_tokens || 0), 0);
  const totalDuration = traceCompleted.reduce((s, t) => s + (t.duration_ms || 0), 0);
  const turns = traceCompleted.length;

  return (
    <div className="bg-gray-50 border border-gray-200 rounded-lg p-3 mb-3">
      <h4 className="text-[10px] font-bold text-gray-500 uppercase mb-2">Session Summary</h4>
      <div className="grid grid-cols-2 gap-2 text-[10px]">
        <div>
          <span className="text-gray-400">Turns:</span>{' '}
          <span className="font-mono text-gray-700">{turns}</span>
        </div>
        <div>
          <span className="text-gray-400">Total Duration:</span>{' '}
          <span className="font-mono text-gray-700">{formatDuration(totalDuration)}</span>
        </div>
        <div>
          <span className="text-gray-400">Input Tokens:</span>{' '}
          <span className="font-mono text-emerald-700">{totalIn.toLocaleString()}</span>
        </div>
        <div>
          <span className="text-gray-400">Output Tokens:</span>{' '}
          <span className="font-mono text-emerald-700">{totalOut.toLocaleString()}</span>
        </div>
        <div>
          <span className="text-gray-400">Tool Calls:</span>{' '}
          <span className="font-mono text-violet-700">{toolStarted.length} started, {toolResults.length} completed</span>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

interface CloudWatchLogsProps {
  sessionId?: string;
}

export default function CloudWatchLogs({ sessionId }: CloudWatchLogsProps) {
  const [logs, setLogs] = useState<CloudWatchLogEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedEntry, setSelectedEntry] = useState<CloudWatchLogEntry | null>(null);
  const [lastFetched, setLastFetched] = useState<Date | null>(null);

  const fetchLogs = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ session_id: sessionId, limit: '100' });
      const res = await fetch(`/api/logs/cloudwatch?${params.toString()}`);
      if (!res.ok) {
        const errText = await res.text();
        throw new Error(`${res.status}: ${errText}`);
      }
      const data: CloudWatchResponse = await res.json();
      setLogs(data.logs || []);
      setLastFetched(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch logs');
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  // Separate telemetry events from app logs
  const { telemetryLogs, appLogs } = useMemo(() => {
    const telem: CloudWatchLogEntry[] = [];
    const app: CloudWatchLogEntry[] = [];
    for (const log of logs) {
      if (log.event_type) {
        telem.push(log);
      } else {
        app.push(log);
      }
    }
    return { telemetryLogs: telem, appLogs: app };
  }, [logs]);

  if (!sessionId) {
    return (
      <div className="flex flex-col items-center justify-center h-48 text-center px-4">
        <div className="w-10 h-10 rounded-full bg-gray-100 flex items-center justify-center mb-3">
          <Cloud className="w-5 h-5 text-gray-400" />
        </div>
        <p className="text-sm text-gray-500">No session selected.</p>
        <p className="text-xs text-gray-400 mt-1">Start a conversation to see CloudWatch logs.</p>
      </div>
    );
  }

  return (
    <>
      {/* Toolbar */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2 text-[10px] text-gray-500">
          <span>{logs.length} event{logs.length !== 1 ? 's' : ''}</span>
          {telemetryLogs.length > 0 && <span>({telemetryLogs.length} telemetry)</span>}
          {lastFetched && (
            <span>updated {lastFetched.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
          )}
        </div>
        <button
          onClick={fetchLogs}
          disabled={loading}
          className="flex items-center gap-1 px-2 py-1 text-[10px] text-gray-500 hover:text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg transition disabled:opacity-50"
        >
          <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
          {loading ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-start gap-2 p-3 mb-3 rounded-lg bg-red-50 border border-red-200 text-xs text-red-700">
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          <div>
            <p className="font-medium">Failed to load CloudWatch logs</p>
            <p className="text-red-500 mt-0.5">{error}</p>
          </div>
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && logs.length === 0 && (
        <div className="flex flex-col items-center justify-center h-48 text-center px-4">
          <div className="w-10 h-10 rounded-full bg-gray-100 flex items-center justify-center mb-3">
            <Cloud className="w-5 h-5 text-gray-400" />
          </div>
          <p className="text-sm text-gray-500">No CloudWatch logs found.</p>
          <p className="text-xs text-gray-400 mt-1">Logs may take 30-60s to appear after a request.</p>
        </div>
      )}

      {/* Turn summary */}
      {telemetryLogs.length > 0 && <TurnSummary logs={telemetryLogs} />}

      {/* Telemetry events */}
      {telemetryLogs.length > 0 && (
        <div className="space-y-1.5 mb-4">
          {telemetryLogs.map((entry, i) => (
            <TelemetryCard
              key={`tel-${i}-${entry.timestamp}`}
              entry={entry}
              onClick={() => setSelectedEntry(entry)}
            />
          ))}
        </div>
      )}

      {/* App logs (non-telemetry) */}
      {appLogs.length > 0 && (
        <>
          {telemetryLogs.length > 0 && (
            <div className="text-[10px] font-bold text-gray-400 uppercase mb-2 mt-4">Application Logs</div>
          )}
          <div className="space-y-1.5">
            {appLogs.map((entry, i) => (
              <LogCard
                key={`app-${i}-${entry.timestamp}`}
                entry={entry}
                onClick={() => setSelectedEntry(entry)}
              />
            ))}
          </div>
        </>
      )}

      {/* Detail modal */}
      {selectedEntry && (
        <TraceDetailModal
          isOpen={true}
          onClose={() => setSelectedEntry(null)}
          data={selectedEntry}
          downloadFilename={`cloudwatch-${selectedEntry.event_type || 'log'}-${selectedEntry.timestamp}.json`}
          header={
            <>
              <Cloud className="w-4 h-4 text-sky-600 shrink-0" />
              <span className="text-sm font-bold text-gray-900">
                {selectedEntry.event_type ? 'Telemetry Event' : 'CloudWatch Log'}
              </span>
              {selectedEntry.event_type && (
                <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold uppercase ${
                  (EVENT_STYLES[selectedEntry.event_type] || EVENT_STYLES['trace.started']).badge
                }`}>
                  {selectedEntry.event_type}
                </span>
              )}
              {selectedEntry.tool_name && (
                <span className="text-xs font-mono text-violet-600">{selectedEntry.tool_name}</span>
              )}
              <span className="text-xs text-gray-400 ml-auto shrink-0">{formatTime(selectedEntry.timestamp)}</span>
            </>
          }
          formattedView={
            selectedEntry.event_type
              ? <TelemetryDetailView entry={selectedEntry} />
              : undefined
          }
        />
      )}
    </>
  );
}
