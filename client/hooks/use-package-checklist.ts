'use client';

import { useCallback, useEffect, useState } from 'react';

import {
  getPackageChecklist as fetchPackageChecklist,
  type PackageChecklist,
} from '@/lib/document-api';

import type { PackageChecklist as PushedChecklist } from './use-package-state';

/**
 * Push-first package checklist hook.
 *
 * Source-of-truth ordering:
 *   1. If the SSE-pushed `state.checklist.items` is present, use it. This
 *      is the hot path during an active chat — the agentic service emits
 *      `checklist_update` frames after every doc-touching tool call, so
 *      the hook never lags behind a real write.
 *   2. Otherwise, fall back to a one-shot `GET /api/packages/{id}/checklist`
 *      cold-load. Used on tab reload, viewer-page warm boot, and package
 *      switch — anywhere there's no live stream.
 *
 * No polling, no setInterval. The PATCH /required-docs response carries
 * the freshly-derived checklist; callers should pass it to `mutate()` to
 * apply optimistically.
 */
export function usePackageChecklist(
  packageId: string | null,
  pushed: PushedChecklist | null,
  token?: string | null,
) {
  const [fetched, setFetched] = useState<PackageChecklist | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  // The SSE push wins when its items[] is present. Otherwise we fall back
  // to the cold-load fetch.
  const checklist: PackageChecklist | null =
    pushed && pushed.items && pushed.items.length >= 0
      ? (pushed as unknown as PackageChecklist)
      : fetched;

  // Cold-load fetch when (a) no push has arrived yet and (b) we have a
  // package ID. Invalidates on package switch.
  useEffect(() => {
    if (!packageId) {
      setFetched(null);
      return;
    }
    if (pushed && pushed.items) {
      // Push path is live — no need to fetch.
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    fetchPackageChecklist(packageId, token)
      .then((data) => {
        if (!cancelled) setFetched(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err : new Error(String(err)));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [packageId, pushed, token]);

  /** Apply a PATCH response (or any externally-derived checklist) without a refetch. */
  const mutate = useCallback((next: PackageChecklist) => {
    setFetched(next);
  }, []);

  return {
    checklist,
    items: checklist?.items ?? [],
    extra: checklist?.extra ?? [],
    pathway: checklist?.pathway ?? null,
    custom: checklist?.custom ?? false,
    loading,
    error,
    mutate,
  };
}
