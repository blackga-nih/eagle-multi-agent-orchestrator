'use client';

import { useState, useEffect, useCallback } from 'react';
import { Cloud, RefreshCw, AlertCircle, Info, AlertTriangle, Bug } from 'lucide-react';
import TraceDetailModal from './trace-detail-modal';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface CloudWatchLogEntry {
  timestamp: string;
  level: string;
  logger: string;
  msg: string;
  tenant_id?: string;
  user_id?: string;
  session_id?: string;
  exc?: string;
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

const LEVEL_STYLES: Record<string, { badge: string; icon: React.ReactNode }> = {
  DEBUG:    { badge: 'bg-gray-100 text-gray-500', icon: <Bug className="w-3 h-3" /> },
  INFO:     { badge: 'bg-blue-100 text-blue-700', icon: <Info className="w-3 h-3" /> },
  WARNING:  { badge: 'bg-amber-100 text-amber-700', icon: <AlertTriangle className="w-3 h-3" /> },
  ERROR:    { badge: 'bg-red-100 text-red-700', icon: <AlertCircle className="w-3 h-3" /> },
  CRITICAL: { badge: 'bg-red-200 text-red-800', icon: <AlertCircle className="w-3 h-3" /> },
};

function getLevelStyle(level: string) {
  return LEVEL_STYLES[level.toUpperCase()] || LEVEL_STYLES.INFO;
}

// ---------------------------------------------------------------------------
// Log Card
// ---------------------------------------------------------------------------

function LogCard({ entry, onClick }: { entry: CloudWatchLogEntry; onClick: () => void }) {
  const style = getLevelStyle(entry.level);

  return (
    <div
      className="rounded-lg border border-gray-200 bg-white hover:shadow-sm transition cursor-pointer group"
      onClick={onClick}
    >
      <div className="flex items-center gap-1.5 px-3 py-2">
        {/* Level badge */}
        <span className={`px-1.5 py-0.5 rounded text-[8px] font-bold uppercase shrink-0 flex items-center gap-0.5 ${style.badge}`}>
          {style.icon}
          {entry.level}
        </span>

        {/* Logger name */}
        <span className="text-[9px] text-gray-400 font-mono shrink-0">{entry.logger}</span>

        {/* Message preview */}
        <span className="text-[10px] text-gray-700 truncate flex-1">{entry.msg}</span>

        {/* Timestamp */}
        <span className="text-[9px] text-gray-400 shrink-0">{formatTime(entry.timestamp)}</span>
      </div>

      {/* Exception preview */}
      {entry.exc && (
        <div className="px-3 pb-1.5">
          <p className="text-[9px] text-red-500 font-mono truncate">{entry.exc.split('\n')[0]}</p>
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
// Formatted Detail View
// ---------------------------------------------------------------------------

function LogFormattedView({ entry }: { entry: CloudWatchLogEntry }) {
  const style = getLevelStyle(entry.level);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="bg-gray-50 border border-gray-200 rounded-xl p-4">
        <div className="flex items-center gap-2 mb-2">
          <span className={`px-2 py-1 rounded text-xs font-bold uppercase flex items-center gap-1 ${style.badge}`}>
            {style.icon}
            {entry.level}
          </span>
          <span className="text-xs text-gray-500 font-mono">{entry.logger}</span>
          <span className="text-xs text-gray-400 ml-auto">{formatTime(entry.timestamp)}</span>
        </div>
        {entry.session_id && (
          <p className="text-[10px] text-gray-400 font-mono">session: {entry.session_id}</p>
        )}
      </div>

      {/* Message */}
      <div>
        <h4 className="text-xs font-bold text-gray-500 uppercase mb-2">Message</h4>
        <div className="bg-gray-50 border border-gray-200 p-4 rounded-xl text-sm font-mono whitespace-pre-wrap break-all">
          {entry.msg}
        </div>
      </div>

      {/* Exception */}
      {entry.exc && (
        <div>
          <h4 className="text-xs font-bold text-gray-500 uppercase mb-2">Exception</h4>
          <pre className="bg-red-50 border border-red-200 p-4 rounded-xl text-xs font-mono whitespace-pre-wrap text-red-700">
            {entry.exc}
          </pre>
        </div>
      )}

      {/* Extra fields */}
      {(() => {
        const extraKeys = Object.keys(entry).filter(
          k => !['timestamp', 'level', 'logger', 'msg', 'tenant_id', 'user_id', 'session_id', 'exc', 'ts'].includes(k)
        );
        if (extraKeys.length === 0) return null;
        return (
          <div>
            <h4 className="text-xs font-bold text-gray-500 uppercase mb-2">Additional Fields</h4>
            <pre className="bg-gray-50 border border-gray-200 p-4 rounded-xl text-xs font-mono whitespace-pre-wrap">
              {JSON.stringify(
                Object.fromEntries(extraKeys.map(k => [k, entry[k]])),
                null, 2
              )}
            </pre>
          </div>
        );
      })()}
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

  // Fetch on mount and when session changes
  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

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
          <span>{logs.length} log{logs.length !== 1 ? 's' : ''}</span>
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

      {/* Log list */}
      <div className="space-y-1.5">
        {logs.map((entry, i) => (
          <LogCard
            key={`cw-${i}-${entry.timestamp}`}
            entry={entry}
            onClick={() => setSelectedEntry(entry)}
          />
        ))}
      </div>

      {/* Detail modal */}
      {selectedEntry && (
        <TraceDetailModal
          isOpen={true}
          onClose={() => setSelectedEntry(null)}
          data={selectedEntry}
          downloadFilename={`cloudwatch-log-${selectedEntry.timestamp}.json`}
          header={
            <>
              <Cloud className="w-4 h-4 text-sky-600 shrink-0" />
              <span className="text-sm font-bold text-gray-900">CloudWatch Log</span>
              <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold uppercase ${getLevelStyle(selectedEntry.level).badge}`}>
                {selectedEntry.level}
              </span>
              <span className="text-xs text-gray-500 font-mono truncate">{selectedEntry.logger}</span>
              <span className="text-xs text-gray-400 ml-auto shrink-0">{formatTime(selectedEntry.timestamp)}</span>
            </>
          }
          formattedView={<LogFormattedView entry={selectedEntry} />}
        />
      )}
    </>
  );
}
