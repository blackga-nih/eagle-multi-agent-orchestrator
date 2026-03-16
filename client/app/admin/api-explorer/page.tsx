'use client';

import { useState, useEffect, useCallback } from 'react';
import { RefreshCw, Activity, Clock, AlertTriangle, GitBranch } from 'lucide-react';
import AuthGuard from '@/components/auth/auth-guard';
import TopNav from '@/components/layout/top-nav';
import PageHeader from '@/components/layout/page-header';

interface RequestEntry {
  timestamp: string;
  method: string;
  path: string;
  status_code: number;
  duration_ms: number;
  tenant_id: string;
}

interface RouteStat {
  route: string;
  calls: number;
  avg_ms: number;
  errors: number;
}

const CATEGORIES = ['all', 'sessions', 'chat', 'documents', 'admin', 'other'] as const;
type Category = (typeof CATEGORIES)[number];

function categorize(path: string): Category {
  if (path.startsWith('/api/sessions')) return 'sessions';
  if (path.startsWith('/api/chat') || path.startsWith('/ws/chat')) return 'chat';
  if (path.startsWith('/api/documents') || path.startsWith('/api/packages')) return 'documents';
  if (path.startsWith('/api/admin')) return 'admin';
  return 'other';
}

function statusColor(code: number): string {
  if (code < 300) return 'bg-green-100 text-green-700';
  if (code < 400) return 'bg-blue-100 text-blue-700';
  if (code < 500) return 'bg-yellow-100 text-yellow-700';
  return 'bg-red-100 text-red-700';
}

function methodColor(method: string): string {
  switch (method) {
    case 'GET': return 'text-blue-600';
    case 'POST': return 'text-green-600';
    case 'DELETE': return 'text-red-600';
    case 'PATCH': return 'text-amber-600';
    default: return 'text-gray-600';
  }
}

function fmtTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return iso;
  }
}

function fmtMs(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`;
}

export default function ApiExplorerPage() {
  const [entries, setEntries] = useState<RequestEntry[]>([]);
  const [routeStats, setRouteStats] = useState<RouteStat[]>([]);
  const [totalLogged, setTotalLogged] = useState(0);
  const [filter, setFilter] = useState('');
  const [category, setCategory] = useState<Category>('all');
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/admin/request-log?limit=500');
      if (!res.ok) return;
      const json = await res.json();
      setEntries(json.entries ?? []);
      setRouteStats(json.route_stats ?? []);
      setTotalLogged(json.total_logged ?? 0);
    } catch {
      // non-fatal
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Derived stats
  const totalCalls = routeStats.reduce((s, r) => s + r.calls, 0);
  const totalErrors = routeStats.reduce((s, r) => s + r.errors, 0);
  const avgMs = routeStats.length
    ? Math.round(routeStats.reduce((s, r) => s + r.avg_ms * r.calls, 0) / Math.max(totalCalls, 1))
    : 0;

  // Filtered entries
  const visibleEntries = entries.filter(e => {
    const matchCat = category === 'all' || categorize(e.path) === category;
    const matchFilter = !filter || e.path.toLowerCase().includes(filter.toLowerCase());
    return matchCat && matchFilter;
  });

  // Filtered route stats
  const visibleStats = routeStats.filter(r => {
    if (category === 'all') return true;
    const path = r.route.split(' ')[1] ?? '';
    return categorize(path) === category;
  });

  const summaryCards = [
    { label: 'Total Requests', value: totalLogged, icon: <Activity className="w-5 h-5" />, color: 'bg-blue-500' },
    { label: 'Avg Response', value: fmtMs(avgMs), icon: <Clock className="w-5 h-5" />, color: 'bg-indigo-500' },
    { label: 'Errors', value: totalErrors, icon: <AlertTriangle className="w-5 h-5" />, color: totalErrors > 0 ? 'bg-red-500' : 'bg-green-500' },
    { label: 'Unique Routes', value: routeStats.length, icon: <GitBranch className="w-5 h-5" />, color: 'bg-purple-500' },
  ];

  return (
    <AuthGuard>
      <div className="flex flex-col h-screen bg-gray-50">
        <TopNav />
        <main className="flex-1 overflow-y-auto">
          <div className="p-8">
            <PageHeader
              title="API Explorer"
              description="Live HTTP request history and per-route statistics"
            />

            {/* Summary cards */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
              {summaryCards.map((c, i) => (
                <div key={i} className="bg-white rounded-2xl border border-gray-200 p-5">
                  <div className="flex items-start justify-between mb-3">
                    <div className={`p-3 rounded-xl ${c.color} text-white`}>{c.icon}</div>
                  </div>
                  <p className="text-2xl font-bold text-gray-900">{c.value}</p>
                  <p className="text-sm text-gray-500">{c.label}</p>
                </div>
              ))}
            </div>

            {/* Filters */}
            <div className="flex flex-wrap items-center gap-3 mb-6">
              {CATEGORIES.map(cat => (
                <button
                  key={cat}
                  onClick={() => setCategory(cat)}
                  className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
                    category === cat
                      ? 'bg-blue-600 text-white'
                      : 'bg-white border border-gray-200 text-gray-600 hover:border-blue-400'
                  }`}
                >
                  {cat.charAt(0).toUpperCase() + cat.slice(1)}
                </button>
              ))}
              <input
                type="text"
                placeholder="Filter by path…"
                value={filter}
                onChange={e => setFilter(e.target.value)}
                className="ml-auto px-3 py-1.5 rounded-xl border border-gray-200 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-400 w-56"
              />
              <button
                onClick={load}
                disabled={loading}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-gray-200 rounded-xl text-sm text-gray-600 hover:border-blue-400 disabled:opacity-50"
              >
                <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                Refresh
              </button>
            </div>

            {/* Per-route table */}
            <div className="bg-white rounded-2xl border border-gray-200 mb-6 overflow-hidden">
              <div className="px-6 py-4 border-b border-gray-100">
                <h3 className="font-bold text-gray-900">Per-Route Statistics</h3>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-gray-500 text-xs border-b border-gray-100">
                      <th className="px-6 py-3 font-medium">Route</th>
                      <th className="px-4 py-3 font-medium text-right">Calls</th>
                      <th className="px-4 py-3 font-medium text-right">Avg ms</th>
                      <th className="px-4 py-3 font-medium text-right">Errors</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleStats.length === 0 ? (
                      <tr>
                        <td colSpan={4} className="px-6 py-8 text-center text-gray-400">
                          No route data yet — make some requests first.
                        </td>
                      </tr>
                    ) : (
                      visibleStats.map((r, i) => {
                        const [method, ...pathParts] = r.route.split(' ');
                        const path = pathParts.join(' ');
                        return (
                          <tr key={i} className="border-b border-gray-50 hover:bg-gray-50">
                            <td className="px-6 py-3 font-mono">
                              <span className={`font-bold mr-2 ${methodColor(method)}`}>{method}</span>
                              <span className="text-gray-700">{path}</span>
                            </td>
                            <td className="px-4 py-3 text-right text-gray-700">{r.calls}</td>
                            <td className="px-4 py-3 text-right text-gray-500">{fmtMs(r.avg_ms)}</td>
                            <td className="px-4 py-3 text-right">
                              {r.errors > 0 ? (
                                <span className="text-red-600 font-medium">{r.errors}</span>
                              ) : (
                                <span className="text-gray-400">0</span>
                              )}
                            </td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Recent call log */}
            <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden">
              <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
                <h3 className="font-bold text-gray-900">Recent Calls</h3>
                <span className="text-xs text-gray-400">{visibleEntries.length} entries</span>
              </div>
              <div className="overflow-x-auto max-h-96 overflow-y-auto">
                <table className="w-full text-sm font-mono">
                  <thead className="sticky top-0 bg-white border-b border-gray-100">
                    <tr className="text-left text-gray-500 text-xs">
                      <th className="px-6 py-3 font-medium">Time</th>
                      <th className="px-4 py-3 font-medium">Method</th>
                      <th className="px-4 py-3 font-medium">Path</th>
                      <th className="px-4 py-3 font-medium">Status</th>
                      <th className="px-4 py-3 font-medium">Duration</th>
                      <th className="px-4 py-3 font-medium">Tenant</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleEntries.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="px-6 py-8 text-center text-gray-400 font-sans">
                          {loading ? 'Loading…' : 'No requests recorded yet.'}
                        </td>
                      </tr>
                    ) : (
                      visibleEntries.map((e, i) => (
                        <tr key={i} className="border-b border-gray-50 hover:bg-gray-50">
                          <td className="px-6 py-2 text-gray-400 text-xs whitespace-nowrap">{fmtTime(e.timestamp)}</td>
                          <td className={`px-4 py-2 font-bold text-xs ${methodColor(e.method)}`}>{e.method}</td>
                          <td className="px-4 py-2 text-gray-700 max-w-xs truncate">{e.path}</td>
                          <td className="px-4 py-2">
                            <span className={`px-1.5 py-0.5 rounded text-xs font-semibold ${statusColor(e.status_code)}`}>
                              {e.status_code}
                            </span>
                          </td>
                          <td className="px-4 py-2 text-gray-500 text-xs whitespace-nowrap">{fmtMs(e.duration_ms)}</td>
                          <td className="px-4 py-2 text-gray-400 text-xs">{e.tenant_id}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </main>
      </div>
    </AuthGuard>
  );
}
