'use client';

import { useState, useEffect, useMemo } from 'react';
import AuthGuard from '@/components/auth/auth-guard';
import TopNav from '@/components/layout/top-nav';
import {
  CheckCircle2,
  XCircle,
  SkipForward,
  ChevronDown,
  ChevronRight,
  Clock,
  Cpu,
  Filter,
  RefreshCw,
  ArrowLeft,
  BarChart3,
  List,
  TrendingUp,
  TrendingDown,
  Minus,
} from 'lucide-react';

/* ── Types ─────────────────────────────────────────────────────── */

interface TestRun {
  run_id: string;
  timestamp: string;
  total: number;
  passed: number;
  failed: number;
  skipped: number;
  errors: number;
  duration_s: number;
  pass_rate: number;
  model: string;
  trigger: string;
}

interface TestResultDetail {
  nodeid: string;
  test_file: string;
  test_name: string;
  status: string;
  duration_s: number;
  error: string;
}

/* ── Helpers ───────────────────────────────────────────────────── */

function statusBadge(status: string) {
  if (status === 'passed') return <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-green-50 text-green-700">PASS</span>;
  if (status === 'failed') return <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-red-50 text-red-700">FAIL</span>;
  return <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-50 text-yellow-700">SKIP</span>;
}

function triggerBadge(trigger: string) {
  if (trigger === 'eval') return <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-purple-50 text-purple-700 border border-purple-200">EVAL</span>;
  if (trigger === 'pytest') return <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-blue-50 text-blue-700 border border-blue-200">PYTEST</span>;
  return <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-gray-50 text-gray-600 border border-gray-200">{trigger.toUpperCase()}</span>;
}

function passRateColor(rate: number) {
  if (rate >= 95) return 'text-green-600';
  if (rate >= 80) return 'text-yellow-600';
  return 'text-red-600';
}

function passRateBg(rate: number) {
  if (rate >= 95) return 'bg-green-500';
  if (rate >= 80) return 'bg-yellow-500';
  return 'bg-red-500';
}

function formatDuration(s: number) {
  if (s < 60) return `${s.toFixed(1)}s`;
  const m = Math.floor(s / 60);
  const sec = (s % 60).toFixed(0);
  return `${m}m ${sec}s`;
}

function formatTimestamp(ts: string) {
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return ts;
  }
}

function formatDate(ts: string) {
  try {
    return new Date(ts).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  } catch {
    return ts;
  }
}

/* ── Component ─────────────────────────────────────────────────── */

export default function TestResults() {
  const [runs, setRuns] = useState<TestRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<string | null>(null);
  const [results, setResults] = useState<TestResultDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedTests, setExpandedTests] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState<'all' | 'passed' | 'failed'>('all');
  const [tab, setTab] = useState<'runs' | 'analytics'>('runs');

  useEffect(() => {
    loadRuns();
  }, []);

  const loadRuns = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/admin/test-runs?limit=50');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setRuns(json.runs || []);
    } catch {
      setError('Could not load test runs. Run pytest to generate results.');
    }
    setLoading(false);
  };

  const loadRunDetail = async (runId: string) => {
    setDetailLoading(true);
    setSelectedRun(runId);
    setExpandedTests(new Set());
    setFilter('all');
    try {
      const res = await fetch(`/api/admin/test-runs/${encodeURIComponent(runId)}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setResults(json.results || []);
    } catch {
      setResults([]);
    }
    setDetailLoading(false);
  };

  const backToList = () => {
    setSelectedRun(null);
    setResults([]);
  };

  const toggleExpand = (id: string) => {
    setExpandedTests(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  /* ── Analytics Data ────────────────────────────────────────────── */

  const analytics = useMemo(() => {
    if (runs.length === 0) return null;

    const totalRuns = runs.length;
    const pytestRuns = runs.filter(r => r.trigger === 'pytest');
    const evalRuns = runs.filter(r => r.trigger === 'eval');

    const totalTests = runs.reduce((s, r) => s + r.total, 0);
    const totalPassed = runs.reduce((s, r) => s + r.passed, 0);
    const totalFailed = runs.reduce((s, r) => s + r.failed, 0);
    const avgPassRate = runs.reduce((s, r) => s + r.pass_rate, 0) / totalRuns;
    const avgDuration = runs.reduce((s, r) => s + r.duration_s, 0) / totalRuns;

    const allPass = runs.filter(r => r.failed === 0 && r.errors === 0).length;
    const greenRate = (allPass / totalRuns) * 100;

    // Trend: compare first half vs second half
    const mid = Math.floor(totalRuns / 2);
    const recentHalf = runs.slice(0, mid || 1);
    const olderHalf = runs.slice(mid || 1);
    const recentAvg = recentHalf.reduce((s, r) => s + r.pass_rate, 0) / (recentHalf.length || 1);
    const olderAvg = olderHalf.length > 0 ? olderHalf.reduce((s, r) => s + r.pass_rate, 0) / olderHalf.length : recentAvg;
    const trend = recentAvg - olderAvg;

    // Models used
    const models = [...new Set(runs.map(r => r.model))];

    // Last 10 runs for sparkline (chronological order: oldest first)
    const sparkline = runs.slice(0, 10).reverse();

    return {
      totalRuns,
      pytestRuns: pytestRuns.length,
      evalRuns: evalRuns.length,
      totalTests,
      totalPassed,
      totalFailed,
      avgPassRate,
      avgDuration,
      greenRate,
      trend,
      models,
      sparkline,
      latestRun: runs[0],
    };
  }, [runs]);

  // ── Analytics View ────────────────────────────────────────────

  const renderAnalytics = () => {
    if (loading) {
      return (
        <div className="flex items-center justify-center py-20">
          <RefreshCw className="w-6 h-6 animate-spin text-gray-400" />
          <span className="ml-2 text-gray-500">Loading analytics...</span>
        </div>
      );
    }

    if (!analytics) {
      return (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-6 text-center">
          <p className="text-amber-700 font-medium">No test data yet.</p>
          <p className="text-amber-600 text-sm mt-2">Run tests to populate analytics.</p>
        </div>
      );
    }

    const a = analytics;
    const TrendIcon = a.trend > 1 ? TrendingUp : a.trend < -1 ? TrendingDown : Minus;
    const trendColor = a.trend > 1 ? 'text-green-600' : a.trend < -1 ? 'text-red-600' : 'text-gray-500';

    return (
      <div className="space-y-6">
        {/* Summary cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-white rounded-2xl border border-gray-200 p-5">
            <p className="text-xs text-gray-500 uppercase tracking-wide">Total Runs</p>
            <p className="text-3xl font-bold text-gray-900 mt-1">{a.totalRuns}</p>
            <div className="flex gap-2 mt-2">
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-50 text-blue-700">{a.pytestRuns} pytest</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-50 text-purple-700">{a.evalRuns} eval</span>
            </div>
          </div>
          <div className="bg-white rounded-2xl border border-gray-200 p-5">
            <p className="text-xs text-gray-500 uppercase tracking-wide">Avg Pass Rate</p>
            <p className={`text-3xl font-bold mt-1 ${passRateColor(a.avgPassRate)}`}>{a.avgPassRate.toFixed(1)}%</p>
            <div className={`flex items-center gap-1 mt-2 text-xs ${trendColor}`}>
              <TrendIcon className="w-3.5 h-3.5" />
              <span>{a.trend >= 0 ? '+' : ''}{a.trend.toFixed(1)}% trend</span>
            </div>
          </div>
          <div className="bg-white rounded-2xl border border-gray-200 p-5">
            <p className="text-xs text-gray-500 uppercase tracking-wide">Green Runs</p>
            <p className="text-3xl font-bold text-green-600 mt-1">{a.greenRate.toFixed(0)}%</p>
            <p className="text-xs text-gray-500 mt-2">{runs.filter(r => r.failed === 0 && r.errors === 0).length}/{a.totalRuns} all-pass</p>
          </div>
          <div className="bg-white rounded-2xl border border-gray-200 p-5">
            <p className="text-xs text-gray-500 uppercase tracking-wide">Avg Duration</p>
            <p className="text-3xl font-bold text-gray-900 mt-1">{formatDuration(a.avgDuration)}</p>
            <p className="text-xs text-gray-500 mt-2">{a.totalTests.toLocaleString()} total tests executed</p>
          </div>
        </div>

        {/* Pass rate sparkline (last 10 runs) */}
        <div className="bg-white rounded-2xl border border-gray-200 p-5">
          <h3 className="text-sm font-medium text-gray-900 mb-4">Pass Rate — Last {a.sparkline.length} Runs</h3>
          <div className="flex items-end gap-1 h-24">
            {a.sparkline.map((run, i) => {
              const height = Math.max(4, (run.pass_rate / 100) * 96);
              return (
                <div key={run.run_id} className="flex-1 flex flex-col items-center gap-1" title={`${formatDate(run.timestamp)}: ${run.pass_rate}%`}>
                  <div
                    className={`w-full rounded-t transition-all ${passRateBg(run.pass_rate)}`}
                    style={{ height: `${height}px`, opacity: 0.7 + (i / a.sparkline.length) * 0.3 }}
                  />
                  <span className="text-[9px] text-gray-400">{formatDate(run.timestamp)}</span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Suite breakdown */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* By trigger type */}
          <div className="bg-white rounded-2xl border border-gray-200 p-5">
            <h3 className="text-sm font-medium text-gray-900 mb-3">By Suite</h3>
            <div className="space-y-3">
              {['pytest', 'eval'].map(trigger => {
                const suiteRuns = runs.filter(r => r.trigger === trigger);
                if (suiteRuns.length === 0) return null;
                const avgRate = suiteRuns.reduce((s, r) => s + r.pass_rate, 0) / suiteRuns.length;
                const greenCount = suiteRuns.filter(r => r.failed === 0 && r.errors === 0).length;
                return (
                  <div key={trigger} className="flex items-center gap-3">
                    {triggerBadge(trigger)}
                    <div className="flex-1">
                      <div className="flex justify-between text-xs mb-1">
                        <span className="text-gray-600">{suiteRuns.length} runs</span>
                        <span className={passRateColor(avgRate)}>{avgRate.toFixed(1)}%</span>
                      </div>
                      <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                        <div className={`h-full rounded-full ${passRateBg(avgRate)}`} style={{ width: `${avgRate}%` }} />
                      </div>
                    </div>
                    <span className="text-[10px] text-gray-400">{greenCount}/{suiteRuns.length} green</span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* By model */}
          <div className="bg-white rounded-2xl border border-gray-200 p-5">
            <h3 className="text-sm font-medium text-gray-900 mb-3">By Model</h3>
            <div className="space-y-3">
              {a.models.map(model => {
                const modelRuns = runs.filter(r => r.model === model);
                const avgRate = modelRuns.reduce((s, r) => s + r.pass_rate, 0) / modelRuns.length;
                return (
                  <div key={model} className="flex items-center gap-3">
                    <span className="text-xs text-gray-700 font-mono w-40 truncate" title={model}>{model}</span>
                    <div className="flex-1">
                      <div className="flex justify-between text-xs mb-1">
                        <span className="text-gray-600">{modelRuns.length} runs</span>
                        <span className={passRateColor(avgRate)}>{avgRate.toFixed(1)}%</span>
                      </div>
                      <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                        <div className={`h-full rounded-full ${passRateBg(avgRate)}`} style={{ width: `${avgRate}%` }} />
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Recent failures */}
        {(() => {
          const failedRuns = runs.filter(r => r.failed > 0).slice(0, 5);
          if (failedRuns.length === 0) return (
            <div className="bg-green-50 border border-green-200 rounded-xl p-4 text-center">
              <CheckCircle2 className="w-5 h-5 text-green-500 mx-auto mb-1" />
              <p className="text-sm text-green-700 font-medium">All recent runs passed</p>
            </div>
          );
          return (
            <div className="bg-white rounded-2xl border border-gray-200 p-5">
              <h3 className="text-sm font-medium text-gray-900 mb-3">Recent Failures</h3>
              <div className="space-y-2">
                {failedRuns.map(run => (
                  <button
                    key={run.run_id}
                    onClick={() => { setTab('runs'); loadRunDetail(run.run_id); }}
                    className="w-full flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-gray-50 text-left transition-colors"
                  >
                    <XCircle className="w-4 h-4 text-red-500 shrink-0" />
                    <span className="text-xs text-gray-700 flex-1">{formatTimestamp(run.timestamp)}</span>
                    {triggerBadge(run.trigger)}
                    <span className="text-xs font-medium text-red-600">{run.failed} failed</span>
                    <span className="text-xs text-gray-500">of {run.total}</span>
                  </button>
                ))}
              </div>
            </div>
          );
        })()}
      </div>
    );
  };

  // ── Run List View ──────────────────────────────────────────────

  const renderRunList = () => {
    if (loading) {
      return (
        <div className="flex items-center justify-center py-20">
          <RefreshCw className="w-6 h-6 animate-spin text-gray-400" />
          <span className="ml-2 text-gray-500">Loading test runs...</span>
        </div>
      );
    }

    if (error || runs.length === 0) {
      return (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-6 text-center">
          <p className="text-amber-700 font-medium">{error || 'No test runs found.'}</p>
          <p className="text-amber-600 text-sm mt-2">
            Run <code className="bg-amber-100 px-1.5 py-0.5 rounded">python -m pytest tests/ -v</code> to generate results
          </p>
        </div>
      );
    }

    return (
      <div className="space-y-2">
        {runs.map((run) => {
          const allPass = run.failed === 0 && run.errors === 0;
          return (
            <button
              key={run.run_id}
              onClick={() => loadRunDetail(run.run_id)}
              className="w-full bg-white rounded-xl border border-gray-200 p-4 text-left hover:bg-gray-50 hover:border-blue-200 transition-all"
            >
              <div className="flex items-center gap-4">
                <div className={`p-2 rounded-lg ${allPass ? 'bg-green-50' : 'bg-red-50'}`}>
                  {allPass
                    ? <CheckCircle2 className="w-5 h-5 text-green-500" />
                    : <XCircle className="w-5 h-5 text-red-500" />
                  }
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900 truncate">
                    {formatTimestamp(run.timestamp)}
                  </p>
                  <p className="text-xs text-gray-500 mt-0.5 flex items-center gap-1.5">
                    {triggerBadge(run.trigger)}
                    <span>{run.model}</span>
                  </p>
                </div>
                <div className="flex items-center gap-6 text-xs">
                  <div className="text-center">
                    <p className="font-bold text-gray-900">{run.total}</p>
                    <p className="text-gray-500">tests</p>
                  </div>
                  <div className="text-center">
                    <p className="font-bold text-green-600">{run.passed}</p>
                    <p className="text-gray-500">pass</p>
                  </div>
                  {run.failed > 0 && (
                    <div className="text-center">
                      <p className="font-bold text-red-600">{run.failed}</p>
                      <p className="text-gray-500">fail</p>
                    </div>
                  )}
                  <div className="text-center">
                    <p className={`font-bold ${passRateColor(run.pass_rate)}`}>
                      {run.pass_rate}%
                    </p>
                    <p className="text-gray-500">rate</p>
                  </div>
                  <div className="text-center">
                    <p className="font-bold text-gray-700">{formatDuration(run.duration_s)}</p>
                    <p className="text-gray-500">time</p>
                  </div>
                </div>
                <ChevronRight className="w-4 h-4 text-gray-400" />
              </div>
            </button>
          );
        })}
      </div>
    );
  };

  // ── Run Detail View ────────────────────────────────────────────

  const renderRunDetail = () => {
    const run = runs.find(r => r.run_id === selectedRun);

    if (detailLoading) {
      return (
        <div className="flex items-center justify-center py-20">
          <RefreshCw className="w-6 h-6 animate-spin text-gray-400" />
          <span className="ml-2 text-gray-500">Loading test details...</span>
        </div>
      );
    }

    const filteredResults = results.filter(r => {
      if (filter === 'all') return true;
      if (filter === 'passed') return r.status === 'passed';
      return r.status === 'failed';
    });

    const passCount = results.filter(r => r.status === 'passed').length;
    const failCount = results.filter(r => r.status === 'failed').length;
    const skipCount = results.filter(r => r.status === 'skipped').length;

    const byFile: Record<string, TestResultDetail[]> = {};
    for (const r of filteredResults) {
      const f = r.test_file || 'unknown';
      if (!byFile[f]) byFile[f] = [];
      byFile[f].push(r);
    }

    return (
      <>
        <button
          onClick={backToList}
          className="flex items-center gap-1 text-sm text-blue-600 hover:text-blue-700 mb-4"
        >
          <ArrowLeft className="w-4 h-4" /> Back to runs
        </button>

        <div className="grid grid-cols-1 md:grid-cols-5 gap-4 mb-6">
          <div className="bg-white rounded-2xl border border-gray-200 p-4">
            <div className="p-2 rounded-xl bg-blue-500 text-white w-fit mb-2"><Cpu className="w-4 h-4" /></div>
            <p className="text-xl font-bold text-gray-900">{results.length}</p>
            <p className="text-xs text-gray-500">Total</p>
          </div>
          <div className="bg-white rounded-2xl border border-gray-200 p-4">
            <div className="p-2 rounded-xl bg-green-500 text-white w-fit mb-2"><CheckCircle2 className="w-4 h-4" /></div>
            <p className="text-xl font-bold text-green-600">{passCount}</p>
            <p className="text-xs text-gray-500">Passed</p>
          </div>
          <div className="bg-white rounded-2xl border border-gray-200 p-4">
            <div className="p-2 rounded-xl bg-red-500 text-white w-fit mb-2"><XCircle className="w-4 h-4" /></div>
            <p className="text-xl font-bold text-red-600">{failCount}</p>
            <p className="text-xs text-gray-500">Failed</p>
          </div>
          <div className="bg-white rounded-2xl border border-gray-200 p-4">
            <div className="p-2 rounded-xl bg-yellow-500 text-white w-fit mb-2"><SkipForward className="w-4 h-4" /></div>
            <p className="text-xl font-bold text-yellow-600">{skipCount}</p>
            <p className="text-xs text-gray-500">Skipped</p>
          </div>
          <div className="bg-white rounded-2xl border border-gray-200 p-4">
            <div className="p-2 rounded-xl bg-gray-500 text-white w-fit mb-2"><Clock className="w-4 h-4" /></div>
            <p className="text-xl font-bold text-gray-900">{run ? formatDuration(run.duration_s) : '--'}</p>
            <p className="text-xs text-gray-500">Duration</p>
          </div>
        </div>

        <div className="flex items-center gap-4 mb-4 text-xs text-gray-500">
          <span className="flex items-center gap-1">
            <Clock className="w-3.5 h-3.5" />
            {run ? formatTimestamp(run.timestamp) : '--'}
          </span>
          {run && triggerBadge(run.trigger)}
          {run && <span>Model: {run.model}</span>}
          {run && <span>Pass rate: {run.pass_rate}%</span>}
        </div>

        <div className="flex items-center gap-2 mb-4">
          <Filter className="w-4 h-4 text-gray-400" />
          {(['all', 'passed', 'failed'] as const).map(f => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-1 text-xs rounded-full transition-colors ${
                filter === f
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              {f === 'all' ? `All (${results.length})` : f === 'passed' ? `Pass (${passCount})` : `Fail (${failCount})`}
            </button>
          ))}
        </div>

        <div className="space-y-4">
          {Object.entries(byFile).map(([file, tests]) => {
            const filePass = tests.filter(t => t.status === 'passed').length;
            const fileTotal = tests.length;
            return (
              <div key={file} className="bg-white rounded-xl border border-gray-200 overflow-hidden">
                <div className="px-4 py-3 bg-gray-50 border-b border-gray-100 flex items-center gap-2">
                  <span className="text-sm font-medium text-gray-900">{file}</span>
                  <span className="text-xs text-gray-500">({filePass}/{fileTotal} passed)</span>
                </div>
                <div className="divide-y divide-gray-100">
                  {tests.map(t => {
                    const isExpanded = expandedTests.has(t.nodeid);
                    return (
                      <div key={t.nodeid}>
                        <button
                          onClick={() => t.error ? toggleExpand(t.nodeid) : undefined}
                          className={`w-full flex items-center gap-3 px-4 py-2.5 text-left ${t.error ? 'hover:bg-gray-50 cursor-pointer' : 'cursor-default'} transition-colors`}
                        >
                          {t.error ? (
                            isExpanded ? <ChevronDown className="w-3.5 h-3.5 text-gray-400 shrink-0" /> : <ChevronRight className="w-3.5 h-3.5 text-gray-400 shrink-0" />
                          ) : (
                            <span className="w-3.5" />
                          )}
                          {t.status === 'passed'
                            ? <CheckCircle2 className="w-4 h-4 text-green-500 shrink-0" />
                            : t.status === 'failed'
                            ? <XCircle className="w-4 h-4 text-red-500 shrink-0" />
                            : <SkipForward className="w-4 h-4 text-yellow-500 shrink-0" />
                          }
                          <span className="flex-1 text-sm text-gray-800 truncate">{t.test_name}</span>
                          <span className="text-xs text-gray-400 font-mono">{t.duration_s.toFixed(2)}s</span>
                          {statusBadge(t.status)}
                        </button>
                        {isExpanded && t.error && (
                          <div className="border-t border-gray-100 bg-red-50 px-4 py-3">
                            <pre className="text-[11px] text-red-700 font-mono whitespace-pre-wrap leading-relaxed max-h-60 overflow-y-auto">
                              {t.error}
                            </pre>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </>
    );
  };

  // ── Render ─────────────────────────────────────────────────────

  return (
    <AuthGuard>
      <div className="flex flex-col h-screen overflow-hidden bg-gray-50">
        <TopNav />
        <main className="flex-1 overflow-y-auto">
          <div className="p-8 max-w-6xl">
            {/* Page header */}
            <div className="mb-6 flex items-center justify-between">
              <div>
                <h1 className="text-2xl font-bold text-gray-900">
                  {selectedRun ? 'Test Run Details' : 'Test Results'}
                </h1>
                <p className="mt-1 text-gray-500">
                  {selectedRun
                    ? 'Individual test outcomes with error details'
                    : 'History of pytest and eval runs with pass/fail tracking'
                  }
                </p>
              </div>
              {!selectedRun && (
                <button
                  onClick={loadRuns}
                  className="flex items-center gap-1.5 px-3 py-2 text-sm bg-white border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
                >
                  <RefreshCw className="w-4 h-4" />
                  Refresh
                </button>
              )}
            </div>

            {/* Tabs (only when not in detail view) */}
            {!selectedRun && (
              <div className="flex gap-1 mb-6 bg-gray-100 p-1 rounded-lg w-fit">
                <button
                  onClick={() => setTab('runs')}
                  className={`flex items-center gap-1.5 px-4 py-1.5 text-sm rounded-md transition-colors ${
                    tab === 'runs' ? 'bg-white text-gray-900 shadow-sm font-medium' : 'text-gray-500 hover:text-gray-700'
                  }`}
                >
                  <List className="w-4 h-4" />
                  Runs
                </button>
                <button
                  onClick={() => setTab('analytics')}
                  className={`flex items-center gap-1.5 px-4 py-1.5 text-sm rounded-md transition-colors ${
                    tab === 'analytics' ? 'bg-white text-gray-900 shadow-sm font-medium' : 'text-gray-500 hover:text-gray-700'
                  }`}
                >
                  <BarChart3 className="w-4 h-4" />
                  Analytics
                </button>
              </div>
            )}

            {selectedRun
              ? renderRunDetail()
              : tab === 'analytics'
              ? renderAnalytics()
              : renderRunList()
            }
          </div>
        </main>
      </div>
    </AuthGuard>
  );
}
