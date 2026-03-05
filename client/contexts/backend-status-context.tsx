'use client';

import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { checkBackendHealth } from '@/hooks/use-agent-stream';

interface BackendStatusContextValue {
  backendConnected: boolean | null;
}

const BackendStatusContext = createContext<BackendStatusContextValue>({ backendConnected: null });

/**
 * Fires a single backend health check on app mount, then re-checks every 30 seconds.
 * Shared via context so TopNav (mounted on every page) reads the cached result
 * instead of issuing a fresh network request on each navigation.
 */
export function BackendStatusProvider({ children }: { children: ReactNode }) {
  const [backendConnected, setBackendConnected] = useState<boolean | null>(null);

  useEffect(() => {
    checkBackendHealth().then(setBackendConnected);
    const interval = setInterval(() => {
      checkBackendHealth().then(setBackendConnected);
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <BackendStatusContext.Provider value={{ backendConnected }}>
      {children}
    </BackendStatusContext.Provider>
  );
}

export function useBackendStatus(): BackendStatusContextValue {
  return useContext(BackendStatusContext);
}
