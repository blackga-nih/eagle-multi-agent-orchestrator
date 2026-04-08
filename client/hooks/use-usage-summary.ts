'use client';

import { useState, useEffect, useRef, useCallback } from 'react';

export interface UsageSummary {
  totalCostUsd: number;
  totalRequests: number;
  totalTokens: number;
  totalInputTokens: number;
  totalOutputTokens: number;
}

/**
 * Fetches the 30-day usage summary from GET /api/user/usage on mount
 * and refreshes every 5 minutes.
 */
export function useUsageSummary(
  getToken: () => Promise<string | null>,
): UsageSummary | null {
  const [data, setData] = useState<UsageSummary | null>(null);
  const getTokenRef = useRef(getToken);
  getTokenRef.current = getToken;

  const fetchUsage = useCallback(async () => {
    try {
      const token = await getTokenRef.current();
      if (!token) return;
      const res = await fetch('/api/user/usage?days=30', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) return;
      const json = await res.json();
      setData({
        totalCostUsd: json.total_cost_usd ?? 0,
        totalRequests: json.total_requests ?? 0,
        totalTokens: json.total_tokens ?? 0,
        totalInputTokens: json.total_input_tokens ?? 0,
        totalOutputTokens: json.total_output_tokens ?? 0,
      });
    } catch {
      // Non-blocking — swallow errors
    }
  }, []);

  useEffect(() => {
    void fetchUsage();
    const interval = setInterval(fetchUsage, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, [fetchUsage]);

  return data;
}
