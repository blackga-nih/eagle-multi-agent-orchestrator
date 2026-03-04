'use client';

import { useState, useEffect } from 'react';
import Badge from '@/components/ui/badge';

interface TraceSummary {
  trace_id: string;
  session_id: string;
  user_id: string;
  created_at: string;
  duration_ms: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cost_usd: number;
  tools_called: string[];
  agents_delegated: string[];
  span_count: number;
  status: string;
}

interface TraceDetail extends TraceSummary {
  tenant_id: string;
  spans: Array<{
    name: string;
    span_type: string;
    duration_ms: number;
    input_data?: Record<string, unknown>;
    output_data?: string;
    metadata?: Record<string, unknown>;
  }>;
  trace_json?: Array<Record<string, unknown>>;
}

export default function TracesPage() {
  const [traces, setTraces] = useState<TraceSummary[]>([]);
  const [selectedTrace, setSelectedTrace] = useState<TraceDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    fetch('/api/admin/traces?limit=50')
      .then((res) => res.json())
      .then((data) => setTraces(data.traces || []))
      .catch((err) => console.error('Failed to fetch traces:', err))
      .finally(() => setLoading(false));
  }, []);

  const loadTraceDetail = async (trace: TraceSummary) => {
    setDetailLoading(true);
    try {
      const date = trace.created_at?.split('T')[0] || '';
      const res = await fetch(
        `/api/admin/traces/${trace.trace_id}?date=${date}`
      );
      if (res.ok) {
        const data = await res.json();
        setSelectedTrace(data);
      }
    } catch (err) {
      console.error('Failed to fetch trace detail:', err);
    } finally {
      setDetailLoading(false);
    }
  };

  return (
    <div className="container mx-auto py-8 px-4">
      <h1 className="text-2xl font-bold mb-6">Agent Traces</h1>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Trace list */}
        <div>
          <h2 className="text-lg font-semibold mb-3">Recent Traces</h2>
          {loading ? (
            <p className="text-muted-foreground">Loading traces...</p>
          ) : traces.length === 0 ? (
            <p className="text-muted-foreground">No traces found.</p>
          ) : (
            <div className="flex flex-col gap-2 max-h-[70vh] overflow-y-auto">
              {traces.map((trace) => (
                <div
                  key={trace.trace_id}
                  className="border rounded-lg p-3 cursor-pointer hover:bg-accent transition-colors"
                  onClick={() => loadTraceDetail(trace)}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-mono text-muted-foreground">
                      {trace.trace_id}
                    </span>
                    <Badge
                      variant={
                        trace.status === 'success' ? 'success' : 'danger'
                      }
                    >
                      {trace.status}
                    </Badge>
                  </div>
                  <div className="flex gap-3 text-sm text-muted-foreground">
                    <span>{trace.duration_ms}ms</span>
                    <span>
                      {trace.total_input_tokens + trace.total_output_tokens}{' '}
                      tokens
                    </span>
                    <span>${trace.total_cost_usd?.toFixed(4)}</span>
                    <span>{trace.span_count} spans</span>
                  </div>
                  {trace.agents_delegated?.length > 0 && (
                    <div className="flex gap-1 mt-1 flex-wrap">
                      {trace.agents_delegated.map((a) => (
                        <Badge key={a} variant="info" className="text-xs">
                          {a}
                        </Badge>
                      ))}
                    </div>
                  )}
                  <div className="text-xs text-muted-foreground mt-1">
                    {trace.created_at
                      ? new Date(trace.created_at).toLocaleString()
                      : ''}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Trace detail */}
        <div>
          <h2 className="text-lg font-semibold mb-3">Trace Detail</h2>
          {detailLoading ? (
            <p className="text-muted-foreground">Loading...</p>
          ) : selectedTrace ? (
            <div className="border rounded-lg p-4 max-h-[70vh] overflow-y-auto">
              <div className="mb-4">
                <h3 className="font-mono text-sm mb-2">
                  {selectedTrace.trace_id}
                </h3>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div>
                    <span className="text-muted-foreground">Session:</span>{' '}
                    <span className="font-mono text-xs">
                      {selectedTrace.session_id}
                    </span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">User:</span>{' '}
                    {selectedTrace.user_id}
                  </div>
                  <div>
                    <span className="text-muted-foreground">Duration:</span>{' '}
                    {selectedTrace.duration_ms}ms
                  </div>
                  <div>
                    <span className="text-muted-foreground">Cost:</span> $
                    {selectedTrace.total_cost_usd?.toFixed(4)}
                  </div>
                  <div>
                    <span className="text-muted-foreground">Input:</span>{' '}
                    {selectedTrace.total_input_tokens} tokens
                  </div>
                  <div>
                    <span className="text-muted-foreground">Output:</span>{' '}
                    {selectedTrace.total_output_tokens} tokens
                  </div>
                </div>
              </div>

              {/* Spans */}
              {selectedTrace.spans?.length > 0 && (
                <div className="mb-4">
                  <h4 className="font-semibold text-sm mb-2">
                    Spans ({selectedTrace.spans.length})
                  </h4>
                  <div className="flex flex-col gap-1">
                    {selectedTrace.spans.map((span, i) => (
                      <div
                        key={i}
                        className="flex items-center gap-2 text-sm bg-muted/50 rounded px-2 py-1"
                      >
                        <Badge
                          variant="info"
                          className="text-xs"
                        >
                          {span.span_type}
                        </Badge>
                        <span className="font-mono text-xs">{span.name}</span>
                        <span className="text-muted-foreground ml-auto">
                          {span.duration_ms}ms
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Tools called */}
              {selectedTrace.tools_called?.length > 0 && (
                <div className="mb-4">
                  <h4 className="font-semibold text-sm mb-2">Tools Called</h4>
                  <div className="flex gap-1 flex-wrap">
                    {selectedTrace.tools_called.map((t) => (
                      <Badge key={t} variant="info" className="text-xs">
                        {t}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}

              {/* Agents delegated */}
              {selectedTrace.agents_delegated?.length > 0 && (
                <div>
                  <h4 className="font-semibold text-sm mb-2">
                    Agents Delegated
                  </h4>
                  <div className="flex gap-1 flex-wrap">
                    {selectedTrace.agents_delegated.map((a) => (
                      <Badge key={a} variant="info" className="text-xs">
                        {a}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <p className="text-muted-foreground">
              Select a trace to view details.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
