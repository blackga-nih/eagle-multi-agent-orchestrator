'use client';

import { useState, useEffect, useCallback } from 'react';
import { CreditCard, Activity, Shield, AlertTriangle, Loader2, RefreshCw } from 'lucide-react';
import AuthGuard from '@/components/auth/auth-guard';
import SidebarNav from '@/components/layout/sidebar-nav';
import PageHeader from '@/components/layout/page-header';
import { useAuth } from '@/contexts/auth-context';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface UsageData {
  totalRequests: number;
  totalTokens: number;
  totalCost: number;
  limits: {
    maxRequests: number;
    maxTokens: number;
    maxCostUsd: number;
  };
  periodStart: string;
  periodEnd: string;
}

// ---------------------------------------------------------------------------
// Tier configuration
// ---------------------------------------------------------------------------

const TIER_CONFIG: Record<string, { label: string; color: string; bgColor: string; features: string[] }> = {
  free: {
    label: 'Free',
    color: 'text-gray-700',
    bgColor: 'bg-gray-100',
    features: ['5 requests/day', 'Basic document generation', 'Email support'],
  },
  standard: {
    label: 'Standard',
    color: 'text-blue-700',
    bgColor: 'bg-blue-50',
    features: ['100 requests/day', 'All document templates', 'Priority email support', 'Workflow automation'],
  },
  premium: {
    label: 'Premium',
    color: 'text-purple-700',
    bgColor: 'bg-purple-50',
    features: [
      'Unlimited requests',
      'All document templates',
      'Priority support',
      'Workflow automation',
      'Custom agent skills',
      'Analytics dashboard',
    ],
  },
  enterprise: {
    label: 'Enterprise',
    color: 'text-[#003149]',
    bgColor: 'bg-[#003149]/5',
    features: [
      'Unlimited requests',
      'Custom document templates',
      'Dedicated support',
      'Advanced workflow automation',
      'Custom agent skills',
      'Full analytics & reporting',
      'SSO & SAML integration',
    ],
  },
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatNumber(value: number): string {
  return new Intl.NumberFormat('en-US').format(value);
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  }).format(value);
}

/**
 * Calculate usage percentage and return a value clamped between 0 and 100.
 */
function usagePercent(used: number, limit: number): number {
  if (limit <= 0) return 0;
  return Math.min(Math.round((used / limit) * 100), 100);
}

/**
 * Determine the status color based on percentage thresholds.
 *   0-59%  -> green
 *  60-84%  -> yellow/amber
 *  85-100% -> red
 */
function statusColor(percent: number): { bar: string; text: string; bg: string; label: string } {
  if (percent >= 85) {
    return { bar: 'bg-red-500', text: 'text-red-700', bg: 'bg-red-50', label: 'Critical' };
  }
  if (percent >= 60) {
    return { bar: 'bg-amber-500', text: 'text-amber-700', bg: 'bg-amber-50', label: 'Warning' };
  }
  return { bar: 'bg-green-500', text: 'text-green-700', bg: 'bg-green-50', label: 'Healthy' };
}

// ---------------------------------------------------------------------------
// Progress Bar Component
// ---------------------------------------------------------------------------

function ProgressBar({ label, used, limit, unit }: { label: string; used: number; limit: number; unit: string }) {
  const percent = usagePercent(used, limit);
  const colors = statusColor(percent);

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium text-gray-700">{label}</span>
        <span className="text-sm text-gray-500">
          {unit === '$' ? formatCurrency(used) : formatNumber(used)}{' '}
          <span className="text-gray-400">/</span>{' '}
          {unit === '$' ? formatCurrency(limit) : formatNumber(limit)}
        </span>
      </div>
      <div className="w-full h-3 bg-gray-100 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${colors.bar}`}
          style={{ width: `${percent}%` }}
        />
      </div>
      <div className="flex items-center justify-between mt-1">
        <span className={`text-xs font-medium ${colors.text}`}>{percent}% used</span>
        <span className="text-xs text-gray-400">
          {unit === '$' ? formatCurrency(limit - used) : formatNumber(limit - used)} remaining
        </span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page Component
// ---------------------------------------------------------------------------

export default function SubscriptionPage() {
  const { user, getToken } = useAuth();
  const [usageData, setUsageData] = useState<UsageData | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // -------------------------------------------------------------------------
  // Data fetching
  // -------------------------------------------------------------------------

  const fetchUsage = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const token = await getToken();
      const response = await fetch('/api/user/usage', {
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        throw new Error(`Failed to fetch usage data (${response.status})`);
      }

      const data: UsageData = await response.json();
      setUsageData(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'An unexpected error occurred';
      setError(message);
      setUsageData(null);
    } finally {
      setIsLoading(false);
    }
  }, [getToken]);

  useEffect(() => {
    fetchUsage();
  }, [fetchUsage]);

  // -------------------------------------------------------------------------
  // Derived values
  // -------------------------------------------------------------------------

  const tierKey = user?.tier?.toLowerCase() || 'standard';
  const tier = TIER_CONFIG[tierKey] || TIER_CONFIG.standard;

  // Compute an overall usage percentage (average of all three dimensions) for
  // the rate limit status indicator.
  const overallPercent = usageData
    ? Math.round(
        (usagePercent(usageData.totalRequests, usageData.limits.maxRequests) +
          usagePercent(usageData.totalTokens, usageData.limits.maxTokens) +
          usagePercent(usageData.totalCost, usageData.limits.maxCostUsd)) /
          3,
      )
    : 0;

  const overallStatus = statusColor(overallPercent);

  // -------------------------------------------------------------------------
  // Summary cards
  // -------------------------------------------------------------------------

  const summaryCards = [
    {
      label: 'Total Requests',
      value: usageData ? formatNumber(usageData.totalRequests) : '--',
      icon: <Activity className="w-5 h-5" />,
      color: 'bg-blue-500',
      description: 'This billing period',
    },
    {
      label: 'Total Tokens',
      value: usageData ? formatNumber(usageData.totalTokens) : '--',
      icon: <CreditCard className="w-5 h-5" />,
      color: 'bg-purple-500',
      description: 'Input + Output',
    },
    {
      label: 'Total Cost',
      value: usageData ? formatCurrency(usageData.totalCost) : '--',
      icon: <Shield className="w-5 h-5" />,
      color: 'bg-green-500',
      description: 'Accumulated spend',
    },
  ];

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return (
    <AuthGuard>
    <div className="flex h-screen bg-gray-50">
      <SidebarNav />

      <main className="flex-1 overflow-y-auto">
        <div className="p-8">
          <PageHeader
            title="Subscription & Usage"
            description="Monitor your plan, usage limits, and rate limit status"
            breadcrumbs={[
              { label: 'Admin', href: '/admin' },
              { label: 'Subscription' },
            ]}
            actions={
              <button
                onClick={fetchUsage}
                disabled={isLoading}
                className="flex items-center gap-2 px-4 py-2.5 bg-white border border-gray-200 text-gray-700 rounded-xl font-medium hover:bg-gray-50 transition-colors disabled:opacity-50"
              >
                <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
                Refresh
              </button>
            }
          />

          {/* Error State */}
          {error && (
            <div className="mb-6 flex items-center gap-3 p-4 bg-red-50 border border-red-200 rounded-xl text-red-700">
              <AlertTriangle className="w-5 h-5 flex-shrink-0" />
              <div className="flex-1">
                <p className="font-medium">Failed to load usage data</p>
                <p className="text-sm text-red-600">{error}</p>
              </div>
              <button
                onClick={fetchUsage}
                className="px-3 py-1.5 bg-red-100 text-red-700 rounded-lg text-sm font-medium hover:bg-red-200 transition-colors"
              >
                Retry
              </button>
            </div>
          )}

          {/* Loading State */}
          {isLoading && !usageData && (
            <div className="flex flex-col items-center justify-center py-20">
              <Loader2 className="w-8 h-8 text-[#003149] animate-spin mb-4" />
              <p className="text-gray-500 text-sm">Loading subscription data...</p>
            </div>
          )}

          {/* Content - show once data is loaded (or stale data exists) */}
          {(!isLoading || usageData) && (
            <>
              {/* Current Tier + Rate Limit Status */}
              <div className="grid lg:grid-cols-3 gap-6 mb-8">
                {/* Current Tier Card */}
                <div className="lg:col-span-2 bg-white rounded-2xl border border-gray-200 p-6">
                  <div className="flex items-start justify-between mb-6">
                    <div>
                      <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
                        Current Plan
                      </p>
                      <div className="flex items-center gap-3">
                        <div className="p-3 bg-gradient-to-br from-[#003149] to-[#7740A4] rounded-xl text-white">
                          <CreditCard className="w-6 h-6" />
                        </div>
                        <div>
                          <h2 className="text-2xl font-bold text-gray-900">{tier.label}</h2>
                          <p className="text-sm text-gray-500">
                            {user?.email || 'No email available'}
                          </p>
                        </div>
                      </div>
                    </div>
                    <span
                      className={`text-xs font-bold uppercase px-3 py-1.5 rounded-full ${tier.bgColor} ${tier.color}`}
                    >
                      {tier.label} Tier
                    </span>
                  </div>

                  {/* Tier Features */}
                  <div className="border-t border-gray-100 pt-4">
                    <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
                      Included Features
                    </p>
                    <div className="grid sm:grid-cols-2 gap-2">
                      {tier.features.map((feature, i) => (
                        <div key={i} className="flex items-center gap-2">
                          <div className="w-5 h-5 bg-green-100 rounded-full flex items-center justify-center flex-shrink-0">
                            <svg
                              className="w-3 h-3 text-green-600"
                              fill="none"
                              stroke="currentColor"
                              viewBox="0 0 24 24"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M5 13l4 4L19 7"
                              />
                            </svg>
                          </div>
                          <span className="text-sm text-gray-600">{feature}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Rate Limit Status Indicator */}
                <div className="bg-white rounded-2xl border border-gray-200 p-6 flex flex-col">
                  <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-4">
                    Rate Limit Status
                  </p>

                  <div className="flex-1 flex flex-col items-center justify-center">
                    {/* Circular indicator */}
                    <div
                      className={`w-28 h-28 rounded-full flex items-center justify-center mb-4 ${overallStatus.bg} border-4 ${
                        overallPercent >= 85
                          ? 'border-red-300'
                          : overallPercent >= 60
                            ? 'border-amber-300'
                            : 'border-green-300'
                      }`}
                    >
                      <div className="text-center">
                        <p className={`text-2xl font-bold ${overallStatus.text}`}>
                          {isLoading ? (
                            <span className="inline-block w-12 h-7 bg-gray-100 rounded animate-pulse" />
                          ) : (
                            `${overallPercent}%`
                          )}
                        </p>
                        <p className="text-[10px] text-gray-500 font-medium">USED</p>
                      </div>
                    </div>

                    <span
                      className={`text-xs font-bold uppercase px-3 py-1.5 rounded-full ${overallStatus.bg} ${overallStatus.text}`}
                    >
                      {overallStatus.label}
                    </span>

                    {overallPercent >= 85 && (
                      <div className="mt-4 flex items-start gap-2 p-3 bg-red-50 rounded-xl">
                        <AlertTriangle className="w-4 h-4 text-red-500 flex-shrink-0 mt-0.5" />
                        <p className="text-xs text-red-600">
                          Approaching rate limit. Consider upgrading your plan to avoid service
                          interruptions.
                        </p>
                      </div>
                    )}

                    {overallPercent >= 60 && overallPercent < 85 && (
                      <div className="mt-4 flex items-start gap-2 p-3 bg-amber-50 rounded-xl">
                        <AlertTriangle className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" />
                        <p className="text-xs text-amber-600">
                          Usage is moderate. Monitor to avoid reaching limits before the period
                          resets.
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* Usage Summary Cards */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
                {summaryCards.map((card, i) => (
                  <div key={i} className="bg-white rounded-2xl border border-gray-200 p-5">
                    <div className="flex items-start justify-between mb-4">
                      <div className={`p-3 rounded-xl ${card.color} text-white`}>
                        {card.icon}
                      </div>
                      <span className="text-xs text-gray-400 font-medium">{card.description}</span>
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

              {/* Usage Progress Bars */}
              {usageData && (
                <div className="bg-white rounded-2xl border border-gray-200 p-6">
                  <div className="mb-6">
                    <h3 className="font-bold text-gray-900">Usage Breakdown</h3>
                    <p className="text-sm text-gray-500 mt-1">
                      Current usage against your plan limits
                    </p>
                  </div>

                  <div className="space-y-6">
                    <ProgressBar
                      label="API Requests"
                      used={usageData.totalRequests}
                      limit={usageData.limits.maxRequests}
                      unit="#"
                    />
                    <ProgressBar
                      label="Token Usage"
                      used={usageData.totalTokens}
                      limit={usageData.limits.maxTokens}
                      unit="#"
                    />
                    <ProgressBar
                      label="Cost"
                      used={usageData.totalCost}
                      limit={usageData.limits.maxCostUsd}
                      unit="$"
                    />
                  </div>

                  {/* Period info */}
                  {usageData.periodStart && usageData.periodEnd && (
                    <div className="mt-6 pt-4 border-t border-gray-100 flex items-center justify-between">
                      <p className="text-xs text-gray-400">
                        Billing period:{' '}
                        {new Date(usageData.periodStart).toLocaleDateString('en-US', {
                          month: 'short',
                          day: 'numeric',
                          year: 'numeric',
                        })}{' '}
                        &ndash;{' '}
                        {new Date(usageData.periodEnd).toLocaleDateString('en-US', {
                          month: 'short',
                          day: 'numeric',
                          year: 'numeric',
                        })}
                      </p>
                      <p className="text-xs text-gray-400">
                        Limits reset at the start of each billing period
                      </p>
                    </div>
                  )}
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
