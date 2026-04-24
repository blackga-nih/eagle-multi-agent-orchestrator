'use client';

import { useEffect } from 'react';
import { reportClientError } from '@/lib/report-client-error';

/**
 * Mount-once listener for window-level errors that React's ErrorBoundary
 * cannot catch:
 *   - window 'error' events (uncaught thrown errors outside React render)
 *   - window 'unhandledrejection' events (promise rejections with no catch)
 *
 * Both are forwarded to /api/errors/report via reportClientError, which
 * fans out to the debug Teams channel. Telemetry-only — never affects UX.
 *
 * Rendered empty — this component exists purely for the useEffect hook.
 */
export function GlobalErrorListener(): null {
  useEffect(() => {
    if (typeof window === 'undefined') return;

    const onError = (ev: ErrorEvent) => {
      // Ignore ResizeObserver noise — known benign browser spam.
      if (ev.message?.includes('ResizeObserver')) return;
      reportClientError({
        source: 'window_error',
        error_type: ev.error?.name || 'Error',
        message: ev.message || String(ev.error || 'unknown'),
        stack: ev.error?.stack,
      });
    };

    const onRejection = (ev: PromiseRejectionEvent) => {
      const reason = ev.reason;
      let msg = 'unhandled rejection';
      let errName = 'UnhandledRejection';
      let stack: string | undefined;
      if (reason instanceof Error) {
        msg = reason.message;
        errName = reason.name || 'Error';
        stack = reason.stack;
      } else if (typeof reason === 'string') {
        msg = reason;
      } else if (reason) {
        try {
          msg = JSON.stringify(reason).slice(0, 500);
        } catch {
          msg = String(reason);
        }
      }
      reportClientError({
        source: 'unhandled_rejection',
        error_type: errName,
        message: msg,
        stack,
      });
    };

    window.addEventListener('error', onError);
    window.addEventListener('unhandledrejection', onRejection);
    return () => {
      window.removeEventListener('error', onError);
      window.removeEventListener('unhandledrejection', onRejection);
    };
  }, []);

  return null;
}
