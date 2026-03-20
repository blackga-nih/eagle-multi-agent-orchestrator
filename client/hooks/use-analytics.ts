/**
 * Analytics hook for tracking user events.
 *
 * Events are batched and sent to /api/analytics/events endpoint.
 */

import { useCallback, useRef, useEffect } from 'react';

interface AnalyticsEvent {
  event: string;
  page?: string;
  metadata?: Record<string, unknown>;
  timestamp: number;
}

const BATCH_SIZE = 10;
const FLUSH_INTERVAL_MS = 5000;

export function useAnalytics() {
  const eventQueue = useRef<AnalyticsEvent[]>([]);
  const flushTimeout = useRef<NodeJS.Timeout | null>(null);

  const flush = useCallback(async () => {
    if (eventQueue.current.length === 0) return;

    const events = [...eventQueue.current];
    eventQueue.current = [];

    try {
      await fetch('/api/analytics/events', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ events }),
      });
    } catch (error) {
      // Silent fail - analytics should not break the app
      console.debug('Analytics flush failed:', error);
    }
  }, []);

  const scheduleFlush = useCallback(() => {
    if (flushTimeout.current) return;
    flushTimeout.current = setTimeout(() => {
      flushTimeout.current = null;
      flush();
    }, FLUSH_INTERVAL_MS);
  }, [flush]);

  const track = useCallback((event: string, metadata?: Record<string, unknown>) => {
    eventQueue.current.push({
      event,
      page: typeof window !== 'undefined' ? window.location.pathname : undefined,
      metadata,
      timestamp: Date.now(),
    });

    if (eventQueue.current.length >= BATCH_SIZE) {
      flush();
    } else {
      scheduleFlush();
    }
  }, [flush, scheduleFlush]);

  // Flush on unmount
  useEffect(() => {
    return () => {
      if (flushTimeout.current) {
        clearTimeout(flushTimeout.current);
      }
      if (eventQueue.current.length > 0) {
        // Sync flush on unmount (best effort)
        const events = [...eventQueue.current];
        navigator.sendBeacon?.(
          '/api/analytics/events',
          JSON.stringify({ events })
        );
      }
    };
  }, []);

  return { track };
}
