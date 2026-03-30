'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  Activity,
  ExternalLink,
  Loader2,
  RefreshCw,
  Search,
  Clock,
  Zap,
  DollarSign,
  AlertCircle,
  ChevronDown,
  ChevronRight,
  Filter,
} from 'lucide-react';
import AuthGuard from '@/components/auth/auth-guard';
import TopNav from '@/components/layout/top-nav';
import PageHeader from '@/components/layout/page-header';
import Badge from '@/components/ui/badge';
import { useAuth } from '@/contexts/auth-context';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface TraceSummary {
  trace_id: string;
  name: string;
  session_id: string;
  user_id: string;
  created_at: string;
  duration_ms: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  total_cost_usd: number;
  tags: string[];
  metadata: Record<string, unknown>;
  status: string;
  environment: string;
  input: string | null;
  output: string | null;
  observation_count: number;
  langfuse_url: string;
}

interface Observation {
  id: string;
  name: string;
  type: string;
  start_time: string;
  end_time: string;
  duration_ms: number;
  model: string;
  input_tokens: number;
  output_tokens: number;
  total_cost: number;
  input: string | Record<string, unknown> | null;
  output: string | Record<string, unknown> | null;
  metadata: Record<string, unknown>;
  level: string;
  status_message: string;
}

interface TraceDetail extends TraceSummary {
  observations: Observation[];
}

interface TraceMeta {
  page: number;
  limit: number;
  totalItems: number;
  totalPages: number;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function formatDuration(ms: number): string {
  if (ms >= 60_000) return `${(ms / 60_000).toFixed(1)}m`;
  if (ms >= 1_000) return `${(ms / 1_000).toFixed(1)}s`;
  return `${ms}ms`;
}

function envColor(env: string): string {
  switch (env) {
    case 'local':
      return 'bg-yellow-100 text-yellow-800';
    case 'dev':
      return 'bg-blue-100 text-blue-800';
    case 'live':
    case 'prod':
      return 'bg-green-100 text-green-800';
    default:
      return 'bg-gray-100 text-gray-600';
  }
}

function obsTypeColor(type: string): string {
  switch (type) {
    case 'GENERATION':
      return 'bg-purple-100 text-purple-800';
    case 'SPAN':
      return 'bg-blue-100 text-blue-800';
    case 'EVENT':
      return 'bg-amber-100 text-amber-800';
    default:
      return 'bg-gray-100 text-gray-600';
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function TracesPage() {
  const { getToken } = useAuth();
  const [traces, setTraces] = useState<TraceSummary[]>([]);
  const [meta, setMeta] = useState<TraceMeta | null>(null);
  const [selectedTrace, setSelectedTrace] = useState<TraceDetail | null>(null);
  const [expandedObs, setExpandedObs] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [page, setPage] = useState(1);
  const [envFilter, setEnvFilter] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState('');

  // -----------------------------------------------------------------------
  // Data fetching
  // -----------------------------------------------------------------------

  const fetchTraces = useCallback(
    async (p: number = 1) => {
      setLoading(true);
      setError(null);
      try {
        const token = await getToken();
        const params = new URLSearchParams({ limit: '50', page: String(p) });
        if (envFilter && envFilter !== 'errors') params.set('tag', `env:${envFilter}`);
        if (searchQuery) params.set('user_id', searchQuery);

        const res = await fetch(`/api/admin/traces?${params}`, {
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
        });
        if (!res.ok) throw new Error(`Backend error: ${res.status}`);
        const data = await res.json();
        if (data.error) throw new Error(data.error);

        let filteredTraces = data.traces || [];
        if (envFilter === 'errors') {
          filteredTraces = filteredTraces.filter((t: TraceSummary) => t.status === 'error');
        }
        setTraces(filteredTraces);
        setMeta(data.meta || null);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load traces');
        setTraces([]);
      } finally {
        setLoading(false);
      }
    },
    [getToken, envFilter, searchQuery],
  );

  useEffect(() => {
    fetchTraces(page);
  }, [page, fetchTraces]);

  const loadTraceDetail = async (trace: TraceSummary) => {
    setDetailLoading(true);
    setExpandedObs(new Set());
    try {
      const token = await getToken();
      const res = await fetch(`/api/admin/traces/${trace.trace_id}`, {
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      });
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

  const toggleObs = (id: string) => {
    setExpandedObs((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // -----------------------------------------------------------------------
  // Summary stats from current page
  // -----------------------------------------------------------------------

  const totalTokens = traces.reduce(
    (sum, t) => sum + t.total_input_tokens + t.total_output_tokens,
    0,
  );
  const totalCost = traces.reduce((sum, t) => sum + (t.total_cost_usd || 0), 0);
  const avgDuration =
    traces.length > 0 ? traces.reduce((sum, t) => sum + t.duration_ms, 0) / traces.length : 0;
  const errorCount = traces.filter((t) => t.status === 'error').length;
  const errorRate = traces.length > 0 ? (errorCount / traces.length) * 100 : 0;

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------

  return (
    <AuthGuard>
      <div className="flex flex-col h-screen bg-gray-50">
        <TopNav />

        <main className="flex-1 overflow-y-auto">
          <div className="p-8">
            <PageHeader
              title="Langfuse Traces"
              description="API invocations and agent traces from Langfuse"
              breadcrumbs={[{ label: 'Admin', href: '/admin' }, { label: 'Traces' }]}
              actions={
                <button
                  onClick={() => fetchTraces(page)}
                  disabled={loading}
                  className="flex items-center gap-2 px-4 py-2.5 bg-white border border-gray-200 text-gray-700 rounded-xl font-medium hover:bg-gray-50 transition-colors disabled:opacity-50"
                >
                  <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                  Refresh
                </button>
              }
            />

            {/* Summary cards */}
            <div className="grid grid-cols-1 md:grid-cols-5 gap-4 mb-6">
              {[
                {
                  icon: <Activity className="w-5 h-5" />,
                  label: 'Traces',
                  value: meta?.totalItems ?? traces.length,
                  color: 'bg-[#003149]',
                },
                {
                  icon: <Clock className="w-5 h-5" />,
                  label: 'Avg Latency',
                  value: formatDuration(avgDuration),
                  color: 'bg-blue-500',
                },
                {
                  icon: <Zap className="w-5 h-5" />,
                  label: 'Page Tokens',
                  value: formatTokens(totalTokens),
                  color: 'bg-purple-500',
                },
                {
                  icon: <DollarSign className="w-5 h-5" />,
                  label: 'Page Cost',
                  value: `$${totalCost.toFixed(4)}`,
                  color: 'bg-green-500',
                },
                {
                  icon: <AlertCircle className="w-5 h-5" />,
                  label: 'Error Rate',
                  value: `${errorRate.toFixed(1)}%`,
                  color: errorRate > 10 ? 'bg-red-500' : 'bg-amber-500',
                },
              ].map((card, i) => (
                <div key={i} className="bg-white rounded-2xl border border-gray-200 p-5">
                  <div className="flex items-start justify-between mb-4">
                    <div className={`p-3 rounded-xl ${card.color} text-white`}>{card.icon}</div>
                  </div>
                  <p className="text-2xl font-bold text-gray-900">{card.value}</p>
                  <p className="text-sm text-gray-500">{card.label}</p>
                </div>
              ))}
            </div>

            {/* Filters */}
            <div className="flex flex-wrap gap-3 mb-6">
              <div className="inline-flex items-center bg-white border border-gray-200 rounded-xl p-1">
                {['', 'local', 'dev', 'live'].map((env) => (
                  <button
                    key={env}
                    onClick={() => {
                      setEnvFilter(env);
                      setPage(1);
                    }}
                    className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                      envFilter === env
                        ? 'bg-[#003149] text-white shadow-md'
                        : 'text-gray-600 hover:bg-gray-100'
                    }`}
                  >
                    {env || 'All'}
                  </button>
                ))}
              </div>

              <button
                onClick={() => {
                  setEnvFilter(envFilter === 'errors' ? '' : 'errors');
                  setPage(1);
                }}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                  envFilter === 'errors'
                    ? 'bg-red-500 text-white shadow-md'
                    : 'text-gray-600 hover:bg-gray-100 border border-gray-200'
                }`}
              >
                <AlertCircle className="w-3.5 h-3.5 inline mr-1" />
                Errors Only
              </button>

              <div className="relative flex-1 min-w-[200px] max-w-sm">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      setPage(1);
                      fetchTraces(1);
                    }
                  }}
                  placeholder="Filter by user ID..."
                  className="w-full pl-10 pr-4 py-2.5 bg-white border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-[#003149]/20 focus:border-[#003149]"
                />
              </div>
            </div>

            {/* Error */}
            {error && (
              <div className="mb-6 flex items-center gap-3 p-4 bg-red-50 border border-red-200 rounded-xl text-red-700">
                <AlertCircle className="w-5 h-5 flex-shrink-0" />
                <div className="flex-1">
                  <p className="font-medium">Failed to load traces</p>
                  <p className="text-sm text-red-600">{error}</p>
                </div>
                <button
                  onClick={() => fetchTraces(page)}
                  className="px-3 py-1.5 bg-red-100 text-red-700 rounded-lg text-sm font-medium hover:bg-red-200 transition-colors"
                >
                  Retry
                </button>
              </div>
            )}

            {/* Main grid: trace list + detail */}
            <div className="grid grid-cols-1 xl:grid-cols-5 gap-6">
              {/* Trace list */}
              <div className="xl:col-span-2">
                <div className="bg-white rounded-2xl border border-gray-200">
                  <div className="p-4 border-b border-gray-100 flex items-center justify-between">
                    <h3 className="font-bold text-gray-900">Recent Traces</h3>
                    {meta && (
                      <span className="text-xs text-gray-400">
                        Page {meta.page} of {meta.totalPages}
                      </span>
                    )}
                  </div>

                  {loading ? (
                    <div className="p-12 text-center">
                      <Loader2 className="w-6 h-6 text-[#003149] animate-spin mx-auto mb-3" />
                      <p className="text-sm text-gray-500">Loading traces from Langfuse...</p>
                    </div>
                  ) : traces.length === 0 ? (
                    <div className="p-12 text-center">
                      <Activity className="w-10 h-10 text-gray-300 mx-auto mb-3" />
                      <p className="text-sm font-medium text-gray-500">No traces found</p>
                    </div>
                  ) : (
                    <div className="divide-y divide-gray-50 max-h-[65vh] overflow-y-auto">
                      {traces.map((trace) => (
                        <div
                          key={trace.trace_id}
                          className={`p-4 cursor-pointer hover:bg-gray-50 transition-colors ${
                            selectedTrace?.trace_id === trace.trace_id
                              ? 'bg-blue-50 border-l-2 border-l-[#003149]'
                              : ''
                          }`}
                          onClick={() => loadTraceDetail(trace)}
                        >
                          <div className="flex items-center justify-between mb-1.5">
                            <div className="flex items-center gap-2">
                              <span className="text-sm font-medium text-gray-900 truncate max-w-[200px]">
                                {trace.name || 'model-inference'}
                              </span>
                              <span
                                className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${envColor(trace.environment)}`}
                              >
                                {trace.environment}
                              </span>
                            </div>
                            <Badge variant={trace.status === 'success' ? 'success' : 'danger'}>
                              {trace.status}
                            </Badge>
                          </div>

                          <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-gray-500">
                            <span>{formatDuration(trace.duration_ms)}</span>
                            <span>
                              {formatTokens(trace.total_input_tokens + trace.total_output_tokens)}{' '}
                              tokens
                            </span>
                            {trace.total_cost_usd > 0 && (
                              <span>${trace.total_cost_usd.toFixed(4)}</span>
                            )}
                            <span>{trace.observation_count} observations</span>
                          </div>

                          {trace.user_id && (
                            <div className="text-[10px] text-gray-400 mt-1 truncate">
                              {trace.user_id}
                            </div>
                          )}
                          <div className="text-[10px] text-gray-400 mt-0.5">
                            {trace.created_at ? new Date(trace.created_at).toLocaleString() : ''}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Pagination */}
                  {meta && meta.totalPages > 1 && (
                    <div className="p-3 border-t border-gray-100 flex items-center justify-between">
                      <button
                        onClick={() => setPage((p) => Math.max(1, p - 1))}
                        disabled={page <= 1}
                        className="px-3 py-1.5 text-sm bg-gray-100 rounded-lg disabled:opacity-40 hover:bg-gray-200 transition-colors"
                      >
                        Previous
                      </button>
                      <span className="text-xs text-gray-500">{meta.totalItems} total traces</span>
                      <button
                        onClick={() => setPage((p) => Math.min(meta.totalPages, p + 1))}
                        disabled={page >= meta.totalPages}
                        className="px-3 py-1.5 text-sm bg-gray-100 rounded-lg disabled:opacity-40 hover:bg-gray-200 transition-colors"
                      >
                        Next
                      </button>
                    </div>
                  )}
                </div>
              </div>

              {/* Trace detail */}
              <div className="xl:col-span-3">
                <div className="bg-white rounded-2xl border border-gray-200">
                  <div className="p-4 border-b border-gray-100">
                    <h3 className="font-bold text-gray-900">Trace Detail</h3>
                  </div>

                  {detailLoading ? (
                    <div className="p-12 text-center">
                      <Loader2 className="w-6 h-6 text-[#003149] animate-spin mx-auto mb-3" />
                      <p className="text-sm text-gray-500">Loading detail...</p>
                    </div>
                  ) : selectedTrace ? (
                    <div className="p-4 max-h-[65vh] overflow-y-auto">
                      {/* Header */}
                      <div className="flex items-center justify-between mb-4">
                        <div>
                          <h4 className="font-semibold text-gray-900">
                            {selectedTrace.name || 'model-inference'}
                          </h4>
                          <p className="text-xs font-mono text-gray-400 mt-0.5">
                            {selectedTrace.trace_id}
                          </p>
                        </div>
                        {selectedTrace.langfuse_url && (
                          <a
                            href={selectedTrace.langfuse_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center gap-1.5 px-3 py-1.5 bg-[#003149] text-white text-xs font-medium rounded-lg hover:bg-[#004166] transition-colors"
                          >
                            <ExternalLink className="w-3 h-3" />
                            View in Langfuse
                          </a>
                        )}
                      </div>

                      {/* Metadata grid */}
                      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-6">
                        {[
                          {
                            label: 'Environment',
                            value: selectedTrace.environment,
                          },
                          {
                            label: 'User',
                            value: selectedTrace.user_id || '-',
                          },
                          {
                            label: 'Session',
                            value: selectedTrace.session_id || '-',
                          },
                          {
                            label: 'Duration',
                            value: formatDuration(selectedTrace.duration_ms),
                          },
                          {
                            label: 'Input Tokens',
                            value: formatTokens(selectedTrace.total_input_tokens),
                          },
                          {
                            label: 'Output Tokens',
                            value: formatTokens(selectedTrace.total_output_tokens),
                          },
                          {
                            label: 'Cost',
                            value: `$${selectedTrace.total_cost_usd?.toFixed(4) || '0'}`,
                          },
                          {
                            label: 'Created',
                            value: selectedTrace.created_at
                              ? new Date(selectedTrace.created_at).toLocaleString()
                              : '-',
                          },
                          {
                            label: 'Status',
                            value: selectedTrace.status,
                          },
                        ].map((item, i) => (
                          <div key={i} className="bg-gray-50 rounded-xl p-3">
                            <p className="text-[10px] text-gray-400 uppercase tracking-wide font-semibold mb-1">
                              {item.label}
                            </p>
                            <p className="text-sm font-medium text-gray-900 truncate">
                              {item.value}
                            </p>
                          </div>
                        ))}
                      </div>

                      {/* Tags */}
                      {selectedTrace.tags?.length > 0 && (
                        <div className="mb-6">
                          <h5 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                            Tags
                          </h5>
                          <div className="flex flex-wrap gap-1.5">
                            {selectedTrace.tags.map((tag) => (
                              <span
                                key={tag}
                                className="text-xs bg-gray-100 text-gray-600 px-2 py-1 rounded-full"
                              >
                                {tag}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Observations / Spans */}
                      {selectedTrace.observations?.length > 0 && (
                        <div>
                          <h5 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">
                            Observations ({selectedTrace.observations.length})
                          </h5>
                          <div className="flex flex-col gap-2">
                            {selectedTrace.observations.map((obs) => (
                              <div
                                key={obs.id}
                                className="border border-gray-100 rounded-xl overflow-hidden"
                              >
                                <div
                                  className="flex items-center gap-2 p-3 cursor-pointer hover:bg-gray-50 transition-colors"
                                  onClick={() => toggleObs(obs.id)}
                                >
                                  {expandedObs.has(obs.id) ? (
                                    <ChevronDown className="w-4 h-4 text-gray-400 flex-shrink-0" />
                                  ) : (
                                    <ChevronRight className="w-4 h-4 text-gray-400 flex-shrink-0" />
                                  )}
                                  <span
                                    className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${obsTypeColor(obs.type)}`}
                                  >
                                    {obs.type}
                                  </span>
                                  <span className="text-sm font-medium text-gray-700 truncate">
                                    {obs.name}
                                  </span>
                                  <div className="ml-auto flex items-center gap-3 text-xs text-gray-400">
                                    {obs.model && (
                                      <span className="bg-blue-50 text-blue-700 px-1.5 py-0.5 rounded font-medium">
                                        {obs.model}
                                      </span>
                                    )}
                                    <span>{formatDuration(obs.duration_ms)}</span>
                                    {obs.input_tokens + obs.output_tokens > 0 && (
                                      <span>
                                        {formatTokens(obs.input_tokens + obs.output_tokens)} tok
                                      </span>
                                    )}
                                    {obs.total_cost > 0 && (
                                      <span>${obs.total_cost.toFixed(4)}</span>
                                    )}
                                  </div>
                                </div>

                                {expandedObs.has(obs.id) && (
                                  <div className="border-t border-gray-100 p-3 bg-gray-50/50">
                                    <div className="grid grid-cols-2 gap-3 mb-3 text-xs">
                                      <div>
                                        <span className="text-gray-400">Input Tokens:</span>{' '}
                                        <span className="font-medium">
                                          {formatTokens(obs.input_tokens)}
                                        </span>
                                      </div>
                                      <div>
                                        <span className="text-gray-400">Output Tokens:</span>{' '}
                                        <span className="font-medium">
                                          {formatTokens(obs.output_tokens)}
                                        </span>
                                      </div>
                                      <div>
                                        <span className="text-gray-400">Start:</span>{' '}
                                        {obs.start_time
                                          ? new Date(obs.start_time).toLocaleTimeString()
                                          : '-'}
                                      </div>
                                      <div>
                                        <span className="text-gray-400">End:</span>{' '}
                                        {obs.end_time
                                          ? new Date(obs.end_time).toLocaleTimeString()
                                          : '-'}
                                      </div>
                                    </div>

                                    {obs.input && (
                                      <div className="mb-2">
                                        <p className="text-[10px] text-gray-400 uppercase font-semibold mb-1">
                                          Input
                                        </p>
                                        <pre className="text-xs bg-gray-900 text-green-400 rounded-lg p-3 overflow-x-auto max-h-40">
                                          {typeof obs.input === 'string'
                                            ? obs.input
                                            : JSON.stringify(obs.input, null, 2)}
                                        </pre>
                                      </div>
                                    )}

                                    {obs.output && (
                                      <div>
                                        <p className="text-[10px] text-gray-400 uppercase font-semibold mb-1">
                                          Output
                                        </p>
                                        <pre className="text-xs bg-gray-900 text-blue-400 rounded-lg p-3 overflow-x-auto max-h-40">
                                          {typeof obs.output === 'string'
                                            ? obs.output
                                            : JSON.stringify(obs.output, null, 2)}
                                        </pre>
                                      </div>
                                    )}

                                    {obs.status_message && (
                                      <div className="mt-2 text-xs text-red-600">
                                        {obs.status_message}
                                      </div>
                                    )}
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="p-12 text-center">
                      <Activity className="w-10 h-10 text-gray-300 mx-auto mb-3" />
                      <p className="text-sm font-medium text-gray-500">
                        Select a trace to view details
                      </p>
                      <p className="text-xs text-gray-400 mt-1">Traces are sourced from Langfuse</p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </main>
      </div>
    </AuthGuard>
  );
}
