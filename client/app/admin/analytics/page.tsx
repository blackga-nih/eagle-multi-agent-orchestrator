'use client';

import { useState, useEffect, useCallback } from 'react';
import AuthGuard from '@/components/auth/auth-guard';
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Clock,
  DollarSign,
  Loader2,
  RefreshCw,
  ThumbsUp,
  TrendingUp,
  Wrench,
  Zap,
} from 'lucide-react';
import TopNav from '@/components/layout/top-nav';
import PageHeader from '@/components/layout/page-header';
import { useAuth } from '@/contexts/auth-context';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface TraceSummary {
  period: string;
  total_traces: number;
  error_count: number;
  error_rate_pct: number;
  avg_latency_ms: number;
  total_cost_usd: number;
  error_breakdown: Record<string, number>;
}

interface ToolHealth {
  name: string;
  call_count: number;
  success_rate: number;
  avg_duration_ms: number;
  error_count: number;
}

interface FeedbackSummary {
  total: number;
  thumbs_up: number;
  thumbs_down: number;
  thumbs_up_pct: number;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDuration(ms: number): string {
  if (ms >= 60_000) return `${(ms / 60_000).toFixed(1)}m`;
  if (ms >= 1_000) return `${(ms / 1_000).toFixed(1)}s`;
  return `${ms}ms`;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function AnalyticsPage() {
  const { getToken } = useAuth();
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState<'24h' | '7d'>('24h');
  const [traceSummary, setTraceSummary] = useState<TraceSummary | null>(null);
  const [tools, setTools] = useState<ToolHealth[]>([]);
  const [feedback, setFeedback] = useState<FeedbackSummary | null>(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const token = await getToken();
      const headers = {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      };

      const [traceRes, toolsRes, feedbackRes] = await Promise.all([
        fetch(`/api/admin/traces/summary?period=${period}`, { headers }).catch(() => null),
        fetch(`/api/admin/tools?period=${period}`, { headers }).catch(() => null),
        fetch('/api/feedback/messages/summary', { headers }).catch(() => null),
      ]);

      if (traceRes?.ok) {
        setTraceSummary(await traceRes.json());
      }
      if (toolsRes?.ok) {
        const data = await toolsRes.json();
        setTools(data.tools || []);
      }
      if (feedbackRes?.ok) {
        setFeedback(await feedbackRes.json());
      }
    } catch {
      // Silent fail — partial data is fine
    } finally {
      setLoading(false);
    }
  }, [getToken, period]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  return (
    <AuthGuard>
      <div className="flex flex-col h-screen bg-gray-50">
        <TopNav />

        <main className="flex-1 overflow-y-auto">
          <div className="p-8">
            <PageHeader
              title="Analytics"
              description="Real-time observability across traces, tools, and feedback"
              breadcrumbs={[
                { label: 'Admin', href: '/admin' },
                { label: 'Analytics' },
              ]}
              actions={
                <div className="flex items-center gap-3">
                  <div className="inline-flex items-center bg-white border border-gray-200 rounded-xl p-1">
                    {(['24h', '7d'] as const).map((p) => (
                      <button
                        key={p}
                        onClick={() => setPeriod(p)}
                        className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                          period === p
                            ? 'bg-[#003149] text-white shadow-md'
                            : 'text-gray-600 hover:bg-gray-100'
                        }`}
                      >
                        {p}
                      </button>
                    ))}
                  </div>
                  <button
                    onClick={fetchAll}
                    disabled={loading}
                    className="flex items-center gap-2 px-4 py-2.5 bg-white border border-gray-200 text-gray-700 rounded-xl font-medium hover:bg-gray-50 transition-colors disabled:opacity-50"
                  >
                    <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                    Refresh
                  </button>
                </div>
              }
            />

            {loading && !traceSummary ? (
              <div className="p-12 text-center">
                <Loader2 className="w-6 h-6 text-[#003149] animate-spin mx-auto mb-3" />
                <p className="text-sm text-gray-500">Loading analytics...</p>
              </div>
            ) : (
              <>
                {/* Summary cards */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 xl:grid-cols-6 gap-4 mb-8">
                  <SummaryCard
                    icon={<Activity className="w-5 h-5" />}
                    label="Total Traces"
                    value={String(traceSummary?.total_traces ?? '—')}
                    color="bg-[#003149]"
                  />
                  <SummaryCard
                    icon={<AlertTriangle className="w-5 h-5" />}
                    label="Error Rate"
                    value={traceSummary ? `${traceSummary.error_rate_pct}%` : '—'}
                    color={
                      (traceSummary?.error_rate_pct ?? 0) > 10
                        ? 'bg-red-500'
                        : 'bg-amber-500'
                    }
                  />
                  <SummaryCard
                    icon={<Clock className="w-5 h-5" />}
                    label="Avg Latency"
                    value={
                      traceSummary
                        ? formatDuration(traceSummary.avg_latency_ms)
                        : '—'
                    }
                    color="bg-blue-500"
                  />
                  <SummaryCard
                    icon={<DollarSign className="w-5 h-5" />}
                    label="Total Cost"
                    value={
                      traceSummary
                        ? `$${traceSummary.total_cost_usd.toFixed(4)}`
                        : '—'
                    }
                    color="bg-green-500"
                  />
                  <SummaryCard
                    icon={<ThumbsUp className="w-5 h-5" />}
                    label="Approval Rate"
                    value={feedback ? `${feedback.thumbs_up_pct}%` : '—'}
                    color="bg-emerald-500"
                    subtitle={
                      feedback
                        ? `${feedback.thumbs_up}/${feedback.total} positive`
                        : undefined
                    }
                  />
                  <SummaryCard
                    icon={<Zap className="w-5 h-5" />}
                    label="Errors"
                    value={String(traceSummary?.error_count ?? '—')}
                    color="bg-red-500"
                  />
                </div>

                {/* Two-column layout: Tool Health + Error Breakdown */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
                  {/* Tool Health */}
                  <div className="bg-white rounded-2xl border border-gray-200">
                    <div className="p-4 border-b border-gray-100 flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Wrench className="w-4 h-4 text-gray-400" />
                        <h3 className="font-bold text-gray-900">Tool Health</h3>
                      </div>
                      <a
                        href="/admin/tools"
                        className="text-xs text-blue-600 hover:text-blue-800 font-medium"
                      >
                        View all
                      </a>
                    </div>
                    {tools.length === 0 ? (
                      <div className="p-8 text-center text-gray-400 text-sm">
                        No tool data available yet
                      </div>
                    ) : (
                      <div className="divide-y divide-gray-50 max-h-[300px] overflow-y-auto">
                        {tools.slice(0, 10).map((tool) => (
                          <div
                            key={tool.name}
                            className="px-4 py-3 flex items-center justify-between"
                          >
                            <div className="flex items-center gap-2 min-w-0">
                              <span className="text-sm font-medium text-gray-900 truncate">
                                {tool.name}
                              </span>
                              <span className="text-xs text-gray-400">
                                {tool.call_count} calls
                              </span>
                            </div>
                            <div className="flex items-center gap-3">
                              <span className="text-xs text-gray-500">
                                {formatDuration(tool.avg_duration_ms)}
                              </span>
                              <span
                                className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                                  tool.success_rate >= 95
                                    ? 'bg-green-50 text-green-600'
                                    : tool.success_rate >= 80
                                    ? 'bg-amber-50 text-amber-600'
                                    : 'bg-red-50 text-red-600'
                                }`}
                              >
                                {tool.success_rate.toFixed(0)}%
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Error Breakdown */}
                  <div className="bg-white rounded-2xl border border-gray-200">
                    <div className="p-4 border-b border-gray-100 flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <BarChart3 className="w-4 h-4 text-gray-400" />
                        <h3 className="font-bold text-gray-900">Error Breakdown</h3>
                      </div>
                      <a
                        href="/admin/traces"
                        className="text-xs text-blue-600 hover:text-blue-800 font-medium"
                      >
                        View traces
                      </a>
                    </div>
                    {!traceSummary ||
                    Object.keys(traceSummary.error_breakdown).length === 0 ? (
                      <div className="p-8 text-center text-gray-400 text-sm">
                        No errors in this period
                      </div>
                    ) : (
                      <div className="p-4 space-y-3">
                        {Object.entries(traceSummary.error_breakdown)
                          .sort(([, a], [, b]) => b - a)
                          .map(([category, count]) => {
                            const maxCount = Math.max(
                              ...Object.values(traceSummary.error_breakdown)
                            );
                            return (
                              <div key={category}>
                                <div className="flex items-center justify-between mb-1">
                                  <span className="text-sm text-gray-700 capitalize">
                                    {category.replace(/-/g, ' ')}
                                  </span>
                                  <span className="text-sm font-medium text-gray-900">
                                    {count}
                                  </span>
                                </div>
                                <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                                  <div
                                    className="h-full bg-red-400 rounded-full"
                                    style={{
                                      width: `${(count / maxCount) * 100}%`,
                                    }}
                                  />
                                </div>
                              </div>
                            );
                          })}
                      </div>
                    )}
                  </div>
                </div>

                {/* Feedback summary */}
                {feedback && feedback.total > 0 && (
                  <div className="bg-white rounded-2xl border border-gray-200 p-6 mb-8">
                    <div className="flex items-center justify-between mb-4">
                      <div className="flex items-center gap-2">
                        <TrendingUp className="w-4 h-4 text-gray-400" />
                        <h3 className="font-bold text-gray-900">
                          User Feedback
                        </h3>
                      </div>
                      <a
                        href="/admin/feedback"
                        className="text-xs text-blue-600 hover:text-blue-800 font-medium"
                      >
                        View all feedback
                      </a>
                    </div>
                    <div className="flex items-center gap-8">
                      <div>
                        <p className="text-3xl font-bold text-gray-900">
                          {feedback.thumbs_up_pct}%
                        </p>
                        <p className="text-sm text-gray-500">positive</p>
                      </div>
                      <div className="flex-1 h-4 bg-gray-100 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-green-400 rounded-full"
                          style={{
                            width: `${feedback.thumbs_up_pct}%`,
                          }}
                        />
                      </div>
                      <div className="text-right">
                        <p className="text-sm text-gray-700">
                          <span className="font-medium text-green-600">
                            {feedback.thumbs_up}
                          </span>{' '}
                          /{' '}
                          <span className="font-medium text-red-600">
                            {feedback.thumbs_down}
                          </span>
                        </p>
                        <p className="text-xs text-gray-400">
                          {feedback.total} total
                        </p>
                      </div>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </main>
      </div>
    </AuthGuard>
  );
}

// ---------------------------------------------------------------------------
// SummaryCard
// ---------------------------------------------------------------------------

function SummaryCard({
  icon,
  label,
  value,
  color,
  subtitle,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  color: string;
  subtitle?: string;
}) {
  return (
    <div className="bg-white rounded-2xl border border-gray-200 p-5">
      <div className="flex items-start justify-between mb-4">
        <div className={`p-3 rounded-xl ${color} text-white`}>{icon}</div>
      </div>
      <p className="text-2xl font-bold text-gray-900">{value}</p>
      <p className="text-sm text-gray-500">{label}</p>
      {subtitle && <p className="text-xs text-gray-400 mt-1">{subtitle}</p>}
    </div>
  );
}
