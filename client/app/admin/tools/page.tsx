'use client';

import { useState, useEffect, useCallback } from 'react';
import { RefreshCw, Loader2, Wrench, AlertTriangle, CheckCircle2, Clock } from 'lucide-react';
import AuthGuard from '@/components/auth/auth-guard';
import TopNav from '@/components/layout/top-nav';
import PageHeader from '@/components/layout/page-header';
import { useAuth } from '@/contexts/auth-context';

interface ToolHealth {
  name: string;
  call_count: number;
  success_count: number;
  error_count: number;
  success_rate: number;
  avg_duration_ms: number;
  recent_errors: string[];
}

export default function ToolsPage() {
  const { getToken } = useAuth();
  const [tools, setTools] = useState<ToolHealth[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchTools = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const token = await getToken();
      const res = await fetch('/api/admin/tools', {
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      });
      if (!res.ok) throw new Error(`Backend error: ${res.status}`);
      const data = await res.json();
      setTools(data.tools || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load tool health');
    } finally {
      setLoading(false);
    }
  }, [getToken]);

  useEffect(() => { fetchTools(); }, [fetchTools]);

  return (
    <AuthGuard>
      <div className="flex flex-col h-screen bg-gray-50">
        <TopNav />
        <main className="flex-1 overflow-y-auto">
          <div className="p-8">
            <PageHeader
              title="Tool Health"
              description="Per-tool call counts, success rates, and latency"
              breadcrumbs={[
                { label: 'Admin', href: '/admin' },
                { label: 'Tools' },
              ]}
              actions={
                <button
                  onClick={fetchTools}
                  disabled={loading}
                  className="flex items-center gap-2 px-4 py-2.5 bg-white border border-gray-200 text-gray-700 rounded-xl font-medium hover:bg-gray-50 transition-colors disabled:opacity-50"
                >
                  <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                  Refresh
                </button>
              }
            />

            {loading ? (
              <div className="p-12 text-center">
                <Loader2 className="w-6 h-6 text-[#003149] animate-spin mx-auto mb-3" />
                <p className="text-sm text-gray-500">Loading tool health data...</p>
              </div>
            ) : error ? (
              <div className="mb-6 flex items-center gap-3 p-4 bg-red-50 border border-red-200 rounded-xl text-red-700">
                <AlertTriangle className="w-5 h-5 flex-shrink-0" />
                <p className="flex-1">{error}</p>
                <button onClick={fetchTools} className="px-3 py-1.5 bg-red-100 text-red-700 rounded-lg text-sm font-medium hover:bg-red-200">Retry</button>
              </div>
            ) : (
              <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden">
                <table className="w-full">
                  <thead>
                    <tr className="bg-gray-50 border-b border-gray-200">
                      <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase">Tool</th>
                      <th className="text-right px-6 py-3 text-xs font-semibold text-gray-500 uppercase">Calls</th>
                      <th className="text-right px-6 py-3 text-xs font-semibold text-gray-500 uppercase">Success Rate</th>
                      <th className="text-right px-6 py-3 text-xs font-semibold text-gray-500 uppercase">Avg Latency</th>
                      <th className="text-right px-6 py-3 text-xs font-semibold text-gray-500 uppercase">Errors</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {tools.length === 0 ? (
                      <tr>
                        <td colSpan={5} className="px-6 py-12 text-center text-gray-400">
                          <Wrench className="w-8 h-8 mx-auto mb-2 text-gray-300" />
                          No tool data available yet
                        </td>
                      </tr>
                    ) : (
                      tools.map((tool) => (
                        <tr key={tool.name} className="hover:bg-gray-50">
                          <td className="px-6 py-4">
                            <div className="flex items-center gap-2">
                              <Wrench className="w-4 h-4 text-gray-400" />
                              <span className="font-medium text-gray-900">{tool.name}</span>
                            </div>
                          </td>
                          <td className="px-6 py-4 text-right text-sm text-gray-700">{tool.call_count}</td>
                          <td className="px-6 py-4 text-right">
                            <span className={`inline-flex items-center gap-1 text-sm font-medium ${
                              tool.success_rate >= 95 ? 'text-green-600' :
                              tool.success_rate >= 80 ? 'text-amber-600' : 'text-red-600'
                            }`}>
                              {tool.success_rate >= 95 ? <CheckCircle2 className="w-3.5 h-3.5" /> : <AlertTriangle className="w-3.5 h-3.5" />}
                              {tool.success_rate.toFixed(1)}%
                            </span>
                          </td>
                          <td className="px-6 py-4 text-right text-sm text-gray-700">
                            <span className="inline-flex items-center gap-1">
                              <Clock className="w-3.5 h-3.5 text-gray-400" />
                              {tool.avg_duration_ms >= 1000 ? `${(tool.avg_duration_ms / 1000).toFixed(1)}s` : `${tool.avg_duration_ms}ms`}
                            </span>
                          </td>
                          <td className="px-6 py-4 text-right">
                            {tool.error_count > 0 ? (
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-red-50 text-red-600 rounded-full text-xs font-medium">
                                {tool.error_count}
                              </span>
                            ) : (
                              <span className="text-sm text-gray-400">0</span>
                            )}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </main>
      </div>
    </AuthGuard>
  );
}
