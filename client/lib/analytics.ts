/**
 * Lightweight analytics event emitter for EAGLE.
 * Accumulates events, flushes every 5s or on beforeunload via sendBeacon().
 */

type AnalyticsEvent = {
  event: string;
  target?: string;
  metadata?: Record<string, unknown>;
  timestamp: number;
  page: string;
};

const FLUSH_INTERVAL_MS = 5000;
const MAX_BATCH_SIZE = 50;

let eventBuffer: AnalyticsEvent[] = [];
let flushTimer: ReturnType<typeof setInterval> | null = null;
let initialized = false;

function getAuthToken(): string | null {
  // Try to read token from localStorage (set by auth context)
  try {
    return localStorage.getItem('eagle_auth_token');
  } catch {
    return null;
  }
}

function flush() {
  if (eventBuffer.length === 0) return;

  const batch = eventBuffer.splice(0, MAX_BATCH_SIZE);
  const payload = JSON.stringify({ events: batch });

  // Use sendBeacon for reliability (works on page unload)
  if (navigator.sendBeacon) {
    const blob = new Blob([payload], { type: 'application/json' });
    navigator.sendBeacon('/api/analytics/events', blob);
  } else {
    // Fallback to fetch
    fetch('/api/analytics/events', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: payload,
      keepalive: true,
    }).catch(() => {
      // Silent fail — analytics should never break the app
    });
  }
}

function init() {
  if (initialized || typeof window === 'undefined') return;
  initialized = true;

  flushTimer = setInterval(flush, FLUSH_INTERVAL_MS);

  window.addEventListener('beforeunload', flush);

  // Dead click detection — clicks on non-interactive elements
  document.addEventListener('click', (e) => {
    const target = e.target as HTMLElement;
    if (!target) return;

    const tag = target.tagName.toLowerCase();
    const isInteractive = ['a', 'button', 'input', 'select', 'textarea'].includes(tag)
      || target.closest('a, button, [role="button"], [tabindex]')
      || target.getAttribute('role') === 'button'
      || target.getAttribute('tabindex') !== null;

    if (!isInteractive) {
      trackEvent('dead_click', {
        target: `${tag}.${target.className?.split?.(' ')?.[0] || ''}`,
        text: target.textContent?.slice(0, 50),
      });
    }
  });
}

export function trackEvent(event: string, metadata?: Record<string, unknown>) {
  if (typeof window === 'undefined') return;

  init();

  eventBuffer.push({
    event,
    metadata,
    timestamp: Date.now(),
    page: window.location.pathname,
  });

  // Auto-flush if buffer is getting large
  if (eventBuffer.length >= MAX_BATCH_SIZE) {
    flush();
  }
}

export function trackClick(target: string, metadata?: Record<string, unknown>) {
  trackEvent('click', { target, ...metadata });
}

/** Cleanup — call on app unmount if needed */
export function destroyAnalytics() {
  if (flushTimer) clearInterval(flushTimer);
  flush();
  initialized = false;
}
