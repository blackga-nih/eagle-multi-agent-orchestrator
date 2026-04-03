'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { listPackages, getPackageDocuments, deletePackage as apiDeletePackage } from '@/lib/document-api';
import type { PackageInfo, PackageDocument } from '@/lib/document-api';

export interface UseAllPackagesResult {
  packages: PackageInfo[];
  loading: boolean;
  error: string | null;
  refetch: () => void;
  /** Delete a package by ID (optimistic removal from local state). */
  removePackage: (packageId: string) => Promise<void>;
  /** Fetch documents for a package (cached after first call). */
  fetchDocuments: (packageId: string) => Promise<PackageDocument[]>;
  /** Cached documents keyed by package ID. */
  documentsCache: Record<string, PackageDocument[]>;
  /** Set of package IDs currently loading documents. */
  loadingDocs: Set<string>;
}

/**
 * Hook that fetches all user packages from GET /api/packages on mount,
 * caches document lists per package, and exposes a refetch() for refresh
 * after streaming completes.
 */
export function useAllPackages(getToken: () => Promise<string | null>): UseAllPackagesResult {
  const [packages, setPackages] = useState<PackageInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [documentsCache, setDocumentsCache] = useState<Record<string, PackageDocument[]>>({});
  const [loadingDocs, setLoadingDocs] = useState<Set<string>>(new Set());

  // Avoid stale closures in fetchPackages
  const getTokenRef = useRef(getToken);
  getTokenRef.current = getToken;

  const fetchPackages = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const token = await getTokenRef.current();
      const result = await listPackages(token);
      // Sort newest first
      result.sort((a, b) => {
        const da = a.created_at ? new Date(a.created_at).getTime() : 0;
        const db = b.created_at ? new Date(b.created_at).getTime() : 0;
        return db - da;
      });
      setPackages(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load packages');
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch on mount
  useEffect(() => {
    void fetchPackages();
  }, [fetchPackages]);

  const fetchDocuments = useCallback(
    async (packageId: string): Promise<PackageDocument[]> => {
      // Return cached if available
      if (documentsCache[packageId]) return documentsCache[packageId];

      setLoadingDocs((prev) => new Set(prev).add(packageId));
      try {
        const token = await getTokenRef.current();
        const docs = await getPackageDocuments(packageId, token);
        setDocumentsCache((prev) => ({ ...prev, [packageId]: docs }));
        return docs;
      } catch {
        return [];
      } finally {
        setLoadingDocs((prev) => {
          const next = new Set(prev);
          next.delete(packageId);
          return next;
        });
      }
    },
    [documentsCache],
  );

  const removePackage = useCallback(
    async (packageId: string) => {
      const token = await getTokenRef.current();
      await apiDeletePackage(packageId, token);
      setPackages((prev) => prev.filter((p) => p.package_id !== packageId));
      setDocumentsCache((prev) => {
        const next = { ...prev };
        delete next[packageId];
        return next;
      });
    },
    [],
  );

  return {
    packages,
    loading,
    error,
    refetch: fetchPackages,
    removePackage,
    fetchDocuments,
    documentsCache,
    loadingDocs,
  };
}
