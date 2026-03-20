'use client';

import { useCallback, useEffect } from 'react';
import { trackEvent, trackClick } from '@/lib/analytics';

/**
 * Hook for tracking analytics events in React components.
 * Automatically initializes the analytics emitter on mount.
 */
export function useAnalytics() {
  useEffect(() => {
    // Track page view on mount
    trackEvent('page_view');
  }, []);

  const track = useCallback((event: string, metadata?: Record<string, unknown>) => {
    trackEvent(event, metadata);
  }, []);

  const click = useCallback((target: string, metadata?: Record<string, unknown>) => {
    trackClick(target, metadata);
  }, []);

  return { track, click };
}
