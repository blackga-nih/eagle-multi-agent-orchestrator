'use client';

/**
 * Fire-and-forget POST to /api/errors/report.
 *
 * Used by ErrorBoundary.componentDidCatch plus the window error /
 * unhandledrejection listeners. Telemetry never breaks the UI — every
 * failure mode is swallowed (fetch rejection, sendBeacon unavailable,
 * SSR context, etc.).
 *
 * Uses navigator.sendBeacon when available so reports fire even during
 * a page unload; falls back to fetch with keepalive:true otherwise.
 */

export interface ClientErrorReport {
  source:
    | 'react_error_boundary'
    | 'window_error'
    | 'unhandled_rejection'
    | string;
  error_type?: string;
  message: string;
  stack?: string;
  component_stack?: string;
  path?: string;
  user_agent?: string;
}

const ENDPOINT = '/api/errors/report';

// Per-source throttle: don't re-send the same error_type + message within
// this many ms. Defends against a render loop DDoSing our own endpoint.
const THROTTLE_MS = 30_000;

const _recentKeys = new Map<string, number>();

function _throttleKey(r: ClientErrorReport): string {
  return `${r.source}|${r.error_type || ''}|${(r.message || '').slice(0, 120)}`;
}

function _shouldSkip(r: ClientErrorReport): boolean {
  const key = _throttleKey(r);
  const now = Date.now();
  const last = _recentKeys.get(key);
  if (last && now - last < THROTTLE_MS) {
    return true;
  }
  _recentKeys.set(key, now);
  // Evict stale entries so the map doesn't grow unbounded.
  if (_recentKeys.size > 64) {
    for (const [k, ts] of _recentKeys.entries()) {
      if (now - ts > THROTTLE_MS) _recentKeys.delete(k);
    }
  }
  return false;
}

export function reportClientError(report: ClientErrorReport): void {
  if (typeof window === 'undefined') return; // SSR — nothing to report
  if (_shouldSkip(report)) return;

  const payload: ClientErrorReport = {
    ...report,
    path: report.path ?? window.location.pathname,
    user_agent: report.user_agent ?? navigator.userAgent,
  };

  try {
    const body = JSON.stringify(payload);

    // sendBeacon keeps the request alive across navigation and doesn't
    // expose a response — perfect for fire-and-forget telemetry.
    if (typeof navigator !== 'undefined' && typeof navigator.sendBeacon === 'function') {
      const blob = new Blob([body], { type: 'application/json' });
      const ok = navigator.sendBeacon(ENDPOINT, blob);
      if (ok) return;
      // fall through to fetch if sendBeacon refused
    }

    void fetch(ENDPOINT, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body,
      keepalive: true,
      credentials: 'same-origin',
    }).catch(() => {
      /* swallow */
    });
  } catch {
    /* swallow — telemetry never breaks the UI */
  }
}
