'use client';

import { useState, useEffect, useCallback } from 'react';
import { DollarSign, TrendingUp, Zap, Users, Loader2, AlertCircle, RefreshCw } from 'lucide-react';
import AuthGuard from '@/components/auth/auth-guard';
import SidebarNav from '@/components/layout/sidebar-nav';
import PageHeader from '@/components/layout/page-header';
import { useAuth } from '@/contexts/auth-context';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface CostSummary {
  totalCost: number;
  averageCostPerRequest: number;
  totalTokens: number;
  activeUsers: number;
}

interface CostEntry {
  id: string;
  date: string;
  userId: string;
  userEmail: string;
  model: string;
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
  cost: number;
  requestType: string;
}

interface CostReport {
  summary: CostSummary;
  entries: CostEntry[];
  periodDays: number;
}

// ---------------------------------------------------------------------------
// Date range options
// ---------------------------------------------------------------------------

const DATE_RANGES = [
  { label: '7d', days: 7 },
  { label: '30d', days: 30 },
  { label: '90d', days: 90 },
] as const;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  }).format(value);
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat('en-US').format(value);
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function CostsPage() {
  const { getToken } = useAuth();
  const [selectedDays, setSelectedDays] = useState<number>(30);
  const [costReport, setCostReport] = useState<CostReport | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // -----------------------------------------------------------------------
  // Data fetching
  // -----------------------------------------------------------------------

  const fetchCosts = useCallback(async (days: number) => {
    setIsLoading(true);
    setError(null);

    try {
      const token = await getToken();
      const response = await fetch(`/api/admin/costs?days=${days}`, {
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        throw new Error(`Failed to fetch cost data (${response.status})`);
      }

      const data: CostReport = await response.json();
      setCostReport(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'An unexpected error occurred';
      setError(message);
      setCostReport(null);
    } finally {
      setIsLoading(false);
    }
  }, [getToken]);

  useEffect(() => {
    fetchCosts(selectedDays);
  }, [selectedDays, fetchCosts]);

  // -----------------------------------------------------------------------
  // Event handlers
  // -----------------------------------------------------------------------

  const handleDateRangeChange = (days: number) => {
    setSelectedDays(days);
  };

  const handleRefresh = () => {
    fetchCosts(selectedDays);
  };

  // -----------------------------------------------------------------------
  // Summary cards configuration
  // -----------------------------------------------------------------------

  const summaryCards = [
    {
      label: 'Total Cost',
      value: costReport ? formatCurrency(costReport.summary.totalCost) : '--',
      icon: <DollarSign className="w-5 h-5" />,
      color: 'bg-green-500',
      description: `Last ${selectedDays} days`,
    },
    {
      label: 'Avg Cost Per Request',
      value: costReport ? formatCurrency(costReport.summary.averageCostPerRequest) : '--',
      icon: <TrendingUp className="w-5 h-5" />,
      color: 'bg-blue-500',
      description: 'Per API call',
    },
    {
      label: 'Total Tokens',
      value: costReport ? formatNumber(costReport.summary.totalTokens) : '--',
      icon: <Zap className="w-5 h-5" />,
      color: 'bg-purple-500',
      description: 'Input + Output',
    },
    {
      label: 'Active Users',
      value: costReport ? String(costReport.summary.activeUsers) : '--',
      icon: <Users className="w-5 h-5" />,
      color: 'bg-amber-500',
      description: 'With API activity',
    },
  ];

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------

  return (
    <AuthGuard>
    <div className="flex h-screen bg-gray-50">
      <SidebarNav />

      <main className="flex-1 overflow-y-auto">
        <div className="p-8">
          <PageHeader
            title="Cost Management"
            description="Monitor AI usage costs and token consumption"
            breadcrumbs={[
              { label: 'Admin', href: '/admin' },
              { label: 'Costs' },
            ]}
            actions={
              <button
                onClick={handleRefresh}
                disabled={isLoading}
                className="flex items-center gap-2 px-4 py-2.5 bg-white border border-gray-200 text-gray-700 rounded-xl font-medium hover:bg-gray-50 transition-colors disabled:opacity-50"
              >
                <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
                Refresh
              </button>
            }
          />

          {/* Date Range Selector */}
          <div className="mb-6">
            <div className="inline-flex items-center bg-white border border-gray-200 rounded-xl p-1">
              {DATE_RANGES.map((range) => (
                <button
                  key={range.days}
                  onClick={() => handleDateRangeChange(range.days)}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                    selectedDays === range.days
                      ? 'bg-[#003149] text-white shadow-md'
                      : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                  }`}
                >
                  {range.label}
                </button>
              ))}
            </div>
          </div>

          {/* Error State */}
          {error && (
            <div className="mb-6 flex items-center gap-3 p-4 bg-red-50 border border-red-200 rounded-xl text-red-700">
              <AlertCircle className="w-5 h-5 flex-shrink-0" />
              <div className="flex-1">
                <p className="font-medium">Failed to load cost data</p>
                <p className="text-sm text-red-600">{error}</p>
              </div>
              <button
                onClick={handleRefresh}
                className="px-3 py-1.5 bg-red-100 text-red-700 rounded-lg text-sm font-medium hover:bg-red-200 transition-colors"
              >
                Retry
              </button>
            </div>
          )}

          {/* Loading State */}
          {isLoading && !costReport && (
            <div className="flex flex-col items-center justify-center py-20">
              <Loader2 className="w-8 h-8 text-[#003149] animate-spin mb-4" />
              <p className="text-gray-500 text-sm">Loading cost data...</p>
            </div>
          )}

          {/* Summary Cards */}
          {!isLoading || costReport ? (
            <>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
                {summaryCards.map((card, i) => (
                  <div key={i} className="bg-white rounded-2xl border border-gray-200 p-5">
                    <div className="flex items-start justify-between mb-4">
                      <div className={`p-3 rounded-xl ${card.color} text-white`}>
                        {card.icon}
                      </div>
                      <span className="text-xs text-gray-400 font-medium">
                        {card.description}
                      </span>
                    </div>
                    <p className="text-2xl font-bold text-gray-900">
                      {isLoading ? (
                        <span className="inline-block w-24 h-7 bg-gray-100 rounded animate-pulse" />
                      ) : (
                        card.value
                      )}
                    </p>
                    <p className="text-sm text-gray-500">{card.label}</p>
                  </div>
                ))}
              </div>

              {/* Cost Entries Table */}
              <div className="bg-white rounded-2xl border border-gray-200">
                <div className="p-6 border-b border-gray-100">
                  <h3 className="font-bold text-gray-900">Usage Details</h3>
                  <p className="text-sm text-gray-500 mt-1">
                    Individual cost entries for the last {selectedDays} days
                  </p>
                </div>

                {isLoading && !costReport ? (
                  <div className="p-12 text-center">
                    <Loader2 className="w-6 h-6 text-gray-400 animate-spin mx-auto mb-3" />
                    <p className="text-sm text-gray-500">Loading entries...</p>
                  </div>
                ) : costReport && costReport.entries.length > 0 ? (
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead>
                        <tr className="border-b border-gray-100">
                          <th className="text-left text-xs font-semibold text-gray-500 uppercase tracking-wider px-6 py-3">
                            Date
                          </th>
                          <th className="text-left text-xs font-semibold text-gray-500 uppercase tracking-wider px-6 py-3">
                            User
                          </th>
                          <th className="text-left text-xs font-semibold text-gray-500 uppercase tracking-wider px-6 py-3">
                            Model
                          </th>
                          <th className="text-left text-xs font-semibold text-gray-500 uppercase tracking-wider px-6 py-3">
                            Type
                          </th>
                          <th className="text-right text-xs font-semibold text-gray-500 uppercase tracking-wider px-6 py-3">
                            Input Tokens
                          </th>
                          <th className="text-right text-xs font-semibold text-gray-500 uppercase tracking-wider px-6 py-3">
                            Output Tokens
                          </th>
                          <th className="text-right text-xs font-semibold text-gray-500 uppercase tracking-wider px-6 py-3">
                            Cost
                          </th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-50">
                        {costReport.entries.map((entry) => (
                          <tr key={entry.id} className="hover:bg-gray-50 transition-colors">
                            <td className="px-6 py-4 text-sm text-gray-600 whitespace-nowrap">
                              {formatDate(entry.date)}
                            </td>
                            <td className="px-6 py-4">
                              <div className="flex items-center gap-2">
                                <div className="w-7 h-7 bg-gradient-to-br from-[#003149] to-[#7740A4] rounded-full flex items-center justify-center text-white font-semibold text-[10px]">
                                  {entry.userEmail
                                    .split('@')[0]
                                    .split('.')
                                    .map((n) => n[0])
                                    .join('')
                                    .toUpperCase()
                                    .slice(0, 2)}
                                </div>
                                <span className="text-sm text-gray-700 truncate max-w-[150px]">
                                  {entry.userEmail}
                                </span>
                              </div>
                            </td>
                            <td className="px-6 py-4">
                              <span className="text-xs bg-blue-50 text-blue-700 px-2 py-1 rounded-full font-medium">
                                {entry.model}
                              </span>
                            </td>
                            <td className="px-6 py-4">
                              <span className="text-xs bg-gray-100 text-gray-600 px-2 py-1 rounded-full font-medium capitalize">
                                {entry.requestType}
                              </span>
                            </td>
                            <td className="px-6 py-4 text-sm text-gray-600 text-right tabular-nums">
                              {formatNumber(entry.inputTokens)}
                            </td>
                            <td className="px-6 py-4 text-sm text-gray-600 text-right tabular-nums">
                              {formatNumber(entry.outputTokens)}
                            </td>
                            <td className="px-6 py-4 text-sm font-semibold text-gray-900 text-right tabular-nums">
                              {formatCurrency(entry.cost)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="p-12 text-center">
                    <DollarSign className="w-10 h-10 text-gray-300 mx-auto mb-3" />
                    <p className="text-sm font-medium text-gray-500">No cost entries found</p>
                    <p className="text-xs text-gray-400 mt-1">
                      No API usage recorded in the last {selectedDays} days
                    </p>
                  </div>
                )}
              </div>
            </>
          ) : null}
        </div>
      </main>
    </div>
    </AuthGuard>
  );
}
